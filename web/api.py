from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from account.email import EmailService
from account.service import AccountError, AccountService
from core.database import Database
from hosting.service import HostingService
db = Database(os.getenv("DATABASE_PATH", "data/helzerx.db"))
accounts = AccountService(db)
hosting = HostingService(db, None)  # replaced after economy initialization
app = FastAPI(title="HelzerX Cloud API", version="1.0.0")


class RegisterBody(BaseModel):
    link_code: str
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RedeemBody(BaseModel):
    plan_key: str


async def current_user(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required.")
    user_id = await accounts.user_from_session(authorization[7:].strip())
    if not user_id:
        raise HTTPException(401, "Invalid or expired session.")
    return user_id


@app.on_event("startup")
async def startup() -> None:
    global hosting
    await db.initialize()
    from economy.service import EconomyService
    hosting = HostingService(db, EconomyService(db))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "helzerx-cloud"}


@app.post("/auth/register")
async def register(body: RegisterBody):
    smtp = os.getenv("SMTP_HOST")
    if not smtp:
        raise HTTPException(503, "Email verification is not configured.")
    user_id = await accounts.consume_link_code(body.link_code)
    if not user_id:
        raise HTTPException(400, "Invalid or expired Discord link code.")
    try:
        token = await accounts.register(user_id, str(body.email), body.password)
    except AccountError as exc:
        raise HTTPException(400, str(exc))
    if smtp:
        mail = EmailService(
            smtp, int(os.getenv("SMTP_PORT", "587")), os.getenv("SMTP_USERNAME", ""),
            os.getenv("SMTP_PASSWORD", ""), os.getenv("SMTP_SENDER", "noreply@example.com"),
        )
        await mail.send_verification(str(body.email), token, os.getenv("WEB_BASE_URL", "http://localhost:8000"))
    return {"status": "verification_pending"}


@app.get("/auth/verify")
async def verify(token: str):
    return {"verified": await accounts.verify_email(token)}


@app.post("/auth/login")
async def login(body: LoginBody):
    try:
        user_id = await accounts.authenticate(str(body.email), body.password)
        token = await accounts.create_session(user_id)
    except AccountError as exc:
        raise HTTPException(401, str(exc))
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        await accounts.revoke_session(authorization[7:].strip())
    return {"status": "ok"}


@app.get("/plans/{kind}")
async def plans(kind: str, _: int = Depends(current_user)):
    if kind not in {"vps", "minecraft"}:
        raise HTTPException(400, "Invalid plan type.")
    rows = await hosting.get_plans(kind)
    return [dict(r) for r in rows]


@app.get("/servers")
async def servers(user_id: int = Depends(current_user)):
    rows = await db.fetchall(
        "SELECT id,plan_id,vmid,hostname,kind,status,ipv4,ipv6,os,expires_at,provider_id,metadata "
        "FROM vps_servers WHERE user_id=? ORDER BY id DESC", (user_id,)
    )
    return [dict(r) for r in rows]


@app.post("/redeem")
async def redeem(body: RedeemBody, user_id: int = Depends(current_user)):
    try:
        result = await hosting.redeem(user_id, body.plan_key)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"redemption_id": result.redemption_id, "status": result.status}

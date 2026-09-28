from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib


class EmailService:
    def __init__(self, host: str, port: int, username: str, password: str, sender: str, tls: bool = True):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.tls = tls

    async def send_verification(self, recipient: str, token: str, base_url: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = "Verify your HelzerX Cloud account"
        message.set_content(
            "Verify your HelzerX Cloud account using this link:\n\n"
            "%s/verify?token=%s\n\n"
            "This link expires in 24 hours." % (base_url.rstrip("/"), token)
        )
        await aiosmtplib.send(
            message,
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            start_tls=self.tls,
        )

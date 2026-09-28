FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /app/data \
    && chown -R bot:bot /app

# Compose runs the service as root because /app/data is a bind mount whose
# host ownership may not match the image's non-root UID. The application never
# needs host access outside the mounted data directory.
CMD ["python", "bot.py"]

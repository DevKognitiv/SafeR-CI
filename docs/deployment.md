# SafeR CI — Deployment Guide

## Prerequisites

- Linux server (Ubuntu 22.04 LTS recommended)
- Docker & Docker Compose v2
- Domain name with DNS configured
- Twilio account (SMS alerts)
- Firebase project (push notifications)

## 1. Clone and Configure

```bash
git clone https://github.com/DevKognitiv/SafeR-CI.git
cd SafeR-CI/backend
cp .env.example .env
# Edit .env with your actual secrets
nano .env
```

## 2. Start Backend Services

```bash
docker-compose up -d
docker-compose exec api alembic upgrade head  # Run DB migrations
```

## 3. Deploy Home Assistant Node

On your Raspberry Pi 4:
1. Flash Home Assistant OS: https://www.home-assistant.io/installation/raspberrypi
2. Copy `ha-config/` files to your HA config directory (`/config/`)
3. Edit `secrets.yaml` with your hub-specific values
4. Install required add-ons: Mosquitto, Node-RED, MariaDB
5. Restart Home Assistant

## 4. Build Flutter App

```bash
cd mobile
flutter pub get
flutter build apk --release  # Android
flutter build ios --release  # iOS
```

## 5. Configure Nginx

```bash
cp infrastructure/nginx/nginx.conf /etc/nginx/conf.d/safer-ci.conf
certbot --nginx -d api.safer-ci.app
nginx -s reload
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| SECRET_KEY | JWT signing key | ✅ |
| DATABASE_URL | PostgreSQL connection string | ✅ |
| REDIS_URL | Redis connection string | ✅ |
| TWILIO_ACCOUNT_SID | Twilio Account SID | ✅ |
| TWILIO_AUTH_TOKEN | Twilio Auth Token | ✅ |
| TWILIO_FROM_NUMBER | Twilio phone number | ✅ |
| FIREBASE_PROJECT_ID | Firebase project | For push |
| WHATSAPP_TOKEN | WhatsApp Business token | For WhatsApp |
| HUB_WEBHOOK_SECRET | Shared HA node secret | ✅ |

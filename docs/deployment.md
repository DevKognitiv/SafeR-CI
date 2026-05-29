# SafeR CI — Deployment Guide

## Prerequisites

- Linux server (Ubuntu 22.04 LTS recommended) or macOS for local dev
- PostgreSQL 15+ with the PostGIS extension (Docker is **optional** — see below)
- Python 3.10+
- Domain name with DNS configured (production)
- Twilio account (SMS alerts) and Firebase project (push notifications)

## 1. Clone and Configure

```bash
git clone https://github.com/DevKognitiv/SafeR-CI.git
cd SafeR-CI/backend
cp .env.example .env
# Edit .env with your actual secrets
nano .env
```

## 2. Provision the database

The backend needs PostgreSQL **with PostGIS** (the `Incident` model uses a
`geography` column and `ST_DWithin` radius search). Pick **one** of:

### Option A — Native local Postgres (no Docker)

Install and start Postgres + PostGIS once, then run the setup script:

```bash
# Debian/Ubuntu
sudo apt install -y postgresql postgresql-16-postgis-3
# macOS
brew install postgresql postgis && brew services start postgresql

# Create the role, database, and PostGIS extension (idempotent)
cd backend
make db            # or: ./scripts/setup_db.sh
```

The script prints the `DATABASE_URL` to copy into `backend/.env`.

### Option B — Hosted Postgres (no local install)

Use any managed Postgres that supports PostGIS (Neon, Supabase, Railway, RDS).
Create a database, enable PostGIS (`CREATE EXTENSION postgis;`), and set the
connection string in `backend/.env`:

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME
```

### Option C — Docker (optional)

`backend/docker-compose.yml` defines every service (api, db, redis,
celery_worker, nginx). Run them all, or just the infra you want:

```bash
cd backend
docker-compose up -d db redis   # just the datastores
# or `docker-compose up -d` for the full stack
```

## 3. Run the backend

```bash
cd backend
make install       # pip install -r requirements.txt
make dev           # uvicorn app.main:app --reload
```

Tables and the PostGIS extension are created automatically on startup
(`init_db`). Verify with:

```bash
curl localhost:8000/health/db     # {"status":"ok","database":"connected"}
```

## 4. Background services (Redis + Celery)

Redis is the broker/result backend for the Celery worker. The API itself
does not require Redis to serve requests, so this is only needed when you
run background tasks. Pick **one**, no Docker required:

### Redis — native

```bash
# Debian/Ubuntu
sudo apt install -y redis-server && sudo service redis-server start
# macOS
brew install redis && brew services start redis

redis-cli ping                    # PONG   (or: make redis to run it foreground)
```

### Redis — hosted

Use any managed Redis (Upstash, Redis Cloud, Elasticache) and set in
`backend/.env`:

```
REDIS_URL=rediss://USER:PASSWORD@HOST:6379/0
```

### Celery worker (native)

With Redis reachable via `REDIS_URL`:

```bash
cd backend
make worker        # celery -A app.workers.celery_app worker --loglevel=info
```

## 5. Deploy Home Assistant Node

On your Raspberry Pi 4:
1. Flash Home Assistant OS: https://www.home-assistant.io/installation/raspberrypi
2. Copy `ha-config/` files to your HA config directory (`/config/`)
3. Edit `secrets.yaml` with your hub-specific values
4. Install required add-ons: Mosquitto, Node-RED, MariaDB
5. Restart Home Assistant

## 6. Build Flutter App

```bash
cd mobile
flutter pub get
flutter build apk --release  # Android
flutter build ios --release  # iOS
```

## 7. Configure Nginx (production)

For local development the API is reached directly at `localhost:8000`, so
Nginx is not required. For production, run native Nginx (no Docker):

```bash
sudo apt install -y nginx                         # or: brew install nginx
sudo cp infrastructure/nginx/nginx.conf /etc/nginx/conf.d/safer-ci.conf
sudo certbot --nginx -d api.safer-ci.app
sudo nginx -s reload
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

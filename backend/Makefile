.PHONY: install db redis dev worker lint

# Install backend dependencies
install:
	pip install -r requirements.txt

# Create local Postgres role/db + PostGIS extension (no Docker needed)
db:
	./scripts/setup_db.sh

# Start a local Redis server in the foreground (no Docker needed).
# Install once: `apt install redis-server` or `brew install redis`.
redis:
	redis-server

# Run the API with autoreload (expects backend/.env)
dev:
	uvicorn app.main:app --reload

# Run a Celery worker against REDIS_URL (expects Redis running)
worker:
	celery -A app.workers.celery_app worker --loglevel=info

# Lint
lint:
	pylint app

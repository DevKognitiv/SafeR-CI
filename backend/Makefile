.PHONY: install db dev lint

# Install backend dependencies
install:
	pip install -r requirements.txt

# Create local Postgres role/db + PostGIS extension (no Docker needed)
db:
	./scripts/setup_db.sh

# Run the API with autoreload (expects backend/.env)
dev:
	uvicorn app.main:app --reload

# Lint
lint:
	pylint app

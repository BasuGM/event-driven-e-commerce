COMPOSE := docker compose
BACKEND := $(COMPOSE) exec backend
FRONTEND := $(COMPOSE) exec frontend
DB := $(COMPOSE) exec -T db
# Read DB credentials from .env so the Makefile and containers agree
include .env
export

.PHONY: up down reset migrate seed seed-large snapshot restore test test-backend test-frontend types

up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

reset:
	$(DB) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1 \
		-c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	$(MAKE) migrate
	$(MAKE) seed

migrate:
	$(BACKEND) python manage.py migrate --noinput

seed:
	$(BACKEND) python manage.py import_olist --size small
	$(BACKEND) python manage.py seed_dev_users

seed-large:
	$(BACKEND) python manage.py import_olist --size large
	$(BACKEND) python manage.py seed_dev_users

snapshot:
	$(DB) pg_dump -U $(POSTGRES_USER) -d $(POSTGRES_DB) -Fc \
		-f /snapshots/$(POSTGRES_DB)-$$(date +%Y%m%d-%H%M%S).dump
	@ls -1t data/snapshots/*.dump | head -1

restore:
	@latest=$$(ls -1t data/snapshots/*.dump 2>/dev/null | head -1); \
	if [ -z "$$latest" ]; then echo "No snapshot in data/snapshots/ — run 'make snapshot' first."; exit 1; fi; \
	echo "Restoring $$latest"; \
	$(DB) pg_restore -U $(POSTGRES_USER) -d $(POSTGRES_DB) --clean --if-exists --no-owner \
		/snapshots/$$(basename $$latest)

test: test-backend test-frontend

test-backend:
	$(BACKEND) pytest

test-frontend:
	$(FRONTEND) npm run test

types:
	$(COMPOSE) exec -T backend python manage.py spectacular --validate > frontend/src/lib/api/schema.yml
	$(FRONTEND) npm run types

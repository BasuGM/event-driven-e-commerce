COMPOSE := docker compose
BACKEND := $(COMPOSE) exec backend
FRONTEND := $(COMPOSE) exec frontend
DB := $(COMPOSE) exec -T db
# Read DB credentials from .env so the Makefile and containers agree.
# "-include" tolerates a missing file; require-env then fails with a helpful message.
-include .env
export

.PHONY: require-env up down reset migrate seed seed-large snapshot restore test test-backend test-frontend typecheck e2e types backfill-sales events-logs mail analytics-backfill replay replay-reset

require-env:
	@test -f .env || { echo "Missing .env. Run: cp .env.example .env"; exit 1; }

up: require-env
	# New npm deps reach the container via frontend/dev.sh (reinstalls when package-lock.json changes)
	$(COMPOSE) up -d --build --wait

down: require-env
	$(COMPOSE) down

reset: require-env
	$(DB) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1 \
		-c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	# Event streams (events:*, their consumer groups, the DLQ) describe the old data: drop them
	# too, or consumers replay old events against the fresh DB. Only those keys (Celery shares
	# the Redis DB). After DROP SCHEMA, so the relay is already waiting and can't refill them.
	$(BACKEND) python manage.py clear_event_streams
	$(MAKE) migrate
	$(MAKE) seed

migrate: require-env
	$(BACKEND) python manage.py migrate --noinput

seed: require-env
	$(BACKEND) python manage.py import_olist --size small
	$(BACKEND) python manage.py seed_dev_users
	$(BACKEND) python manage.py backfill_analytics

seed-large: require-env
	$(BACKEND) python manage.py import_olist --size large
	$(BACKEND) python manage.py seed_dev_users
	$(BACKEND) python manage.py backfill_analytics

# Rebuild the analytics projections from orders (the importer emits no events)
analytics-backfill: require-env
	$(BACKEND) python manage.py backfill_analytics

# Replay imported orders as live events. Override with e.g.
#   make replay ARGS="--from 2018-01-01 --to 2018-01-07 --speed 2 --limit 500"
REPLAY_ARGS ?= --from 2017-11-20 --to 2017-11-30 --speed 10
replay: require-env
	$(BACKEND) python manage.py replay_orders $(if $(ARGS),$(ARGS),$(REPLAY_ARGS))

replay-reset: require-env
	$(BACKEND) python manage.py replay_reset $(ARGS)

snapshot: require-env
	$(DB) pg_dump -U $(POSTGRES_USER) -d $(POSTGRES_DB) -Fc \
		-f /snapshots/$(POSTGRES_DB)-$$(date +%Y%m%d-%H%M%S).dump
	@ls -1t data/snapshots/*.dump | head -1

restore: require-env
	@latest=$$(ls -1t data/snapshots/*.dump 2>/dev/null | head -1); \
	if [ -z "$$latest" ]; then echo "No snapshot in data/snapshots/ — run 'make snapshot' first."; exit 1; fi; \
	echo "Restoring $$latest"; \
	$(DB) pg_restore -U $(POSTGRES_USER) -d $(POSTGRES_DB) --clean --if-exists --no-owner \
		/snapshots/$$(basename $$latest)

test: test-backend test-frontend typecheck

test-backend: require-env
	$(BACKEND) pytest

test-frontend: require-env
	$(FRONTEND) npm run test

typecheck: require-env
	$(FRONTEND) npx tsc --noEmit

# Playwright smoke test against the running, seeded stack (make up && make reset first)
e2e: require-env
	$(COMPOSE) --profile e2e run --rm e2e

# One-off: recount sales_count without canceled/unavailable orders (safe to re-run)
backfill-sales: require-env
	$(BACKEND) python manage.py backfill_sales_count

events-logs: require-env
	$(COMPOSE) logs -f relay consumers stream

mail: require-env
	@echo "Mailpit (every email the app sends): http://localhost:$${MAILPIT_HOST_PORT:-8025}"

types: require-env
	$(COMPOSE) exec -T backend python manage.py spectacular --validate > frontend/src/lib/api/schema.yml
	$(FRONTEND) npm run types

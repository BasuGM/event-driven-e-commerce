# Docker, Compose, Make and the shell scripts

Containers package each service; Compose wires them into one stack; Make gives that stack short
commands. Docker Engine + Compose v2 (the `docker compose` plugin; the e2e overrides need a recent Compose,
tested with v5.5.1, see the [runbook](../operations/runbook.md)), GNU Make, POSIX `sh`/Bash,
Mailpit v1.29.5. Official docs: [Docker Compose](https://docs.docker.com/compose/).

## Dockerfile with a cached dependency layer

Copying only the dependency list first means a code edit doesn't reinstall packages. The backend
image is `python:3.13-slim`; the frontend is `node:22-slim`.

```dockerfile
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .
```

Source: [backend/Dockerfile](../../backend/Dockerfile).

## One service, one env file

Every service reads the same `.env`, so the Makefile and the containers agree on credentials.
Host ports are variables with defaults, so a clash with another local service is a one-line fix;
containers always talk to each other on the default ports.

```yaml
  db:
    image: postgres:17
    env_file: .env
    ports:
      - "${DB_HOST_PORT:-5432}:5432"
```

Source: [docker-compose.yml](../../docker-compose.yml), service `db`.

## Bind mounts and named volumes

A bind mount (`./backend:/app`) puts host code in the container, so edits show up at once. Named
volumes hold data that must outlive a container: the database, Redis, Celery beat's schedule,
and the frontend's `node_modules` (named, not anonymous, so restarts reuse them).

```yaml
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
      - frontend_next:/app/.next
```

Source: [docker-compose.yml](../../docker-compose.yml), service `frontend`.

## One image, many commands

The backend image runs six different processes; only `command` differs. That is how the web
server, Celery worker, beat, event relay, consumers and the SSE stream share one codebase.

```yaml
  relay:
    build: ./backend
    command: python manage.py run_relay
  consumers:
    build: ./backend
    command: python manage.py run_consumers
```

Source: [docker-compose.yml](../../docker-compose.yml), services `relay` and `consumers`
(abridged). More: [architecture](../architecture.md).

## Healthchecks and start order

A healthcheck is a command Compose runs to decide when a container is ready. `depends_on` with
`condition: service_healthy` makes dependants wait for it, so Django never starts before
Postgres accepts connections.

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
    …
    depends_on:
      db:
        condition: service_healthy
```

Source: [docker-compose.yml](../../docker-compose.yml), services `db` and `backend`.

## Graceful stop

`stop_grace_period` gives a container time to react to SIGTERM before Docker kills it. The relay
and the consumers use it to finish the batch they are on.

```yaml
    command: python manage.py run_consumers
    stop_grace_period: 20s
```

Source: [docker-compose.yml](../../docker-compose.yml), service `consumers`.

## Compose profiles

A service with a `profiles` entry is not started by a plain `up`. The Playwright container only
runs under `make e2e`.

```yaml
  e2e:
    image: mcr.microsoft.com/playwright:v1.63.0-noble
    profiles: ["e2e"]
```

Source: [docker-compose.yml](../../docker-compose.yml), service `e2e`. More:
[testing](../testing.md).

## Entry-point script

`frontend/dev.sh` reinstalls npm packages into the named volume only when `package-lock.json`
changed, because a rebuilt image doesn't refresh a volume that already exists.

```sh
hash=$(sha1sum package-lock.json | cut -d' ' -f1)
if [ "$(cat node_modules/.lock-hash 2>/dev/null)" != "$hash" ]; then
  npm ci --no-audit --no-fund
  echo "$hash" > node_modules/.lock-hash
fi
exec npm run dev
```

Source: [frontend/dev.sh](../../frontend/dev.sh).

## Makefile as a task runner

`.PHONY` targets are commands, not files. `-include .env` plus `export` hands the settings to
every recipe, and a `require-env` prerequisite fails early with a clear message when `.env` is
missing. `exec` variables hold the command prefix once.

```make
BACKEND := $(COMPOSE) exec backend
-include .env
export

require-env:
	@test -f .env || { echo "Missing .env. Run: cp .env.example .env"; exit 1; }

migrate: require-env
	$(BACKEND) python manage.py migrate --noinput
```

Source: [Makefile](../../Makefile), targets `require-env` and `migrate`.

## Composite targets and shell inside recipes

A target can just list other targets (`test`). Inside a recipe `$$` escapes `$` so the shell sees
its own variables; `snapshot` and `restore` use it for timestamps and the newest dump.

```make
test: test-backend test-frontend typecheck

snapshot: require-env
	$(DB) pg_dump -U $(POSTGRES_USER) -d $(POSTGRES_DB) -Fc \
		-f /snapshots/$(POSTGRES_DB)-$$(date +%Y%m%d-%H%M%S).dump
```

Source: [Makefile](../../Makefile), targets `test` and `snapshot`.

## Redirecting command output into a file

`make types` writes the OpenAPI schema straight into the frontend tree, then regenerates the
TypeScript types from it.

```make
types: require-env
	$(COMPOSE) exec -T backend python manage.py spectacular --validate > frontend/src/lib/api/schema.yml
	$(FRONTEND) npm run types
```

Source: [Makefile](../../Makefile), target `types`. More: [drf-and-openapi](drf-and-openapi.md).

## Mailpit (dev SMTP sink)

Mailpit accepts SMTP on 1025 and shows every message in a web UI. The app's `MAILERS` setting
points at it by service name.

```yaml
  mailpit:
    image: axllent/mailpit:v1.29.5
    ports:
      - "${MAILPIT_HOST_PORT:-8025}:8025"
```

Source: [docker-compose.yml](../../docker-compose.yml), service `mailpit`. More:
[notifications](../flows/notifications.md).

## Compose override files

`-f base -f override` merges two files. The e2e override clears published ports (`!reset`),
replaces volumes (`!override`) and moves Postgres to `tmpfs`, so each run starts empty.

```yaml
  db:
    ports: !reset []
    environment:
      POSTGRES_DB: ecommerce_e2e
    volumes: !override []
    tmpfs:
      - /var/lib/postgresql/data
```

Source: [docker-compose.e2e.yml](../../docker-compose.e2e.yml), service `db`. The same file uses
a YAML anchor (`&e2e-django-env`) shared by every Django service.

## Compose project names: an isolated stack

`-p` gives a second copy of the stack its own containers, network and volumes. The script
refuses to run under any other project name.

```sh
dc() { docker compose -p "$PROJECT" $FILES "$@"; }
…
if [ "$PROJECT" != "$EXPECTED_PROJECT" ]; then
  echo "e2e: refusing to run against compose project '$PROJECT' …" >&2
  exit 2
fi
```

Source: [scripts/e2e.sh](../../scripts/e2e.sh). More: [lab](../concepts/lab.md).

## Inspecting the merged config as a guard

`docker compose config --format json` prints the merged result; the script checks every Django
service points at `ecommerce_e2e` before anything starts. The command's status is captured
first because plain `sh` has no `pipefail`.

```sh
config_json=$(dc config --format json) || fail "docker compose config failed"
printf '%s' "$config_json" | python3 -c '
…
' "$EXPECTED_DB" "$DJANGO_SERVICES" || fail "a Django service would not use $EXPECTED_DB on db"
```

Source: [scripts/e2e.sh](../../scripts/e2e.sh).

## `trap` and an atomic `mkdir` lock

`mkdir` either creates the directory or fails, atomically, so it works as a lock without `flock`
(absent on macOS). The lock stores the PID, and a dead PID is a stale lock. A `trap` releases
it and tears the stack down however the script ends.

```sh
if ! mkdir "$LOCK" 2>/dev/null; then
  holder=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    refuse "another e2e run (pid $holder) holds the $PROJECT project. …"
  fi
  …
fi
…
trap cleanup EXIT
trap 'exit 130' INT TERM
```

Source: [scripts/e2e.sh](../../scripts/e2e.sh). More: [testing](../testing.md).

## Not used here

- Docker Swarm, Kubernetes, multi-stage builds: the images are dev images; production hosting is
  out of scope (see "Before deploying" in `CLAUDE.md`).
- Compose `restart:` policies and `networks:` blocks: the default network is enough.
- Make pattern rules and file-based targets: every target is a command.

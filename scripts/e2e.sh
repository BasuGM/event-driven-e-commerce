#!/bin/sh
# `make e2e`: Playwright against an isolated, freshly seeded stack, never the dev stack.
#
# The e2e stack is a second compose project (ecommerce-e2e) from the same docker-compose.yml plus
# docker-compose.e2e.yml: its own containers, network, database (ecommerce_e2e, on tmpfs),
# Redis and Mailpit, and no host ports. Before anything writes, the script checks, statically and
# then live on every Django service, that the database it would use is the e2e one.
#
#   make e2e                       all specs        make e2e ARGS="e2e/shop.spec.ts"
#   KEEP_E2E=1 make e2e            leave the stack up (frontend on http://localhost:3101)
#   make e2e-down                  remove a kept stack
set -u

PROJECT="${E2E_PROJECT:-ecommerce-e2e}"
EXPECTED_PROJECT="ecommerce-e2e"
EXPECTED_DB="ecommerce_e2e"
DJANGO_SERVICES="backend worker beat relay consumers stream"

cd "$(dirname "$0")/.."

# Guard 0: only ever the e2e project (never the dev project, whatever the environment says)
if [ "$PROJECT" != "$EXPECTED_PROJECT" ]; then
  echo "e2e: refusing to run against compose project '$PROJECT' (expected '$EXPECTED_PROJECT')." >&2
  exit 2
fi

FILES="-f docker-compose.yml -f docker-compose.e2e.yml"
if [ "${KEEP_E2E:-}" = "1" ]; then
  FILES="$FILES -f docker-compose.e2e-keep.yml"
fi
dc() { docker compose -p "$PROJECT" $FILES "$@"; }

# One run at a time: a second run's first step (`down`) would tear down the first run's stack.
# Lock = an atomic mkdir in e2e-results/ holding the owner's PID (macOS has no flock); a lock
# whose PID is gone is stale and taken over. Checked BEFORE the cleanup trap is installed, so a
# refused run never touches the other run's containers.
LOCK="e2e-results/.e2e-lock"
mkdir -p e2e-results
refuse() { echo "e2e: REFUSED: $*" >&2; exit 4; }
if ! mkdir "$LOCK" 2>/dev/null; then
  holder=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    refuse "another e2e run (pid $holder) holds the $PROJECT project. Wait for it to finish, or stop it first."
  fi
  echo "e2e: removing a stale lock (pid ${holder:-unknown} is gone)"
  rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null || refuse "another e2e run took the lock just now."
fi
echo $$ > "$LOCK/pid"
release_lock() { [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ] && rm -rf "$LOCK"; }
# No lock holder, but containers are up: a kept stack (KEEP_E2E=1) or a run started by an older
# version of this script. Don't tear it down from here.
if [ -n "$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT")" ]; then
  release_lock
  refuse "containers of the $PROJECT project are already running (a kept stack, or another run). Remove them with 'make e2e-down' first."
fi

started=$(date +%s)
phase() { echo "e2e: [$(( $(date +%s) - started ))s] $*"; }

cleanup() {
  rc=$?
  if [ "${KEEP_E2E:-}" = "1" ]; then
    phase "KEEP_E2E=1: stack left running at http://localhost:3101 (make e2e-down removes it)"
  else
    phase "tearing down the e2e stack"
    dc --profile e2e down --remove-orphans >/dev/null 2>&1
  fi
  release_lock
  phase "done, exit $rc"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

fail() { echo "e2e: ABORT: $*" >&2; exit 3; }

# Guard 1 (static, before any container starts): what every Django service would be given
phase "static check of the merged compose config"
dc config --format json | python3 -c '
import json, sys
expected_db, services = sys.argv[1], sys.argv[2].split()
config = json.load(sys.stdin)["services"]
bad = []
for name in services:
    env = config[name].get("environment") or {}
    db, host = env.get("POSTGRES_DB"), env.get("POSTGRES_HOST")
    ok = db == expected_db and host == "db"
    mark = "ok" if ok else "MISMATCH"
    print(f"  static  {name:<10} POSTGRES_DB={db} POSTGRES_HOST={host}  {mark}")
    if not ok:
        bad.append(name)
sys.exit(1 if bad else 0)
' "$EXPECTED_DB" "$DJANGO_SERVICES" || fail "a Django service would not use $EXPECTED_DB on db"

# Clean start: recreate the containers (tmpfs database and Redis start empty); keep the
# frontend/e2e node_modules and .next volumes for speed
dc --profile e2e down --remove-orphans >/dev/null 2>&1

# Guard 2 (live): ask a running Django service what it is configured with and where its
# connection actually landed, and compare with the e2e db container's address
db_ip() {
  docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(dc ps -q db)"
}
live_guard() {
  service=$1
  expected_ip=$(db_ip)
  line=$(dc exec -T "$service" python manage.py shell -c '
from django.conf import settings
from django.db import connection
cfg = settings.DATABASES["default"]
with connection.cursor() as c:
    c.execute("SELECT current_database(), host(inet_server_addr())")
    current, addr = c.fetchone()
print(cfg["NAME"], cfg["HOST"], current, addr)
' 2>/dev/null | tail -1)
  set -- $line
  name=${1:-?} host=${2:-?} current=${3:-?} addr=${4:-?}
  if [ "$name" = "$EXPECTED_DB" ] && [ "$host" = "db" ] && [ "$current" = "$EXPECTED_DB" ] && [ "$addr" = "$expected_ip" ]; then
    echo "  live    $service: NAME=$name HOST=$host current_database()=$current server=$addr (e2e db $expected_ip)  ok"
  else
    echo "  live    $service: NAME=$name HOST=$host current_database()=$current server=$addr (e2e db $expected_ip)  MISMATCH" >&2
    fail "$service is not connected to the e2e database"
  fi
}

phase "starting db, redis, mailpit, backend"
dc up -d --build --wait db redis mailpit backend >/dev/null 2>&1 || fail "could not start db/redis/mailpit/backend"
live_guard backend

phase "starting worker, beat, relay, consumers, stream, frontend"
dc up -d --build --wait worker beat relay consumers stream frontend >/dev/null 2>&1 || fail "could not start the other services"
for service in worker beat relay consumers stream; do
  live_guard "$service"
done

phase "migrate + seed (small) in the e2e database"
dc exec -T backend python manage.py migrate --noinput >/dev/null || fail "migrate failed"
dc exec -T backend python manage.py import_olist --size small | tail -2 || fail "import failed"
dc exec -T backend python manage.py seed_dev_users >/dev/null || fail "seed_dev_users failed"
dc exec -T backend python manage.py backfill_analytics >/dev/null || fail "backfill_analytics failed"

# The frontend installs its dependencies on first use of its volume, then compiles routes on
# first visit: wait until the home page answers (this also warms it up)
phase "waiting for the frontend"
tries=0
until dc exec -T backend python -c 'import urllib.request; urllib.request.urlopen("http://frontend:3000/", timeout=60)' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [ "$tries" -ge 60 ] && fail "frontend did not answer within 10 minutes"
  sleep 10
done

# Warm every route the specs enter: the dev server compiles a route on its first request, which
# on this cold, second stack can outlast a spec's retry window. Any HTTP answer counts (anonymous
# /cart, /checkout, /orders redirect to /login; /staff/* render the neutral not-found page): the
# route is compiled either way.
phase "warming routes"
dc exec -T backend python manage.py shell -c '
import time, urllib.error, urllib.request
from apps.catalog.models import Product
slug = Product.objects.filter(min_price__isnull=False).order_by("-sales_count", "id").values_list("slug", flat=True).first()
paths = ["/login", "/shop", f"/shop/{slug}", "/cart", "/checkout", "/orders",
         "/staff/events", "/staff/health", "/staff/analytics"]
for path in paths:
    started = time.monotonic()
    for attempt in range(10):
        try:
            status = urllib.request.urlopen("http://frontend:3000" + path, timeout=180).status
        except urllib.error.HTTPError as exc:
            status = exc.code  # an error page still means the route compiled
        except Exception as exc:  # timeout / connection reset: try again
            print(f"  warm    {path}: {type(exc).__name__}, retrying", flush=True)
            time.sleep(5)
            continue
        print(f"  warm    {path}: HTTP {status} in {time.monotonic() - started:.1f}s", flush=True)
        break
    else:
        raise SystemExit(f"could not warm {path}")
' || fail "warming the routes failed"

phase "running Playwright"
status=0
if [ "$#" -gt 0 ]; then
  dc --profile e2e run --rm e2e sh e2e/run.sh "$@" || status=$?
else
  dc --profile e2e run --rm e2e || status=$?
fi
phase "Playwright exited with $status"
if [ "$status" -ne 0 ]; then
  # The containers are removed on exit: keep their logs next to the Playwright traces
  logs="e2e-results/logs-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$logs"
  for service in frontend backend stream; do
    dc logs --no-color --timestamps "$service" > "$logs/$service.log" 2>&1
  done
  phase "saved frontend/backend/stream logs to $logs"
fi
exit "$status"

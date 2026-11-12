#!/bin/sh
# `make screenshots`: regenerate the README screenshots (docs/images/*.png) with Playwright.
#
# Runs ONLY against the lab stack (compose project ecommerce-e2e, started by `make lab-up`): the
# script creates data (orders, payments, a replay) and refuses to run unless that stack is up
# and its Django services are connected to the database ecommerce_e2e. It never talks to the dev
# stack: every docker compose call below names the ecommerce-e2e project, and the Playwright
# config refuses any BASE_URL other than http://frontend:3000 (the lab's frontend, on the lab's
# network).
#
#   make lab-up && make screenshots     then: make lab-down
set -u

PROJECT="ecommerce-e2e"
EXPECTED_DB="ecommerce_e2e"
DJANGO_SERVICES="backend worker beat relay consumers stream"
NEEDED_SERVICES="db redis mailpit $DJANGO_SERVICES frontend"

cd "$(dirname "$0")/.."
dc() { docker compose -p "$PROJECT" -f docker-compose.yml -f docker-compose.e2e.yml -f docker-compose.e2e-keep.yml "$@"; }
fail() { echo "screenshots: REFUSED: $*" >&2; exit 3; }
phase() { echo "screenshots: $*"; }

# Guard 1: a `make e2e` run owns the stack (and is about to tear it down)
[ -d e2e-results/.e2e-lock ] && fail "an e2e run holds the lock (e2e-results/.e2e-lock). Wait for it, or use make lab-up afterwards."

# Guard 2: the lab stack is up: every service running
running=$(dc ps --status running --services 2>/dev/null)
for service in $NEEDED_SERVICES; do
  printf '%s\n' "$running" | grep -qx "$service" || fail "the lab stack is not up ($service is not running). Start it with: make lab-up"
done

# Guard 3 (live): every Django service is connected to the lab database, on the lab's db container
db_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(dc ps -q db)")
for service in $DJANGO_SERVICES; do
  out=$(dc exec -T "$service" python manage.py shell -c '
from django.conf import settings
from django.db import connection
cfg = settings.DATABASES["default"]
with connection.cursor() as c:
    c.execute("SELECT current_database(), host(inet_server_addr())")
    current, addr = c.fetchone()
print(cfg["NAME"], cfg["HOST"], current, addr)
' 2>/dev/null | tail -1)
  set -- $out
  if [ "${1:-?}" = "$EXPECTED_DB" ] && [ "${2:-?}" = "db" ] && [ "${3:-?}" = "$EXPECTED_DB" ] && [ "${4:-?}" = "$db_ip" ]; then
    echo "  live    $service: database $EXPECTED_DB on $db_ip  ok"
  else
    fail "$service is not connected to $EXPECTED_DB (got: ${out:-nothing})"
  fi
done

# Data the shots need: a short replay (imported orders re-enacted as live events), at full speed.
# Idempotent: a second run finds the copies and adds nothing.
phase "replay (Nov 2017, 40 orders) on the lab stack"
dc exec -T backend python manage.py replay_orders --from 2017-11-20 --to 2017-11-30 --speed 0 --limit 40 | tail -5 \
  || fail "the replay failed"

RAW="e2e-results/screenshots-raw"
rm -rf "$RAW"; mkdir -p "$RAW" docs/images
phase "Playwright (one browser session, ~3-4 min: a payment webhook is delayed 30 s)"
dc --profile screenshots run --rm screenshots || { echo "screenshots: Playwright failed (see e2e-results/screenshots-test-results/)" >&2; exit 1; }

# Optimise: pngquant in a throwaway container (nothing added to the repo's dependencies). A file
# pngquant can't shrink within the quality range is copied as it is.
phase "optimising PNGs with pngquant"
docker run --rm -v "$PWD/$RAW:/in:ro" -v "$PWD/docs/images:/out" alpine:3.20 sh -c '
  apk add --no-cache pngquant >/dev/null 2>&1 || { echo "could not install pngquant" >&2; exit 1; }
  for f in /in/*.png; do
    name=$(basename "$f")
    pngquant --quality=70-95 --speed 1 --strip --force --output "/out/$name" "$f" || cp "$f" "/out/$name"
  done
' || fail "pngquant step failed (raw shots are in $RAW)"

ls -l docs/images/*.png | awk '{ printf "  %7.0f KB  %s\n", $5/1024, $9 }'
big=$(find docs/images -name '*.png' -size +300k)
[ -n "$big" ] && echo "screenshots: WARNING: over 300 KB (crop to the viewport):" && echo "$big"
exit 0

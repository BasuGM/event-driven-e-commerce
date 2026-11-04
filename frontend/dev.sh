#!/bin/sh
# Entry point for the `frontend` compose service. node_modules is a named volume, so new npm
# dependencies don't arrive with a rebuilt image: reinstall only when package-lock.json changed.
set -e
cd /app
hash=$(sha1sum package-lock.json | cut -d' ' -f1)
if [ "$(cat node_modules/.lock-hash 2>/dev/null)" != "$hash" ]; then
  npm ci --no-audit --no-fund
  echo "$hash" > node_modules/.lock-hash
fi
exec npm run dev

#!/bin/sh
# Entry point for the `e2e` compose service (Playwright image). Installs the frontend's
# dependencies into a Linux-only volume, but only when package-lock.json has changed.
set -e
cd /app
hash=$(sha1sum package-lock.json | cut -d' ' -f1)
if [ "$(cat node_modules/.lock-hash 2>/dev/null)" != "$hash" ]; then
  npm ci --no-audit --no-fund
  echo "$hash" > node_modules/.lock-hash
fi
exec npx playwright test "$@"

#!/bin/sh
# Entry point of the `screenshots` compose service (Playwright image), run by scripts/screenshots.sh.
set -e
cd /app
hash=$(sha1sum package-lock.json | cut -d' ' -f1)
if [ "$(cat node_modules/.lock-hash 2>/dev/null)" != "$hash" ]; then
  npm ci --no-audit --no-fund
  echo "$hash" > node_modules/.lock-hash
fi
exec npx playwright test -c screenshots/playwright.config.ts "$@"

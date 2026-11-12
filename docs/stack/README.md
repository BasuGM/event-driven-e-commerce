# Stack quick reference

One page per technology, listing the concepts **this project actually uses**: each with a short
snippet copied from the repo, a link to its file and symbol, and a sentence on why it is there.
Where a concept has an in-depth write-up, the page ends the entry with a "More:" link. Each
page closes with a "Not used here" list.

For tutorials that teach the underlying ideas (transactions, locks, idempotency, delivery
guarantees, Redis Streams, and more), with exercises, see [docs/concepts/](../concepts/README.md).
For what the system does, see [architecture](../architecture.md), the [flows](../flows/) and the
[ADRs](../adr/README.md).

## Pages

| Page | Covers |
|---|---|
| [docker-and-make](docker-and-make.md) | Dockerfiles, Compose, Makefile, the e2e shell scripts, Mailpit |
| [postgresql](postgresql.md) | constraints, locks, upserts, full-text search, set-based SQL |
| [redis](redis.md) | Streams, consumer groups, Pub/Sub, persistence, the Celery broker |
| [python](python.md) | the language and standard-library features the backend uses |
| [django](django.md) | models, migrations, ORM, admin, sessions, templates, mail, ASGI |
| [drf-and-openapi](drf-and-openapi.md) | the API contract end to end: DRF, drf-spectacular, openapi-typescript/fetch, zod, react-hook-form |
| [celery-and-asgi](celery-and-asgi.md) | Celery tasks and beat; uvicorn and server-sent events |
| [nextjs](nextjs.md) | App Router, caching, route handlers, the API proxy |
| [react-and-typescript](react-and-typescript.md) | hooks, hydration, types |
| [ui](ui.md) | Tailwind 4, shadcn/ui, Radix, next-themes, lucide, react-day-picker, Recharts |
| [frontend-testing](frontend-testing.md) | Vitest, Testing Library, Playwright |
| [backend-testing](backend-testing.md) | pytest, pytest-django |

## Versions

| Technology | Version | Where it is pinned |
|---|---|---|
| Python | 3.13 | [backend/Dockerfile](../../backend/Dockerfile) |
| Django | 6.1.2 | [backend/requirements.txt](../../backend/requirements.txt) |
| Django REST Framework | 3.18.3 | requirements.txt |
| drf-spectacular | 0.30.0 | requirements.txt |
| psycopg | 3.3.6 | requirements.txt |
| Celery | 5.6.3 | requirements.txt |
| redis-py | 6.4.0 | requirements.txt (the newest Celery's transport allows) |
| uvicorn | 0.54.0 | requirements.txt |
| pytest / pytest-django | 9.1.1 / 4.14.0 | [backend/requirements-dev.txt](../../backend/requirements-dev.txt) |
| PostgreSQL | 17 | [docker-compose.yml](../../docker-compose.yml) |
| Redis server | 7 | docker-compose.yml |
| Mailpit | v1.29.5 | docker-compose.yml |
| Node.js | 22 | [frontend/Dockerfile](../../frontend/Dockerfile) |
| Next.js | 16.4.2 | [frontend/package.json](../../frontend/package.json) |
| React | 19.3.0 | package.json |
| TypeScript | 5.9.3 | package-lock.json |
| Tailwind CSS | 4.3.3 | package-lock.json |
| shadcn CLI / radix-ui | 4.21.4 / 1.7.0 | package-lock.json |
| Recharts | 3.8.0 | package-lock.json |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 | package-lock.json |
| zod / react-hook-form | 4.6.5 / 7.89.0 | package-lock.json |
| next-themes / lucide-react | 0.4.6 / 1.54.0 | package-lock.json |
| react-day-picker | 10.0.2 | package-lock.json |
| Vitest | 5.0.3 | package-lock.json |
| Testing Library (react) | 16.3.3 | package-lock.json |
| Playwright | 1.63.0 | package.json (and the image tag in docker-compose.yml) |

Ranges in `package.json` (`^`) resolve to the versions above through `package-lock.json`.

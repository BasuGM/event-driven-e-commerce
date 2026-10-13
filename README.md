# Event-driven e-commerce

A learning/portfolio e-commerce platform built around events: Django + DRF backend, Next.js
frontend, PostgreSQL and Redis, all run with Docker Compose. It is seeded with the real
[Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
so there is realistic data from day one.

## Prerequisites

- Docker with Docker Compose v2
- Node.js 22+ (only needed to run frontend tooling outside the containers)
- `make`

## Olist data

Download "Brazilian E-Commerce Public Dataset by Olist" from Kaggle (link above), unzip it and
put the CSVs **directly** in `data/olist/` (e.g. `data/olist/olist_orders_dataset.csv`). The
folder is gitignored. The geolocation CSV is not used yet.

## Setup

```sh
cp .env.example .env   # adjust host ports here if 5432/6379/8000/3000 are taken
make up                # build and start db, redis, backend, frontend
make reset             # create the schema, import ~2,000 orders, create dev users
```

`make seed-large` imports the full dataset (~1 minute). `make test` runs all tests. See
`CLAUDE.md` for the full command list and project conventions.

## URLs (default ports)

| What              | URL                              |
|-------------------|----------------------------------|
| Dashboard         | http://localhost:3000            |
| API docs (Swagger)| http://localhost:8000/api/docs/  |
| Django admin      | http://localhost:8000/admin/     |

## Dev login

`make reset` / `make seed` create three dev-only accounts: `admin` (superuser), `staff` and
`customer`. The password is `DEV_USER_PASSWORD` from `.env` (default `devpass123`).

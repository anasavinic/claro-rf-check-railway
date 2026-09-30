# Claro RF Check

Django application for Claro RF checks, structured like [BRSC Core Connect](https://gitlab.com/inatel-rd/brsc-core-connect).

The UI, user-facing messages, and documentation are in English. Domain terms from the Claro workbook (`EP`, sheet names, `CGI`, `Gerência`) stay as they appear in the source systems.

This copy is prepared for a Railway test deploy: one web service, Railway Postgres, and a volume at `/data`. Setup steps are in [docs/railway-test-deploy.md](docs/railway-test-deploy.md). Variable names are in `.env.railway.example`.

## Overview

| Item | Detail |
|------|--------|
| Language | Python 3.12 |
| Framework | Django + Django REST Framework |
| Database | PostgreSQL 14 |
| Task queue | Celery + Redis |
| Object storage | MinIO (local) / Huawei OBS (cloud) |
| Email (local) | Mailpit |
| Frontend | Django templates, Tailwind, HTMX, Alpine.js CSP |
| Containers | Docker Compose (`docker-compose.dev.yaml`) |
| Task runner | Invoke (`inv`) |

Application source lives in `code/`. Docker mounts that folder into the Django container at `/code`.

Host ports are offset from Core Connect so both stacks can run on the same machine. Container and volume names are prefixed with `claro_rf_check`.

## Architecture

| Service | Container | Host port | Description |
|---------|-----------|-----------|-------------|
| Django | `claro_rf_check` | http://localhost:8007 | Main application |
| MkDocs | `claro_rf_check_mkdocs` | http://localhost:8008 | Documentation |
| Mailpit | `claro_rf_check_mailpit` | http://localhost:8027 | Captured local email (SMTP `:1027`) |
| PostgreSQL | `claro_rf_check_postgres` | `5434` | Database |
| Redis | `claro_rf_check_redis` | `6381` | Celery broker / cache |
| MinIO | `claro_rf_check_minio` | http://localhost:9120 API / http://localhost:9121 console | S3-compatible object storage |
| Celery worker | `claro_rf_check_celery` | — | Background tasks |
| Celery beat | `claro_rf_check_celery_beat` | — | Scheduled tasks |
| Flower | `claro_rf_check_flower` | http://localhost:8009 | Celery monitoring |
| pgAdmin | `claro_rf_check_pgadmin` | http://localhost:50525 | Database admin UI |
| Portainer | `claro_rf_check_portainer` | http://localhost:9002 | Docker management UI |
| VS Code debug | — | `5682` | debugpy attach port |

`GET /healthz` is the unauthenticated liveness probe (no database). `GET /readyz` is readiness (200 when the database answers, otherwise 503). EP imports require a signed-in user; results are visible to the owner or staff.

## Quick start

```bash
cd D:/Projects/claro-rf-check-railway
python3.12 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r dev-requirements.txt
cp .env.dev.example .env.dev   # fill in SECRET_KEY
cp .env.dev .env
pre-commit install
inv docker.build
inv docker.run --daemon --no-tailwind
inv django.migrate
```

Open http://localhost:8007.

Tailwind is watched on the host by `inv docker.run` unless `--no-tailwind` is set. You do not need Node.js on the host for the standard Docker workflow; Node is installed in the image and used when the production image builds static files.

## Compose files

| File | Purpose |
|------|---------|
| `docker-compose.base.yaml` | Shared Django image defaults (`extends` only) |
| `docker-compose.yaml` | Networks and named volumes |
| `docker-compose.dev.yaml` | Local stack (MinIO, Mailpit, pgAdmin, Flower, MkDocs) |
| `docker-compose.staging.yaml` | Django (gunicorn) + Celery + Postgres + Redis, `prod` image target |
| `docker-compose.prod.app.yaml` | Production app + Redis + Celery |
| `docker-compose.prod.db.yaml` | Production Postgres on a separate host |

Local `inv` commands use `docker-compose.dev.yaml` and `.env.dev`. Staging and production are started with those compose files directly.

## Environment

`.env.dev.example` follows the Core Connect contract (`SECRET_KEY`, `ALLOWED_HOSTS`, `USE_OBS_MEDIA`, Mailpit). Do not copy OAuth, iTeam, or Kanban variables — those belong to Core Connect.

EP uploads use MinIO when `USE_OBS_MEDIA=True`. Local Docker must set `OBS_ADDRESSING_STYLE=path` (virtual hosting cannot resolve `bucket.minio`). Staging/prod OBS keeps `virtual`. Tests and CI force filesystem storage (`claro_rf_check.settings.ci`).

## Invoke tasks

```bash
inv --list
inv docker.build
inv docker.run --daemon --no-tailwind
inv docker.down
inv django.migrate
inv django.makemigrations
inv database.backup
inv database.restore --file-name backup_YYYYMMDD_HHMMSS.bkp
inv cache.clear
inv lint
inv test
```

`inv db.*` is an alias of `inv database.*`.

## Project structure

```
claro-rf-check/
├── code/
│   ├── claro_rf_check/   # settings, healthz, S3 storage
│   ├── home/
│   ├── ep_import/
│   └── theme/
├── docs/
├── tasks/
├── docker-compose.*.yaml
├── Dockerfile
└── requirements*.txt
```

SSO against Core Connect is not part of this application yet.

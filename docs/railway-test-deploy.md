# Railway test deployment

This copy deploys as one Django web service, a private Railway PostgreSQL database, and one volume mounted at `/data`. Do not add Celery, Redis, MinIO, or a public database endpoint.

Imports and checks run in background threads inside the web process. Keep the service at one replica so those threads and the upload files stay on the same machine.

## Railway setup

1. Create a Railway project and deploy this repository with the Dockerfile builder (`railway.json` already selects it).
2. Add PostgreSQL, then create the database reference variables shown in `.env.railway.example`.
3. Set `GITLAB_PYPI_TOKEN` before the first build. The image installs `core-connect-sso` from the GitLab Package Registry (project `84791364`). Use a token that can read that registry. Railway passes the variable into the Docker build because the Dockerfile declares `ARG GITLAB_PYPI_TOKEN`.
4. Attach one volume to the web service at `/data` and generate a public domain.
5. Set `DJANGO_ALLOWED_HOSTS` to that domain and `CSRF_TRUSTED_ORIGINS` to `https://` plus the same domain. Generate strong values for `DJANGO_SECRET_KEY`, the Basic auth pair, and the Django test user. Never commit them.
6. Confirm pre-deploy runs `migrate` and `ensure_test_user`, then open `/healthz` (no auth) and the site (Basic prompt, then `/accounts/login/`).

`RAILWAY_PUBLIC_DOMAIN` is added to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` when Railway injects it. Set the variables explicitly as well so the first boot is not waiting on that injection.

## What this deploy does not do

- Core Connect SSO is not used. Sign in with the local user from `CLARO_RF_TEST_USERNAME` / `CLARO_RF_TEST_PASSWORD`.
- Scheduled retention and stuck-job cleanup do not run, because there is no Celery beat.
- Failed tasks are not retried. The error is written to the service logs.
- Object storage is off. Uploaded workbooks stay on the volume under `/data/media`.

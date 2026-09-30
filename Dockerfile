# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /code

# Runtime essentials + Node (local dev image builds Tailwind on demand).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos '' app_user \
    && adduser --disabled-password --gecos '' celery_user

# ----
# Dev (local Compose). Railway does not build this stage.
# ----
FROM base AS dev

RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    nano \
    procps \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG CORE_CONNECT_SSO_PROJECT_ID=84791364
ARG GITLAB_PYPI_USER=gitlab-ci-token
ARG GITLAB_PYPI_TOKEN

COPY dev-requirements.txt /code/

RUN set -eu; \
    if [ -z "${GITLAB_PYPI_TOKEN}" ]; then \
      echo "GITLAB_PYPI_TOKEN is required to install core-connect-sso from the GitLab Package Registry." >&2; \
      exit 1; \
    fi; \
    pip install --upgrade pip; \
    PIP_EXTRA_INDEX_URL="https://${GITLAB_PYPI_USER}:${GITLAB_PYPI_TOKEN}@gitlab.com/api/v4/projects/${CORE_CONNECT_SSO_PROJECT_ID}/packages/pypi/simple" \
        pip install --no-cache-dir -r dev-requirements.txt

COPY ./code /code
ENV PYTHONPATH=/code

# ----
# Tailwind CSS. @source scans templates across the Django tree.
# ----
FROM node:22-bookworm-slim AS assets

WORKDIR /build/code/theme/static_src

COPY code/theme/static_src/package.json code/theme/static_src/package-lock.json ./
RUN npm ci

COPY code /build/code
RUN npm run build

# ----
# Python wheels, including the private core-connect-sso package.
# The GitLab token stays in this stage and is not copied into the runtime image.
# Railway injects GITLAB_PYPI_TOKEN when the service variable is declared as ARG.
# ----
FROM python:3.12-slim AS python-deps

ARG CORE_CONNECT_SSO_PROJECT_ID=84791364
ARG GITLAB_PYPI_USER=gitlab-ci-token
ARG GITLAB_PYPI_TOKEN

COPY requirements.txt /tmp/requirements.txt

RUN set -eu; \
    pip install --upgrade pip; \
    if [ -z "${GITLAB_PYPI_TOKEN}" ]; then \
      echo "GITLAB_PYPI_TOKEN is required to install core-connect-sso from the GitLab Package Registry." >&2; \
      exit 1; \
    fi; \
    pip wheel --wheel-dir /wheels -r /tmp/requirements.txt \
      --extra-index-url "https://${GITLAB_PYPI_USER}:${GITLAB_PYPI_TOKEN}@gitlab.com/api/v4/projects/${CORE_CONNECT_SSO_PROJECT_ID}/packages/pypi/simple"

# ----
# Railway runtime. This must stay the last stage: Railway builds the final target.
# ----
FROM python:3.12-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=claro_rf_check.settings.railway

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' app_user \
    && adduser --disabled-password --gecos '' celery_user

COPY requirements.txt /code/
COPY --from=python-deps /wheels /wheels
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY ./code /code
COPY --from=assets /build/code/theme/static /code/theme/static
COPY scripts/railway-entrypoint.sh /code/railway-entrypoint.sh
RUN chmod +x /code/railway-entrypoint.sh

# Static files are baked into the image. Uploads live on the Railway volume.
RUN DJANGO_SETTINGS_MODULE=claro_rf_check.settings.railway \
    DJANGO_SECRET_KEY=build-only-not-a-runtime-secret \
    DJANGO_ALLOWED_HOSTS=build.local \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["/code/railway-entrypoint.sh"]

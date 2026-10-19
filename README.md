# Claro RF Check

Claro RF Check is a Django-based web application for BRSC/Inatel Claro RF validation workflows: Engineering Parameters (EP) workbook import, Ger├¬ncia MML script generation (pre-check / full-check), command-return validation, and report export/email. The development environment runs entirely on **WSL (Windows Subsystem for Linux)** with **VS Code** as the default editor and **Docker CLI** (Docker Engine inside WSL) for application services.

The UI, user-facing messages, and documentation are in English. Domain terms from the Claro workbook (`EP`, sheet names, `CGI`, `Ger├¬ncia`) stay as they appear in the source systems.

This repository also builds a Windows executable (same approach as Vivo RF Check). See [docs/desktop-exe.md](docs/desktop-exe.md).

This copy is prepared for a Railway test deploy: one web service, Railway Postgres, and a volume at `/data`. Setup steps are in [docs/railway-test-deploy.md](docs/railway-test-deploy.md). Variable names are in `.env.railway.example`.

This README is the official guide for setting up the project from scratch. Follow the steps in order. For local WSL development, the [Environment variables](#7-environment-variables) section includes defaults that work without requesting secrets from the team (except a GitLab Personal Access Token for the private `core-connect-sso` package ÔÇö see [Updating dependencies](#18-updating-dependencies)).

## Table of contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Where to run commands](#where-to-run-commands)
- [1. Install and configure WSL](#1-install-and-configure-wsl)
- [2. Install dependencies inside WSL](#2-install-dependencies-inside-wsl)
- [3. Install and configure VS Code with WSL](#3-install-and-configure-vs-code-with-wsl)
- [4. Configure SSH access to GitLab](#4-configure-ssh-access-to-gitlab)
- [5. Clone the repository](#5-clone-the-repository)
- [6. Python virtual environment](#6-python-virtual-environment)
- [7. Environment variables](#7-environment-variables)
- [8. Pre-commit hooks](#8-pre-commit-hooks)
- [9. Docker stack](#9-docker-stack)
- [10. Database migrations](#10-database-migrations)
- [11. Tailwind CSS](#11-tailwind-css)
- [12. Create a superuser](#12-create-a-superuser)
- [13. Access the application](#13-access-the-application)
- [14. Running tests](#14-running-tests)
- [15. Linting and formatting](#15-linting-and-formatting)
- [16. Remote debugging with VS Code](#16-remote-debugging-with-vs-code)
- [17. Invoke tasks reference](#17-invoke-tasks-reference)
- [18. Updating dependencies](#18-updating-dependencies)
- [19. Database backup and restore](#19-database-backup-and-restore)
- [20. Application structure](#20-application-structure)
- [21. Troubleshooting](#21-troubleshooting)
- [22. FAQ](#22-faq)
- [23. Final validation checklist](#23-final-validation-checklist)
- [Additional documentation](#additional-documentation)

---

## Overview

| Item | Detail |
|------|--------|
| Language | Python 3.12 |
| Framework | Django + Django REST Framework |
| Database | PostgreSQL 14 |
| Task queue | Celery + Redis |
| Frontend | Django templates, HTMX, Alpine.js CSP, Tailwind CSS |
| Object storage | MinIO (local) / Huawei OBS (cloud) ÔÇö same S3-compatible contract |
| Email (local) | Mailpit |
| Auth | Core Connect SSO (`core-connect-sso`) + Django admin |
| Containers | Docker Compose (`docker-compose.dev.yaml`) |
| Task runner | [Invoke](https://www.pyinvoke.org/) (`inv`) |
| Repository | [gitlab.com/inatel-rd/claro-rf-check](https://gitlab.com/inatel-rd/claro-rf-check) |

The application source code lives in the `code/` directory. Docker mounts this folder into the Django-based containers at `/code`.

Host ports, container names, and volumes are offset/prefixed from Core Connect and Audit Mail so multiple BRSC projects can run at the same time on one machine.

`GET /healthz` is the unauthenticated liveness probe (no database). `GET /readyz` is readiness (200 when the database answers, otherwise 503).

---

## Architecture

Development services started by Docker Compose:

| Service | Container | Host port | Description |
|---------|-----------|-----------|-------------|
| Django | `claro_rf_check` | [http://localhost:8007](http://localhost:8007) | Main application |
| MkDocs | `claro_rf_check_mkdocs` | [http://localhost:8008](http://localhost:8008) | Project documentation |
| Mailpit | `claro_rf_check_mailpit` | [http://localhost:8027](http://localhost:8027) | Captured local email UI (SMTP `:1027`) |
| PostgreSQL | `claro_rf_check_postgres` | `5434` | Database |
| Redis | `claro_rf_check_redis` | `6381` | Celery broker / cache |
| MinIO | `claro_rf_check_minio` | [http://localhost:9120](http://localhost:9120) API / [http://localhost:9121](http://localhost:9121) console | S3-compatible object storage |
| Celery worker | `claro_rf_check_celery` | ÔÇö | Background tasks |
| Celery beat | `claro_rf_check_celery_beat` | ÔÇö | Scheduled tasks |
| Flower | `claro_rf_check_flower` | [http://localhost:8009](http://localhost:8009) | Celery monitoring |
| pgAdmin | `claro_rf_check_pgadmin` | [http://localhost:50525](http://localhost:50525) | Database admin UI |
| Portainer | `claro_rf_check_portainer` | [http://localhost:9002](http://localhost:9002) | Docker management UI |
| VS Code debug | `claro_rf_check` | `5682` | debugpy attach port |

> **Note:** Node.js is installed inside the Docker image (used by Tailwind). You do **not** need Node.js on WSL for the standard development workflow when CSS is built inside the container (see [step 11](#11-tailwind-css)).

Compose file layout:

| File | Purpose |
|------|---------|
| `docker-compose.base.yaml` | Shared Django image defaults (`extends` only) |
| `docker-compose.yaml` | Networks, named volumes, and BuildKit secrets |
| `docker-compose.dev.yaml` | Full local development stack |
| `docker-compose.staging.yaml` | Staging scaffolding (gunicorn + Celery + Postgres + Redis) |
| `docker-compose.prod.app.yaml` | Production app + Redis + Celery |
| `docker-compose.prod.db.yaml` | Production Postgres on a separate host |

Local Invoke commands use `docker-compose.dev.yaml` and `.env.dev`. Staging and production are started with those compose files directly.

---

## Prerequisites

Before starting, you need:

- Windows 10/11 with administrator access (to install WSL)
- **Ubuntu 24.04 LTS** as the WSL distro (recommended ÔÇö ships Python 3.12 in default repositories)
- A GitLab account with access to the [claro-rf-check](https://gitlab.com/inatel-rd/claro-rf-check) repository
- A GitLab Personal Access Token with `read_api` (and `read_registry` if required) to install `core-connect-sso` from the Package Registry ÔÇö see [step 18](#18-updating-dependencies)
- Values for optional secret environment variables ÔÇö request them from the project responsible if you need real Core Connect SSO against a shared IdP (local defaults work for offline/dev SSO)

---

## Where to run commands

Most setup mistakes come from running a command in the wrong place. Every shell block in this guide is meant for one of these contexts:

| Label | Where | Typical commands |
|-------|--------|------------------|
| **WSL** | Ubuntu terminal inside WSL (project under `~/projects/...`, not `/mnt/c/`) | `apt`, `git`, `docker`, `wsl` config, cloning |
| **venv** | Same WSL terminal **after** `source venv/bin/activate` (prompt shows `(venv)`) | `inv ÔÇª`, `pip`, `pre-commit`, `pytest`, `ruff` |
| **container** | Inside a running Docker container via `docker exec ÔÇª` | `manage.py migrate`, `tailwind`, `createsuperuser` |
| **Windows PowerShell** | Only when this guide says so (install/restart WSL) | `wsl --install`, `wsl --shutdown` |

Quick checks:

```bash
# WSL ÔÇö confirm you are on Linux, not PowerShell/CMD
uname -a

# venv ÔÇö must point at this project's venv
which python   # ÔÇª/claro-rf-check/venv/bin/python

# container ÔÇö Django app process
docker exec claro_rf_check python -c "import django; print(django.get_version())"
```

| Do this | Not this |
|---------|----------|
| `inv docker.*` / `inv django.*` / `inv test` from **venv** at the project root | Running `inv` without activating the venv |
| Tailwind / `manage.py` app commands via **`docker exec claro_rf_check ÔÇª`** | `python manage.py ÔÇª` on the WSL host for the running app |
| `docker` / `docker compose` from **WSL** | Docker Desktop or PowerShell for day-to-day compose |

Invoke tasks that talk to Compose still run on the **host venv**; they call Docker for you. You do not need to `docker exec` for `inv django.migrate`.

---

## 1. Install and configure WSL

All development work must happen **inside WSL**, not in the Windows filesystem (`C:\...`). Clone the repository and run Docker commands from the WSL terminal.

### Install WSL

#### Option A ÔÇö Quick install (recommended)

Open **PowerShell as Administrator** on Windows and run:

```powershell
wsl --install -d Ubuntu-24.04
```

This enables WSL, installs WSL 2, and sets up **Ubuntu 24.04 LTS**. **Restart your computer** when prompted.

> **Why 24.04?** Newer Ubuntu distros in the Microsoft Store may ship Python 3.14 by default and may not include Python 3.12 in the default apt repositories. Ubuntu 24.04 LTS avoids extra setup steps for Python.

After reboot, open the **Ubuntu 24.04** terminal from the Start menu and complete the initial user setup (username and password).

#### Option B ÔÇö Manual install (if Option A fails)

Some machines require enabling Windows features before WSL can be installed. Run in **PowerShell as Administrator**:

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

Restart your computer, then run:

```powershell
wsl --install --no-distribution
wsl --update
wsl --install -d Ubuntu-24.04
```

Restart again if prompted, then open Ubuntu and complete the initial user setup.

#### Verify WSL version

Ensure you are on WSL 2:

```powershell
wsl --set-default-version 2
wsl -l -v
```

The Ubuntu distro should show **VERSION 2**.

### Recommended WSL configuration

1. Open the Ubuntu terminal from the Start menu (or run `wsl` in PowerShell).
2. Create a Linux home directory structure for your projects:

```bash
mkdir -p ~/projects
cd ~/projects
```

3. Keep the project under the Linux filesystem (e.g. `~/projects/claro-rf-check`), **not** under `/mnt/c/`. File I/O and Docker volume performance are significantly better on the native Linux filesystem.

4. Enable **systemd** (required for the Docker service). Create or edit `/etc/wsl.conf`:

```bash
sudo tee /etc/wsl.conf > /dev/null <<'EOF'
[boot]
systemd=true
EOF
```

Optionally, set your default WSL user (replace `your_user` with your Linux username):

```bash
sudo tee -a /etc/wsl.conf > /dev/null <<'EOF'

[user]
default=your_user
EOF
```

> Do **not** add `command=service docker start` under `[boot]`. With `systemd=true`, Docker is managed by `systemctl` ÔÇö this is the recommended setup.

From **PowerShell on Windows**, restart WSL:

```powershell
wsl --shutdown
```

Then open the Ubuntu terminal again and confirm systemd is running:

```bash
systemctl --version
```

5. Update packages:

```bash
sudo apt update && sudo apt upgrade -y
```

---

## 2. Install dependencies inside WSL

Install the following tools **inside the WSL terminal**.

### Git

```bash
sudo apt install -y git
git --version
```

### Python 3.12

The project requires **Python 3.12** for the local virtual environment (matching the Docker image). This Python is used for Invoke, tests, linters, and pre-commit ÔÇö the Django app itself runs inside Docker.

Check what you already have **before** installing anything (WSL terminal):

```bash
python3.12 --version
command -v python3.12
command -v pyenv && pyenv versions
```

Expected for a usable install: `Python 3.12.x` and a path from `command -v python3.12`.

#### Option A ÔÇö Already available (apt, pyenv, or another manager)

If `python3.12 --version` already prints `3.12.x`, **skip Options BÔÇôD**. Do not install deadsnakes on top of a working pyenv (or other) install.

If you use [pyenv](https://github.com/pyenv/pyenv) and 3.12 is listed but not on `PATH`:

```bash
pyenv versions
# install only if 3.12.x is missing:
# pyenv install 3.12.8
pyenv local 3.12.8   # or: pyenv global 3.12.8
hash -r
python3.12 --version
which python3.12     # should be under ~/.pyenv/ÔÇª
```

Use that same `python3.12` in [step 6](#6-python-virtual-environment) (`python3.12 -m venv venv`). You do **not** need `python3.12-venv` from apt when pyenv provides the interpreter.

#### Option B ÔÇö Install from Ubuntu repositories (Ubuntu 24.04 LTS)

On Ubuntu 24.04, when `python3.12` is **not** already available:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
python3.12 --version
```

#### Option C ÔÇö Install via deadsnakes PPA (only if A/B do not apply)

Use this on **Ubuntu 26.04+** or when apt cannot find `python3.12` **and** you are **not** managing Python with pyenv. Prefer Option A (pyenv) if you already use it.

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
python3.12 --version
```

> **Important:** Do **not** use the system `python3` (e.g. 3.14) to create the virtual environment. Always use `python3.12` explicitly in [step 6](#6-python-virtual-environment).
>
> Do **not** mix pyenv and deadsnakes for the same version unless you know which binary `which python3.12` resolves to.

### Docker CLI (inside WSL)

Docker runs **natively inside WSL** via the Docker Engine. Do **not** use Docker Desktop ÔÇö install the Docker CLI and Docker Compose plugin directly in your WSL distro.

#### Remove conflicting packages

```bash
sudo apt-get remove -y docker.io docker-doc docker-compose podman-docker containerd runc
```

#### Install Docker Engine

Follow the [official Docker Engine install guide for Ubuntu](https://docs.docker.com/engine/install/ubuntu/):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Add your user to the `docker` group (avoids using `sudo` on every command):

```bash
sudo groupadd -f docker
sudo usermod -aG docker $USER
```

From **PowerShell on Windows**, restart WSL so the group change takes effect:

```powershell
wsl --shutdown
```

Open the Ubuntu terminal again, then enable and start Docker via systemd:

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

Verify Docker works **from inside WSL**:

```bash
docker --version
docker compose version
docker run --rm hello-world
sudo systemctl status docker
```

> All `docker` and `inv docker.*` commands must be run from the WSL terminal, not from PowerShell or CMD.

---

## 3. Install and configure VS Code with WSL

VS Code is the default editor for this project.

1. Install [Visual Studio Code](https://code.visualstudio.com/) on Windows.
2. Install the [**WSL** extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl) (`ms-vscode-remote.remote-wsl`).
3. Install the [**Python** extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) (`ms-python.python`).
4. Install the [**Docker** extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-docker) (optional, useful for container management).

Open the project in WSL:

```bash
cd ~/projects/claro-rf-check
code .
```

This opens VS Code connected to WSL. Confirm the green indicator in the bottom-left corner shows **WSL: Ubuntu** (or your distro name).

### Select the Python interpreter

1. Press `Ctrl+Shift+P` ÔåÆ **Python: Select Interpreter**.
2. Choose the interpreter from `./venv/bin/python` (after creating the virtual environment in [step 6](#6-python-virtual-environment)).

---

## 4. Configure SSH access to GitLab

SSH is required to clone the repository from GitLab.

### Generate an SSH key (skip if you already have one)

```bash
ssh-keygen -t ed25519 -C "your.email@example.com"
```

Press Enter to accept the default file location (`~/.ssh/id_ed25519`). Set a passphrase if desired.

### Add the key to the SSH agent

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### Register the public key on GitLab

```bash
cat ~/.ssh/id_ed25519.pub
```

Copy the output, then:

1. Go to [GitLab SSH Keys](https://gitlab.com/-/user_settings/ssh_keys).
2. Paste the public key and save.

### Test the connection

```bash
ssh -T git@gitlab.com
```

Expected response: `Welcome to GitLab, @your-username!`

---

## 5. Clone the repository

Clone **inside WSL**:

```bash
cd ~/projects
git clone git@gitlab.com:inatel-rd/claro-rf-check.git
cd claro-rf-check
```

---

## 6. Python virtual environment

**Context:** all commands in this section are **WSL**, then **venv** once activated. A local virtual environment is required to run Invoke tasks, tests, linters, and pre-commit hooks on the host (outside Docker).

Confirm Python 3.12 is available before proceeding:

```bash
# WSL
python3.12 --version
command -v pyenv && pyenv versions   # optional ÔÇö skip install if 3.12 is already here
```

If `python3.12` is missing, go back to [Python 3.12](#python-312): prefer an existing **pyenv** 3.12 (Option A), then apt (Option B), then deadsnakes (Option C) only if needed.

Remove any broken venv from a previous failed attempt:

```bash
rm -rf venv
```

Set GitLab Package Registry access (required to install `core-connect-sso` ÔÇö see [step 18](#18-updating-dependencies) for token creation):

```bash
export GITLAB_PYPI_TOKEN="token"
export PIP_EXTRA_INDEX_URL="https://__token__:${GITLAB_PYPI_TOKEN}@gitlab.com/api/v4/projects/84791364/packages/pypi/simple"  # pragma: allowlist secret
```

Create and activate the virtual environment:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r dev-requirements.txt
```

Confirm the venv is using Python 3.12:

```bash
python --version
which python
```

Expected: `Python 3.12.x` and a path ending in `venv/bin/python`.

Verify Invoke is available:

```bash
inv --list
```

Activate the environment in every new terminal session:

```bash
source venv/bin/activate
```

> After pulling branch changes that update `requirements*.txt` / `dev-requirements.txt`, run `pip install -r dev-requirements.txt` again (with `PIP_EXTRA_INDEX_URL` set).

---

## 7. Environment variables

The project uses `.env.dev` at the project root for values injected into Docker containers. Invoke tasks pass it via `docker compose --env-file .env.dev`.

| File | Purpose |
|------|---------|
| `.env.dev` | Local Docker Compose / Invoke (`COMPOSE_ENV_FILE`) |
| `.env.dev.example` | Committed template (safe local defaults) |
| `.env` | Optional copy of `.env.dev` for tools that read `.env` by convention |

`.env.dev` is not committed to Git.

### Setup

1. Copy the template:

```bash
cp .env.dev.example .env.dev
cp .env.dev .env
```

2. Confirm required values are **not empty**. Empty `POSTGRES_*` / `SECRET_KEY` / `PGADMIN_*` will break Docker Compose and container startup.

3. Leave the debug flags **empty** (do not use `False`):

```env
DEBUG_PYCHARM=
DEBUG_VSCODE=
DEBUG_CELERY=
```

> Using `DEBUG_PYCHARM=False` enables PyCharm remote debugging ÔÇö in Python the string `"False"` is truthy and can break container startup. Prefer empty values for normal development.

4. Export `GITLAB_PYPI_TOKEN` in the **same shell** before `inv docker.build` (Compose reads it as a BuildKit secret). Do not commit the token.

### Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SETTINGS_MODULE` | Yes | Use `claro_rf_check.settings.dev` for local development |
| `SECRET_KEY` | Yes | Django secret key (local default is fine for WSL) |
| `DEBUG` | Yes | Set to `True` for local development |
| `ALLOWED_HOSTS` / `DJANGO_ALLOWED_HOSTS` | Yes | e.g. `localhost,127.0.0.1` |
| `POSTGRES_DB` | Yes | Database name (e.g. `claro_rf_check`) |
| `POSTGRES_USER` | Yes | Must be `postgres` for the default Compose healthcheck |
| `POSTGRES_PASSWORD` | Yes | Database password (local default: `postgres`) |
| `DB_HOST` | Yes | Use `postgres` (Docker service name) |
| `DB_PORT` | No | Internal port; default `5432` |
| `PGADMIN_DEFAULT_EMAIL` | Yes | pgAdmin login email |
| `PGADMIN_DEFAULT_PASSWORD` | Yes | pgAdmin login password |
| `CACHE_REDIS_URL` | Yes | e.g. `redis://redis:6379/1` |
| `CELERY_BROKER_URL` | Yes | e.g. `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Yes | e.g. `redis://redis:6379/0` |
| `USE_OBS_MEDIA` | Yes | `True` for MinIO/OBS uploads |
| `OBS_*` | Yes (when OBS media on) | Bucket, endpoint, keys; local MinIO needs `OBS_ADDRESSING_STYLE=path` |
| `EMAIL_HOST` / `EMAIL_PORT` | Yes | Local defaults: `mailpit` / `1025` |
| `DEBUG_PYCHARM` | No | Leave **empty** |
| `DEBUG_VSCODE` | No | Leave **empty**; set automatically with `inv docker.run --debug-vscode` |
| `DEBUG_CELERY` | No | Leave **empty**; Compose defaults to broker/worker path (`DEBUG_CELERY:-true`) unless you override |
| `CORE_CONNECT_SSO_*` | Yes (for SSO login) | Issuer, client id `claro-rf`, redirect URI on `:8007` |
| `GITLAB_PYPI_TOKEN` | Yes (build) | Shell env for Docker BuildKit secret ÔÇö never commit |

### Example `.env.dev` (local development)

```env
DJANGO_SETTINGS_MODULE=claro_rf_check.settings.dev
SECRET_KEY=django-insecure-dev-only-change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

POSTGRES_DB=claro_rf_check
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DB_HOST=postgres
DB_PORT=5432

PGADMIN_DEFAULT_EMAIL=admin@localhost
PGADMIN_DEFAULT_PASSWORD=admin

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_USE_TLS=False
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=claro-rf-check@localhost

CACHE_REDIS_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

USE_OBS_MEDIA=True
OBS_BUCKET_NAME=claro-rf-check
OBS_ENDPOINT=http://minio:9000
OBS_ADDRESSING_STYLE=path
OBS_CUSTOM_DOMAIN=localhost:9120/claro-rf-check
OBS_ACCESS_KEY=minioadmin
OBS_SECRET_KEY=minioadmin

DEBUG_PYCHARM=
DEBUG_VSCODE=
DEBUG_CELERY=

CORE_CONNECT_SSO_PROJECT_ID=84791364
GITLAB_PYPI_USER=__token__

CORE_CONNECT_SSO_ISSUER=http://localhost:8001
CORE_CONNECT_SSO_INTERNAL_ISSUER=http://host.docker.internal:8001
CORE_CONNECT_SSO_CLIENT_ID=claro-rf
CORE_CONNECT_SSO_REDIRECT_URI=http://localhost:8007/claro-rf/sso/callback/
CORE_CONNECT_SSO_SCOPES=openid profile email
CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT=true
CORE_CONNECT_SSO_ENVIRONMENT=development
CORE_CONNECT_SSO_LOGIN_REDIRECT_URL=/
CORE_CONNECT_SSO_LOGOUT_REDIRECT_URL=/claro-rf/sso/login/
```

> **Never commit** `.env.dev`, `.env`, `.env.staging`, or `.env.prod` to Git. Only `.env.*.example` files are tracked.
>
> EP uploads use MinIO when `USE_OBS_MEDIA=True`. Local Docker must set `OBS_ADDRESSING_STYLE=path` (virtual hosting cannot resolve `bucket.minio`). Staging/prod OBS keeps `virtual`. Tests and CI force filesystem storage (`claro_rf_check.settings.ci`).

---

## 8. Pre-commit hooks

**Context:** **venv**. [Pre-commit](https://pre-commit.com/) runs code quality checks before each commit (Ruff + detect-secrets).

```bash
# venv
pre-commit install
```

Run all hooks manually:

```bash
# venv
pre-commit run --all-files
```

Run a specific hook:

```bash
# venv
pre-commit run detect-secrets --all-files
```

---

## 9. Docker stack

**Context:** **venv** at the project root (Invoke), with `GITLAB_PYPI_TOKEN` exported in the same WSL shell. Docker Engine must be running in WSL.

### Helper for compose exec

Throughout this guide, container commands use the Django container name `claro_rf_check`:

```bash
# venv ÔÇö Invoke (preferred when a task exists)
inv django.migrate

# container ÔÇö via docker exec
docker exec -it claro_rf_check python manage.py <command>
```

### Build images

```bash
# WSL shell with venv active
export GITLAB_PYPI_TOKEN="token"
inv docker.build
```

### Start the stack

Recommended for WSL (detached mode, Tailwind handled separately in [step 11](#11-tailwind-css)):

```bash
# venv
inv docker.run --daemon --no-tailwind
```

**Foreground** (logs visible in the terminal):

```bash
# venv
inv docker.run --no-tailwind
```

> On WSL with Windows PATH interop, `inv docker.run` without `--no-tailwind` tries to start Tailwind on the host and may fail with `npm error path C:\Windows\package.json`. Always use `--no-tailwind` and run Tailwind inside the container (step 11).

Useful flags:

| Flag | Description |
|------|-------------|
| `--daemon` | Run containers in the background |
| `--no-tailwind` | Skip starting the Tailwind CSS watcher on the host |
| `--debug-vscode` | Enable VS Code remote debugging (see [section 16](#16-remote-debugging-with-vs-code)) |
| `--celery` | Enable Celery debugging flags for the broker path |

### Stop the stack

```bash
# venv
inv docker.down
```

Remove containers **and volumes** (deletes database data):

```bash
# venv
inv docker.down --volumes
```

### Kill running containers

```bash
# venv
inv docker.kill
```

### Full rebuild (advanced)

Rebuilds everything from scratch. Optionally restores a database backup:

```bash
# venv
inv docker.fresh-restart
inv docker.fresh-restart --backup-file=backup_YYYYMMDD_HHMMSS.bkp
```

> Do **not** use `inv docker.fresh-restart` on first-time setup. Use the first-run sequence below.

### First-run sequence (after `.env.dev` is ready)

Order matters for static CSS. The Django container often starts **before** `dist/styles.css` exists; after you generate CSS you **must** restart `claro_rf_check` so Django picks up the new static directory (otherwise the CSS URL stays HTTP 404 even though the file is on disk). Full detail: [step 11](#11-tailwind-css).

```bash
# venv ÔÇö build and start
export GITLAB_PYPI_TOKEN="token"
inv docker.build
inv docker.run --daemon --no-tailwind
inv django.migrate

# container ÔÇö generate Tailwind CSS (dist/ is gitignored)
docker exec claro_rf_check python manage.py tailwind install
docker exec claro_rf_check python manage.py tailwind build

# WSL ÔÇö restart Django so static finders see the new dist/
docker restart claro_rf_check

# WSL ÔÇö confirm CSS is served (expect: 200 and non-zero size)
curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' \
  http://localhost:8007/static/css/dist/styles.css
```

Then create a superuser ([step 12](#12-create-a-superuser)) and open http://localhost:8007.

> **Expected before migrations:** Celery-related warnings about missing tables (e.g. `django_celery_beat_periodictask` does not exist) are normal. Proceed with `inv django.migrate`.

### Already configured (after `git pull`)

```bash
# venv
inv docker.run --daemon --no-tailwind
```

If `code/theme/static/css/dist/styles.css` is missing, or `/static/css/dist/styles.css` returns **404**, follow [step 11](#11-tailwind-css) (build + restart).

---

## 10. Database migrations

**Context:** **venv** (Invoke talks to the container). Stack must already be up ([step 9](#9-docker-stack)).

```bash
# venv
inv django.migrate
```

Create new migrations after model changes:

```bash
# venv
inv django.makemigrations
```

---

## 11. Tailwind CSS

**Context:** Tailwind commands run in the **container**; verification curls run in **WSL**. Prefer `inv docker.run --no-tailwind` so a host npm watcher is never started.

The compiled CSS (`code/theme/static/css/dist/styles.css`) is **not** in Git. On a fresh clone you must build it inside the container, then **restart Django**.

### Why restart after the first build

On first start, `dist/` usually does not exist yet. Django discovers static directories at process start. If you generate `styles.css` afterward without restarting `claro_rf_check`, the file can exist on disk while `http://localhost:8007/static/css/dist/styles.css` still returns **HTTP 404**. Restarting only the Django container fixes that.

Correct order (also in the [first-run sequence](#first-run-sequence-after-envdev-is-ready)):

1. Start the stack (`inv docker.run --daemon --no-tailwind`)
2. Build CSS inside the container
3. `docker restart claro_rf_check`
4. Verify file on disk **and** HTTP 200

### Build CSS

With the stack running:

```bash
# container
docker exec claro_rf_check python manage.py tailwind install
docker exec claro_rf_check python manage.py tailwind build

# WSL ÔÇö required after the first successful build (or whenever dist/ was missing at container start)
docker restart claro_rf_check
```

For live CSS reloading during development, start the watcher **inside** the container (after the first build + restart):

```bash
# container (detached)
docker exec -d claro_rf_check python manage.py tailwind start
```

### Verify CSS was generated and is served

Run these from **WSL** after build + restart:

```bash
# 1) File exists on the host bind mount (non-zero size)
ls -lh code/theme/static/css/dist/styles.css

# 2) Same path visible inside the container
docker exec claro_rf_check ls -lh /code/theme/static/css/dist/styles.css

# 3) Django can resolve the static URL (expect a path under /code/ÔÇª/dist/styles.css)
docker exec claro_rf_check python manage.py findstatic css/dist/styles.css

# 4) Application serves it (expect: 200 and a non-zero byte size, often ~100000+)
curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' \
  http://localhost:8007/static/css/dist/styles.css
```

| Check | Expected |
|-------|----------|
| `ls` on host / in container | File present, size greater than zero |
| `findstatic` | Prints a filesystem path ending in `styles.css` (not ÔÇ£No matchingÔÇªÔÇØ) |
| `curl` | `200` and `size_download` greater than zero |

If steps 1ÔÇô3 succeed but step 4 returns **404**, restart Django again (`docker restart claro_rf_check`) and re-run the curl. Hard-refresh the browser (`Ctrl+Shift+R`) after a 200.

> Always run Tailwind **inside** `claro_rf_check`. Do not rely on host `npm` / Windows PATH interop.

---

## 12. Create a superuser

**Context:** **container** (via `docker exec`). Stack running and migrations applied.

```bash
# container
docker exec -it claro_rf_check python manage.py createsuperuser
```

Or non-interactive (useful for a quick local admin):

```bash
# container
docker exec -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_EMAIL=admin@localhost \
  -e DJANGO_SUPERUSER_PASSWORD=admin \
  claro_rf_check python manage.py createsuperuser --noinput
```

Then sign in at http://localhost:8007/admin/ or use Core Connect SSO at `/claro-rf/sso/login/` when the IdP is available.

---

## 13. Access the application

| Resource | URL |
|----------|-----|
| Application | [http://localhost:8007](http://localhost:8007) |
| Django Admin | [http://localhost:8007/admin/](http://localhost:8007/admin/) |
| SSO login | [http://localhost:8007/claro-rf/sso/login/](http://localhost:8007/claro-rf/sso/login/) |
| Documentation (MkDocs) | [http://localhost:8008](http://localhost:8008) |
| Mailpit (captured email) | [http://localhost:8027](http://localhost:8027) |
| Flower (Celery) | [http://localhost:8009](http://localhost:8009) |
| MinIO API / Console | [http://localhost:9120](http://localhost:9120) / [http://localhost:9121](http://localhost:9121) |
| pgAdmin | [http://localhost:50525](http://localhost:50525) |
| Portainer | [http://localhost:9002](http://localhost:9002) |
| Health / Ready | `/healthz` ┬À `/readyz` |

### Main user flows

1. Sign in (admin or SSO).
2. Import an EP workbook (`/ep/upload/`).
3. Select sites/cells and generate Ger├¬ncia scripts (pre-check / full-check / combined).
4. Upload command returns and process validation.
5. Export or email reports.

EP imports require a signed-in user; results are visible to the owner or staff.

---

## 14. Running tests

**Context:** **venv** (pytest on the host, not inside Docker), with SQLite via `claro_rf_check.settings.ci` (configured in `pyproject.toml`):

```bash
# venv
inv test
```

Run a specific test file:

```bash
# venv
inv test --file-path=code/ep_import/tests/test_views.py
```

Filter by keyword:

```bash
# venv
inv test --keyword=test_login
```

You can also run pytest directly from the project root with the venv active:

```bash
# venv
DJANGO_SETTINGS_MODULE=claro_rf_check.settings.ci pytest
```

> If collection fails with `ModuleNotFoundError`, reinstall host deps with `PIP_EXTRA_INDEX_URL` set: `pip install -r dev-requirements.txt`.

---

## 15. Linting and formatting

**Context:** **venv**.

```bash
# venv
inv lint
```

Run individually:

```bash
# venv
inv lint.check
inv lint.format
inv lint.pip-audit
```

---

## 16. Remote debugging with VS Code

### Start the stack with debugging enabled

```bash
inv docker.run --daemon --no-tailwind --debug-vscode
```

Wait for the message `Waiting for debugger attach...` in the container logs.

### Configure VS Code

Create `.vscode/launch.json` in the project root:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Claro RF Check Debug",
      "type": "debugpy",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5682
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/code",
          "remoteRoot": "/code"
        }
      ],
      "django": true,
      "justMyCode": true
    }
  ]
}
```

> Port **5682** is the host mapping for the debug port inside the container (`5682:5679` in `docker-compose.dev.yaml`).

Press **F5** or use **Run and Debug** ÔåÆ **Claro RF Check Debug**.

### Debugging Celery

```bash
inv docker.run --daemon --no-tailwind --debug-vscode --celery
```

---

## 17. Invoke tasks reference

List all available tasks:

```bash
inv --list
```

| Task | Description |
|------|-------------|
| `inv docker.build` | Build Docker images |
| `inv docker.run` | Start the stack |
| `inv docker.down` | Stop and remove containers |
| `inv docker.down --volumes` | Stop containers and remove volumes (wipes DB data) |
| `inv docker.kill` | Kill running containers |
| `inv docker.fresh-restart` | Full rebuild and optional DB restore |
| `inv docker.celery-status` | Check Celery worker status |
| `inv django.migrate` | Apply database migrations |
| `inv django.makemigrations` | Create new migrations |
| `inv database.backup` / `inv db.backup` | Create a database backup |
| `inv database.restore --file-name=<file>` / `inv db.restore` | Restore from backup |
| `inv cache.cache-clear` | Clear the Django cache |
| `inv cache.cache-info` | Show cache backend info |
| `inv lint` | Run Ruff check + format check |
| `inv lint.format` | Apply Ruff fixes and format |
| `inv lint.pip-audit` | Audit `requirements.txt` |
| `inv test` | Run pytest |

> Task names with underscores are called with hyphens: `fresh_restart` ÔåÆ `inv docker.fresh-restart`.

---

## 18. Updating dependencies

Application dependencies are managed with [pip-tools](https://github.com/jazzband/pip-tools). The package `core-connect-sso` comes from the GitLab Package Registry, so you need a Personal Access Token before installing or recompiling.

### GitLab Personal Access Token

| Option | When to use |
|--------|-------------|
| **Legacy token** | Use this one. It exposes the classic scopes `read_api` and `read_registry` that this project expects. |
| **Fine-grained token** | Do **not** use it for this setup unless the team explicitly says so. |

**Create a Legacy token:**

1. Sign in at [gitlab.com](https://gitlab.com).
2. Open your avatar ÔåÆ **Edit profile** / **Preferences**.
3. In the left sidebar, open **Access Tokens** ([direct link](https://gitlab.com/-/user_settings/personal_access_tokens)).
4. Click **Generate token** and choose **Legacy token**.
5. Enable scopes: `read_api`, `read_registry`.
6. Create the token and **copy it immediately**.

Never commit this token. Use it only as an environment variable in your local shell.

### Set registry access in the terminal

**Bash / WSL:**

```bash
export GITLAB_PYPI_TOKEN="token"
export PIP_EXTRA_INDEX_URL="https://__token__:${GITLAB_PYPI_TOKEN}@gitlab.com/api/v4/projects/84791364/packages/pypi/simple"  # pragma: allowlist secret
```

`GITLAB_PYPI_TOKEN` is also required for `inv docker.build` (Compose BuildKit secret `gitlab_pypi_token`).

### Recompile lock files

1. Edit `requirements.in` (runtime) or `dev-requirements.in` (development).
2. Compile the lock files with `--no-emit-index-url` so the token / index URL is **not** written into the `.txt` files:

```bash
pip-compile --no-emit-index-url requirements.in
pip-compile --no-emit-index-url dev-requirements.in
```

3. Install locally:

```bash
pip install -r dev-requirements.txt
```

4. Rebuild the Docker stack:

```bash
inv docker.down
inv docker.build --up
```

---

## 19. Database backup and restore

### Create a backup

```bash
inv database.backup
# or
inv db.backup
```

Backups are saved to the `backups/` directory.

### Restore from backup

```bash
inv database.restore --file-name=backup_YYYYMMDD_HHMMSS.bkp
```

Replace the filename with the actual backup file in `backups/`.

---

## 20. Application structure

```text
claro-rf-check/
Ôö£ÔöÇÔöÇ code/                         # Django application
Ôöé   Ôö£ÔöÇÔöÇ claro_rf_check/           # Settings, URLs, Celery, health probes, S3 storage
Ôöé   Ôö£ÔöÇÔöÇ users/                    # Custom User + Core Connect SSO
Ôöé   Ôö£ÔöÇÔöÇ home/                     # Landing + 404
Ôöé   Ôö£ÔöÇÔöÇ ep_import/                # EP workbook upload and jobs
Ôöé   Ôö£ÔöÇÔöÇ precheck/                 # Pre-check flow (mainly 5G)
Ôöé   Ôö£ÔöÇÔöÇ poscheck/                 # Full Check (2G/3G/4G/5G)
Ôöé   Ôö£ÔöÇÔöÇ combined/                 # Combined multi-tech check
Ôöé   Ôö£ÔöÇÔöÇ reports/                  # XLSX export + email
Ôöé   Ôö£ÔöÇÔöÇ theme/                    # Tailwind CSS app
Ôöé   ÔööÔöÇÔöÇ static/                   # Shared JS (HTMX, Alpine CSP, app.js)
Ôö£ÔöÇÔöÇ docs/                         # MkDocs documentation
Ôö£ÔöÇÔöÇ tasks/                        # Invoke automation
Ôö£ÔöÇÔöÇ docker-compose.base.yaml
Ôö£ÔöÇÔöÇ docker-compose.yaml
Ôö£ÔöÇÔöÇ docker-compose.dev.yaml
Ôö£ÔöÇÔöÇ docker-compose.staging.yaml
Ôö£ÔöÇÔöÇ docker-compose.prod.app.yaml
Ôö£ÔöÇÔöÇ docker-compose.prod.db.yaml
Ôö£ÔöÇÔöÇ Dockerfile
Ôö£ÔöÇÔöÇ requirements.in / .txt
Ôö£ÔöÇÔöÇ dev-requirements.in / .txt
Ôö£ÔöÇÔöÇ pyproject.toml                # ruff, coverage, pytest
Ôö£ÔöÇÔöÇ mkdocs.yml
ÔööÔöÇÔöÇ .pre-commit-config.yaml
```

Extended product guides: [docs/index.md](docs/index.md) and MkDocs at http://localhost:8008.

---

## 21. Troubleshooting

### `WARN: The "POSTGRES_DB" variable is not set`

Create `.env.dev` from `.env.dev.example` (see [step 7](#7-environment-variables)) and fill in all required values. Invoke uses `docker compose --env-file .env.dev`.

### Docker build fails on `core-connect-sso` / empty BuildKit secret

Export the token before building:

```bash
export GITLAB_PYPI_TOKEN="token"
inv docker.build
```

See [step 18](#18-updating-dependencies).

### `claro_rf_check` container keeps restarting

Usually caused by `DEBUG_PYCHARM=False` in `.env.dev`. Set debug flags to empty:

```env
DEBUG_PYCHARM=
DEBUG_VSCODE=
DEBUG_CELERY=
```

Then restart: `inv docker.down && inv docker.run --daemon --no-tailwind`

### `npm error path C:\Windows\package.json`

WSL is invoking Windows npm when Tailwind runs on the host. Use `--no-tailwind` and run Tailwind inside the container (see [step 11](#11-tailwind-css)).

### Page loads without styles / CSS URL returns HTTP 404

Typical first-setup failure: Tailwind build succeeds, the file exists under `code/theme/static/css/dist/styles.css`, but the app still returns **404** because Django started before `dist/` existed.

```bash
# container ÔÇö rebuild if the file is missing
docker exec claro_rf_check python manage.py tailwind install
docker exec claro_rf_check python manage.py tailwind build

# WSL ÔÇö always restart Django after the first build (or when dist/ was created while the container was already up)
docker restart claro_rf_check

# WSL ÔÇö verify (expect: 200 and non-zero size)
curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' \
  http://localhost:8007/static/css/dist/styles.css
```

If the curl is still `404` while `ls` and `findstatic` succeed, see [step 11 ÔÇö Verify CSS](#verify-css-was-generated-and-is-served) and the [FAQ](#22-faq).

### `Command 'python3.12' not found` / `Unable to locate package python3.12`

**Do not jump straight to deadsnakes** if you already manage Python with pyenv (or similar).

1. Check an existing install:

```bash
command -v pyenv && pyenv versions
python3.12 --version
which python3.12
```

2. If pyenv has 3.12.x, activate it (`pyenv local 3.12.x` or `pyenv global 3.12.x`), then `hash -r` and re-check `python3.12 --version`. Use that interpreter in [step 6](#6-python-virtual-environment).

3. Only if you are **not** using pyenv and apt cannot find the package, install via deadsnakes ([Python 3.12 ÔÇö Option C](#option-c--install-via-deadsnakes-ppa-only-if-ab-do-not-apply)).

Do **not** substitute system `python3` (e.g. 3.14) for `python3.12`.

### `ensurepip is not available` / venv creation fails

```bash
sudo apt install -y python3.12-venv
rm -rf venv
python3.12 -m venv venv
source venv/bin/activate
```

### `venv/bin/activate: No such file or directory`

```bash
rm -rf venv
python3.12 -m venv venv
source venv/bin/activate
```

### `docker: command not found` inside WSL

Docker Engine is not installed. Follow [section 2 ÔÇö Docker CLI](#docker-cli-inside-wsl).

### `Cannot connect to the Docker daemon`

```bash
sudo systemctl start docker
sudo systemctl status docker
```

If the daemon is stuck, from **PowerShell on Windows**:

```powershell
wsl --shutdown
```

Then reopen Ubuntu and run `sudo systemctl start docker`.

### `Permission denied` when running Docker

```bash
sudo usermod -aG docker $USER
```

Log out and back into WSL, then retry.

### Celery container is unhealthy on first start

Expected before migrations:

```bash
inv django.migrate
docker restart claro_rf_check_celery
```

### `relation "django_celery_beat_periodictask" does not exist`

Same as above ÔÇö run migrations first.

### `inv: command not found`

```bash
source venv/bin/activate
```

### Port already in use (e.g. `8007`)

```bash
inv docker.down
docker ps
```

### Slow file I/O or Docker volume issues

Ensure the project is cloned under the Linux filesystem (`~/projects/...`), not under `/mnt/c/`.

### `ssh: connect to host gitlab.com: Permission denied`

Verify your SSH key is registered on GitLab (see [section 4](#4-configure-ssh-access-to-gitlab)).

### Pre-commit hook failures

```bash
pre-commit run --all-files
```

Fix reported issues, then commit again.

### VS Code debugger does not connect

1. Confirm the stack was started with `inv docker.run --debug-vscode`.
2. Check that `launch.json` uses port **5682** and host `localhost`.
3. Verify the container is running: `docker ps --filter name=claro_rf_check`.

### MinIO / EP upload fails with hostname errors

Local Docker must use path-style addressing:

```env
OBS_ADDRESSING_STYLE=path
```

Do not use `virtual` against the `minio` service DNS name.

### Postgres healthcheck fails after changing `POSTGRES_USER`

The Compose healthcheck uses `pg_isready -U postgres`. Keep `POSTGRES_USER=postgres` for local setup, or update the healthcheck in `docker-compose.dev.yaml`.

### `ModuleNotFoundError` when running `inv test`

```bash
# venv
source venv/bin/activate
export PIP_EXTRA_INDEX_URL="https://__token__:${GITLAB_PYPI_TOKEN}@gitlab.com/api/v4/projects/84791364/packages/pypi/simple"  # pragma: allowlist secret
pip install -r dev-requirements.txt
inv test
```

### I ran a command but nothing / the wrong tool ran

Confirm the context ([Where to run commands](#where-to-run-commands)):

- `inv: command not found` ÔåÆ activate **venv**
- `manage.py` / Tailwind on the host failing with Windows `npm` paths ÔåÆ use **container** (`docker exec claro_rf_check ÔÇª`) and `--no-tailwind`
- `docker: command not found` ÔåÆ install Docker in **WSL**, not only on Windows

---

## 22. FAQ

### Do I need Node.js on WSL?

No for the standard flow. Node is inside the Docker image. Build Tailwind with `docker exec claro_rf_check python manage.py tailwind ÔÇª` ([step 11](#11-tailwind-css)).

### I already use pyenv for Python 3.12. Should I install deadsnakes?

No. If `pyenv versions` shows 3.12.x, select it and use `python3.12 -m venv venv`. Only use apt/deadsnakes when you are **not** using pyenv and `python3.12` is missing. See [Python 3.12 ÔÇö Option A](#option-a--already-available-apt-pyenv-or-another-manager).

### Where do I run `inv`, `docker`, and `manage.py`?

| Command family | Context |
|----------------|---------|
| `inv ÔÇª`, `pip`, `pre-commit`, `pytest` | **venv** (project root) |
| `docker` / `docker compose` / `docker restart` | **WSL** |
| `python manage.py tailwind|createsuperuser|ÔÇª` for the running app | **container** via `docker exec claro_rf_check ÔÇª` |

Full table: [Where to run commands](#where-to-run-commands).

### Tailwind finished without errors, but `/static/css/dist/styles.css` is still 404

Almost always: Django started before `dist/` existed. Rebuild if needed, then **`docker restart claro_rf_check`**, then re-check with `curl` ([step 11](#11-tailwind-css)). Steps **9** and **11** must stay in that order on first setup.

### Do I need Core Connect running for local work?

Only for real browser SSO against the IdP (`CORE_CONNECT_SSO_ISSUER=http://localhost:8001`). You can use Django admin (`createsuperuser`) without Core Connect. Optional offline mock: `CORE_CONNECT_SSO_DEV=1` in `.env.dev`.

### Why `--no-tailwind` on WSL?

Without it, Invoke may start a host Tailwind watcher that hits Windows `npm` via PATH interop (`C:\Windows\package.json`). Build CSS in the container instead.

### Why does Docker build need `GITLAB_PYPI_TOKEN`?

The image installs `core-connect-sso` from the GitLab Package Registry. Export the token in the same shell before `inv docker.build` ([step 18](#18-updating-dependencies)).

### Can this stack run next to Core Connect / Audit Mail?

Yes. Ports and container names are offset/prefixed (app on **8007**, Postgres **5434**, Redis **6381**, etc.). See [Architecture](#architecture).

---

## 23. Final validation checklist

Use this checklist to confirm your environment is fully working:

- [ ] WSL 2 is installed and the project lives under `~/projects/` (Linux filesystem)
- [ ] `systemd` is enabled in WSL (`/etc/wsl.conf` with `systemd=true`)
- [ ] `python3.12 --version` shows Python 3.12.x (not 3.14) ÔÇö via apt **or** pyenv; do not force deadsnakes over pyenv
- [ ] `python --version` inside venv shows Python 3.12.x (`which python` ÔåÆ `ÔÇª/venv/bin/python`)
- [ ] `sudo systemctl status docker` shows `active (running)`
- [ ] `docker --version` and `docker compose version` work from WSL
- [ ] `docker run --rm hello-world` succeeds from WSL
- [ ] `ssh -T git@gitlab.com` succeeds
- [ ] `GITLAB_PYPI_TOKEN` is exported for builds and host pip installs
- [ ] Virtual environment is active (`which python` points to `venv/bin/python`)
- [ ] `pip install -r dev-requirements.txt` succeeded
- [ ] `.env.dev` exists with required variables filled in
- [ ] Debug flags are empty (`DEBUG_PYCHARM=`, not `False`)
- [ ] `OBS_ADDRESSING_STYLE=path` for local MinIO
- [ ] `inv --list` shows available tasks
- [ ] `pre-commit run --all-files` passes
- [ ] `inv docker.build` completes without errors
- [ ] `inv docker.run --daemon --no-tailwind` starts all services
- [ ] `inv django.migrate` completes without errors
- [ ] Tailwind built **inside the container**, then `docker restart claro_rf_check`
- [ ] `ls code/theme/static/css/dist/styles.css` shows a non-empty file
- [ ] `curl` to `/static/css/dist/styles.css` returns **HTTP 200** (not 404)
- [ ] [http://localhost:8007](http://localhost:8007) loads with styles
- [ ] Superuser can log in at [http://localhost:8007/admin/](http://localhost:8007/admin/)
- [ ] MkDocs opens at [http://localhost:8008](http://localhost:8008)
- [ ] Mailpit UI opens at [http://localhost:8027](http://localhost:8027)
- [ ] `inv lint` passes
- [ ] `inv test` runs without errors
- [ ] `inv docker.celery-status` reports a worker online

---

## Additional documentation

Extended documentation is available via MkDocs at [http://localhost:8008](http://localhost:8008) when the stack is running, or in the [`docs/`](docs/) directory:

| Topic | Doc |
|-------|-----|
| Docs home / stack notes | [docs/index.md](docs/index.md) |
| EP import guide | [docs/ep-import-guide.md](docs/ep-import-guide.md) |
| 5G pre-check | [docs/precheck-5g-guide.md](docs/precheck-5g-guide.md) |
| Full Check (pos-check) | [docs/poscheck-guide.md](docs/poscheck-guide.md) |
| Claro EP schema | [docs/ep-schema.md](docs/ep-schema.md) |
| Health / observability | [docs/operations/health-and-observability.md](docs/operations/health-and-observability.md) |
| Ops runbooks | [docs/operations/runbooks.md](docs/operations/runbooks.md) |

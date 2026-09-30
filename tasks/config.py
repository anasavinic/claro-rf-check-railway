import os

from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env.dev"))

CONTAINER_NAME = os.getenv("CONTAINER_NAME", "claro_rf_check")
DB_CONTAINER = os.getenv("DB_CONTAINER", "claro_rf_check_postgres")
DB_NAME = os.getenv("POSTGRES_DB", "claro_rf_check")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
COMPOSE_FILE = os.getenv("COMPOSE_FILE", "docker-compose.dev.yaml")
COMPOSE_ENV_FILE = os.getenv("COMPOSE_ENV_FILE", ".env.dev")
CODE_DIR = os.getenv("CODE_DIR", "./code")
COMPOSE = f"docker compose --env-file {COMPOSE_ENV_FILE} -f {COMPOSE_FILE}"

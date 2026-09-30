#!/bin/sh
set -eu

mkdir -p "${MEDIA_ROOT:-/data/media}"

echo "Applying migrations to host=${DB_HOST:-unset} db=${POSTGRES_DB:-unset}"
python manage.py migrate --noinput
python manage.py ensure_test_user

exec gunicorn claro_rf_check.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -

# Runbooks

## Application will not become ready

1. Check `GET /healthz`. If it fails, the process is down: inspect the container and Gunicorn logs.
2. Check `GET /readyz`. A 503 means the database is unreachable. Confirm `DB_HOST`, credentials, and that Postgres is healthy.
3. Do not treat `/healthz` as a database check.

## Import stays in processing

The reconcile task marks jobs stuck longer than `EP_IMPORT_STUCK_AFTER_SECONDS` as failed. The user can upload the file again. The failure message does not include the worker traceback.

## Restore and backups

Database backups belong in `backups/`, which is gitignored. Keep them outside the repository, encrypted, with a retention period and a tested restore. Do not commit `.sql`, `.dump`, or credential files.

# Health and observability

## Probes

| Path | Purpose | External I/O |
|---|---|---|
| `GET /healthz` | Liveness. The process is up. | None |
| `GET /readyz` | Readiness. The database answers `SELECT 1`. | Database |

Both are unauthenticated. A load balancer should use `/healthz` for liveness and `/readyz` before sending traffic.

`/healthz` returns `200 {"status": "ok"}`.

`/readyz` returns `200 {"status": "ok"}` or `503 {"status": "unavailable"}`.

## Logs

Staging and production write JSON to stdout. Import failures include `job_id` (also used as `correlation_id`), stage, and error code. Spreadsheet contents and exception text are not returned to the user.

## Retention

Expired EP files, jobs, and cells are removed by the Celery Beat task `ep_import.purge_expired_imports`. Stuck jobs are marked failed by `ep_import.reconcile_stuck_imports`.

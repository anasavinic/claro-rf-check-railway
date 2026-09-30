# Claro RF Check

Django application for Claro RF checks, based on the BRSC Core Connect project template.

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Django + Django REST Framework |
| Task queue | Celery + Redis |
| Database | PostgreSQL 14 |
| Object storage | MinIO (local) / Huawei OBS (cloud) |
| Frontend | Django templates, Tailwind, HTMX, Alpine.js CSP |
| Container | Docker Compose |

## Getting started

See `README.md` at the repository root for setup, ports, and compose files.

Frontend notes (Core Connect-inspired, not a 1:1 port):

- Alpine uses the **CSP build** vendored at `code/static/js/vendor/alpinejs-csp-3.15.8.min.js`. Templates may only bind property/method names (no inline JS expressions).
- HTMX comes from `django-htmx` (`{% htmx_script %}`); Tailwind from `django-tailwind`. Other JS libraries must live under `static/`.
- After HTMX swaps, `app.js` calls `Alpine.initTree` on the swapped node.

The application language is English. Workbook column aliases stay in the original Claro vocabulary.

## Guides

- [EP import](ep-import-guide.md)
- [5G pre-check](precheck-5g-guide.md)
- [Full Check (pos-check)](poscheck-guide.md)

## Technical reference

- [Claro EP schema](ep-schema.md)

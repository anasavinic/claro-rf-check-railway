"""Operability endpoints (Huawei ELB / ECS health checks)."""

from __future__ import annotations

from django.db import connection
from django.http import JsonResponse
from django.views import View


class HealthzView(View):
    """Liveness probe. No database, cache, or storage I/O."""

    http_method_names = ["get", "head"]

    def get(self, request, *args, **kwargs):
        return JsonResponse({"status": "ok"})

    def head(self, request, *args, **kwargs):
        response = self.get(request, *args, **kwargs)
        response.content = b""
        return response


class ReadyzView(View):
    """Readiness probe. Returns 503 when the database is unreachable."""

    http_method_names = ["get", "head"]

    def get(self, request, *args, **kwargs):
        ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # noqa: BLE001 — probe must never raise
            ok = False

        status = 200 if ok else 503
        return JsonResponse({"status": "ok" if ok else "unavailable"}, status=status)

    def head(self, request, *args, **kwargs):
        response = self.get(request, *args, **kwargs)
        response.content = b""
        return response

"""Celery broker dispatch helpers and fail-fast settings."""

from __future__ import annotations

from types import SimpleNamespace

from django.conf import settings
from kombu.exceptions import OperationalError as KombuOperationalError

from claro_rf_check.celery_dispatch import broker_dispatch_errors, delay_task


def test_broker_dispatch_errors_include_kombu_and_redis():
    errors = broker_dispatch_errors()
    assert ConnectionError in errors
    assert TimeoutError in errors
    assert KombuOperationalError in errors


def test_delay_task_publishes_without_retry_or_result_backend(monkeypatch):
    from celery.app.task import Task

    monkeypatch.setattr(Task, "_claro_rf_thread_delay", False, raising=False)
    calls: list[dict] = []

    def fake_apply_async(*, args=(), kwargs=None, retry=True, ignore_result=False, **options):
        calls.append(
            {
                "args": args,
                "kwargs": kwargs or {},
                "retry": retry,
                "ignore_result": ignore_result,
                "options": options,
            }
        )
        return SimpleNamespace(id="task-1")

    task = SimpleNamespace(apply_async=fake_apply_async)
    result = delay_task(task, "exec-1", foo="bar")

    assert result.id == "task-1"
    assert calls == [
        {
            "args": ("exec-1",),
            "kwargs": {"foo": "bar"},
            "retry": False,
            "ignore_result": True,
            "options": {},
        }
    ]


def test_delay_task_uses_patched_delay_in_thread_mode(monkeypatch):
    from celery.app.task import Task

    monkeypatch.setattr(Task, "_claro_rf_thread_delay", True, raising=False)
    calls: list[tuple] = []

    def fake_delay(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(id="thread-1")

    task = SimpleNamespace(delay=fake_delay, apply_async=lambda **_kwargs: None)
    result = delay_task(task, "job-1", bar=2)

    assert result.id == "thread-1"
    assert calls == [(("job-1",), {"bar": 2})]


def test_celery_broker_fail_fast_settings():
    assert settings.CELERY_BROKER_CONNECTION_TIMEOUT > 0
    assert settings.CELERY_BROKER_CONNECTION_MAX_RETRIES >= 1
    transport = settings.CELERY_BROKER_TRANSPORT_OPTIONS
    assert transport["socket_connect_timeout"] == settings.CELERY_BROKER_CONNECTION_TIMEOUT
    assert transport["socket_timeout"] == settings.CELERY_BROKER_CONNECTION_TIMEOUT
    assert transport["retry_on_timeout"] is False
    assert transport["max_retries"] == settings.CELERY_BROKER_CONNECTION_MAX_RETRIES
    assert settings.CELERY_TASK_PUBLISH_RETRY_POLICY["max_retries"] >= 1
    result_transport = settings.CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS
    assert result_transport["socket_timeout"] == settings.CELERY_BROKER_CONNECTION_TIMEOUT
    assert result_transport["retry_on_timeout"] is False

"""Safe Celery dispatch when the broker (Redis) may be unavailable."""

from __future__ import annotations

from typing import Any

BROKER_UNAVAILABLE_CODE = "BROKER_UNAVAILABLE"
BROKER_UNAVAILABLE_TITLE = "Could not process"
BROKER_UNAVAILABLE_MESSAGE = "Could not start processing. The queue service is unavailable."


def broker_dispatch_errors() -> tuple[type[BaseException], ...]:
    """Exceptions raised when Celery cannot reach the broker."""
    errors: list[type[BaseException]] = [ConnectionError, TimeoutError, OSError]
    try:
        from kombu.exceptions import OperationalError as KombuOperationalError

        errors.append(KombuOperationalError)
    except ImportError:
        pass
    try:
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError

        errors.extend([RedisConnectionError, RedisTimeoutError])
    except ImportError:
        pass
    return tuple(errors)


def delay_task(task: Any, *args: Any, **kwargs: Any) -> Any:
    """Enqueue a task so broker/result-backend outages fail the request quickly.

    On desktop/Railway thread mode, ``Task.delay`` is patched to run in-process
    after commit — use that path. Elsewhere, publish with retry=False and
    ignore_result=True so Celery does not block on the Redis result backend.
    """
    from celery.app.task import Task

    if getattr(Task, "_claro_rf_thread_delay", False):
        return task.delay(*args, **kwargs)
    return task.apply_async(args=args, kwargs=kwargs, retry=False, ignore_result=True)

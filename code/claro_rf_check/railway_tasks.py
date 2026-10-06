"""Run Celery tasks in-process when this deploy has no Redis worker."""

import logging
import threading
import time

logger = logging.getLogger("claro_rf_check.railway")

# One writer at a time. Combined 4G+5G used to start both checks together, so
# the second save could fail and leave the screen on Processing.
_RUN_LOCK = threading.Lock()
_LOCK_ATTEMPTS = 6


def _sqlite_locked(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def _apply_with_lock_retry(task, args, kwargs) -> None:
    from django.db import close_old_connections
    from django.db.utils import OperationalError

    for attempt in range(_LOCK_ATTEMPTS):
        try:
            task.apply(args=args, kwargs=kwargs, throw=True)
            return
        except OperationalError as exc:
            if not _sqlite_locked(exc) or attempt == _LOCK_ATTEMPTS - 1:
                raise
            logger.warning("Background task retrying after database lock: %s", task.name)
            close_old_connections()
            time.sleep(0.25 * (attempt + 1))


def install_thread_tasks() -> None:
    """Replace ``Task.delay`` with a daemon thread started after commit.

    Imports and checks call ``.delay()`` and then poll. A thread keeps that
    contract without a broker. ``on_commit`` waits until the row is visible.
    """

    from celery.app.task import Task

    if getattr(Task, "_claro_rf_thread_delay", False):
        return

    def delay(self, *args, **kwargs):
        from django.db import transaction

        task = self

        def runner():
            from django.db import close_old_connections

            close_old_connections()
            try:
                with _RUN_LOCK:
                    _apply_with_lock_retry(task, args, kwargs)
            except Exception:
                logger.exception("Background task failed: %s", task.name)
            finally:
                close_old_connections()

        def start():
            threading.Thread(target=runner, name=f"task-{task.name}", daemon=True).start()

        transaction.on_commit(start)

    Task.delay = delay
    Task._claro_rf_thread_delay = True

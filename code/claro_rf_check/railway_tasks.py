"""Run Celery tasks in-process when this deploy has no Redis worker."""

import logging
import threading

logger = logging.getLogger("claro_rf_check.railway")


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
                task.apply(args=args, kwargs=kwargs, throw=True)
            except Exception:
                logger.exception("Background task failed: %s", task.name)
            finally:
                close_old_connections()

        def start():
            threading.Thread(target=runner, name=f"task-{task.name}", daemon=True).start()

        transaction.on_commit(start)

    Task.delay = delay
    Task._claro_rf_thread_delay = True

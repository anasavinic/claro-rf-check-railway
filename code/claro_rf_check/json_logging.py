from __future__ import annotations

from typing import Any

from pythonjsonlogger.json import JsonFormatter


class ClaroRfCheckJsonFormatter(JsonFormatter):
    """JSON formatter for staging/production logs."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        if record.exc_info and "exception" not in log_record:
            log_record["exception"] = self.formatException(record.exc_info)


def build_json_logging(level: str) -> dict[str, Any]:
    """Build a dictConfig-compatible JSON logging setup."""

    normalized_level = (level or "INFO").strip().upper()
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "claro_rf_check.json_logging.ClaroRfCheckJsonFormatter",
                "fmt": fmt,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": normalized_level,
        },
        "loggers": {
            "gunicorn.access": {"handlers": ["console"], "level": normalized_level, "propagate": False},
            "gunicorn.error": {"handlers": ["console"], "level": normalized_level, "propagate": False},
            "celery": {"handlers": ["console"], "level": normalized_level, "propagate": False},
            "celery.task": {"handlers": ["console"], "level": normalized_level, "propagate": False},
        },
    }

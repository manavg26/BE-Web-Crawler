from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_call(event: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        logger = logging.getLogger(func.__module__)
        event_name = event or func.__qualname__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                started = time.perf_counter()
                logger.info("operation_started", extra={"event": event_name})
                try:
                    result = await func(*args, **kwargs)
                except Exception:
                    _log_exception(logger, event_name, started)
                    raise
                logger.info(
                    "operation_completed",
                    extra={"event": event_name, "duration_ms": _elapsed_ms(started)},
                )
                return result

            async_wrapper.__signature__ = inspect.signature(func, eval_str=True)  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            logger.info("operation_started", extra={"event": event_name})
            try:
                result = func(*args, **kwargs)
            except Exception:
                _log_exception(logger, event_name, started)
                raise
            logger.info(
                "operation_completed",
                extra={"event": event_name, "duration_ms": _elapsed_ms(started)},
            )
            return result

        sync_wrapper.__signature__ = inspect.signature(func, eval_str=True)  # type: ignore[attr-defined]
        return sync_wrapper

    return decorator


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _log_exception(logger: logging.Logger, event_name: str, started: float) -> None:
    import sys

    exc_type, exc, traceback = sys.exc_info()
    status_code = getattr(exc, "status_code", None)
    extra = {"event": event_name, "duration_ms": _elapsed_ms(started), "status_code": status_code}
    if isinstance(status_code, int) and status_code < 500:
        logger.warning("operation_rejected", extra=extra)
        return
    logger.exception("operation_failed", extra=extra, exc_info=(exc_type, exc, traceback))

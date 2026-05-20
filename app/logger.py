import json
import logging
import sys
import time
from typing import Any

_EXCLUDED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _EXCLUDED and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())
    root.addHandler(handler)
    root.setLevel(level)


class Log:
    """Thin wrapper pour logger avec des kwargs en extra fields."""

    def __init__(self, name: str):
        self._log = logging.getLogger(name)

    def info(self, event: str, **kw: Any) -> None:
        self._log.info(event, extra=kw)

    def warning(self, event: str, **kw: Any) -> None:
        self._log.warning(event, extra=kw)

    def error(self, event: str, exc_info: bool = False, **kw: Any) -> None:
        self._log.error(event, extra=kw, exc_info=exc_info)


def get_logger(name: str) -> Log:
    return Log(name)

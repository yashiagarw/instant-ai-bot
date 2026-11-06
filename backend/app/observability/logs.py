"""Structured logs with a request id, and no personal data.

- One JSON object per line (LOG_FORMAT=json, the default): time, level, logger, message, request_id, service, and the
  exception when there is one. LOG_FORMAT=console prints the same as plain text for reading locally.
- The request id comes from the browser (X-Request-ID, made by the web and admin apps for every API call), or is made
  here; the API sends it back in the response, passes it to every worker job it queues (notifications, dataset
  jobs), and the worker sets it while the job runs, so one id follows a request across web, API and worker.
- Every message is masked before it is written (app.llm.mask: phone numbers, emails, number plates), so a careless
  log call cannot leak them. Uvicorn's access log (it prints client IPs) is replaced by our own line without IP
  or query string.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import uuid
from datetime import UTC, datetime

from app.llm.mask import mask

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_service = "api"


def new_request_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex}"


def clean_request_id(value: str | None) -> str | None:
    """An id from outside (header or job argument) only if it looks like one."""
    return value if value and VALID_ID.match(value) else None


def current_request_id() -> str | None:
    return request_id_var.get()


class _Context(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.service = _service
        # Mask personal data in the final message (args included), once, before any handler formats it.
        try:
            text = record.getMessage()
        except Exception:  # a bad format string: keep what we have
            text = str(record.msg)
        record.msg, record.args = mask(text).text, None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "service": getattr(record, "service", _service),
        }
        for key in ("method", "path", "status", "duration_ms", "job"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exception"] = mask(self.formatException(record.exc_info)).text
        return json.dumps(out, ensure_ascii=False)


CONSOLE = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"


def configure(service: str, fmt: str = "json", level: str = "INFO") -> None:
    """Route every logger (ours, uvicorn, arq, sqlalchemy warnings) through one masked handler."""
    global _service
    _service = service
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_Context())
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(CONSOLE))
    handler._im_handler = True  # ours: replaced when configure() runs again; other handlers (pytest's) stay
    root = logging.getLogger()
    root.handlers[:] = [h for h in root.handlers if not getattr(h, "_im_handler", False)] + [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "arq", "arq.worker", "arq.jobs", "arq.connections"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    # Uvicorn's access line has the client IP and the full query string: ours replaces it.
    logging.getLogger("uvicorn.access").handlers[:] = []
    logging.getLogger("uvicorn.access").propagate = False

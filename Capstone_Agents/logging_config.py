"""Process-wide logging for the AURA API.

- Everything at INFO and above goes to a rotating file, ``<AURA_LOG_DIR>/aura.log``
  (5 files x 10 MB).
- Only WARNING and above is printed to the terminal, so a running server stays quiet
  until something needs attention.
- Every line carries the request ID of the HTTP request that produced it ("-" outside
  a request), so one request can be followed through the file.

Never log user content: chat text, photos, addresses, tokens or passwords.
"""
from __future__ import annotations

import contextvars
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("aura_request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 4  # aura.log + 4 rotated files = 5 files
_HANDLER_MARK = "_aura_handler"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(log_dir: Path, filename: str = "aura.log") -> None:
    """Attach AURA's file and terminal handlers to the root logger (idempotent)."""
    root = logging.getLogger()
    if any(getattr(handler, _HANDLER_MARK, False) for handler in root.handlers):
        return
    formatter = logging.Formatter(LOG_FORMAT)
    request_ids = RequestIdFilter()

    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / filename, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)

    terminal_handler = logging.StreamHandler()
    terminal_handler.setLevel(logging.WARNING)

    for handler in (file_handler, terminal_handler):
        handler.setFormatter(formatter)
        handler.addFilter(request_ids)
        setattr(handler, _HANDLER_MARK, True)
        root.addHandler(handler)
    root.setLevel(logging.INFO)

    # The API writes its own access line per request (without query strings, which
    # carry media signatures). Uvicorn's access log would duplicate it and print every
    # request to the terminal, so it is switched off.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True

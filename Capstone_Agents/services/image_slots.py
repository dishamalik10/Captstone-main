"""A process-wide cap on concurrent heavy image work (CNN, cut-out, body analysis).

Upload routes run in FastAPI's thread pool (plain ``def``), so several can overlap.
Measured on the 8 GB dev Mac, two concurrent CNN calls cost almost nothing extra, but
an unbounded number would compete for memory and CPU with the LLM. Callers wait up to
``WAIT_SECONDS`` for a slot and then get ``ImageBusyError`` (served as HTTP 503).
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from settings import settings


class ImageBusyError(RuntimeError):
    """All image-processing slots stayed busy for the whole wait."""


WAIT_SECONDS = 60.0
_slots = threading.BoundedSemaphore(max(1, settings.image_concurrency))


@contextmanager
def image_slot(wait_seconds: float | None = None) -> Iterator[None]:
    if not _slots.acquire(timeout=WAIT_SECONDS if wait_seconds is None else wait_seconds):
        raise ImageBusyError("AURA is busy processing other photos. Try again in a minute.")
    try:
        yield
    finally:
        _slots.release()

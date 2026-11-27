"""The try-on worker process, and the supervisor the API uses to run it.

The API starts one worker (``python -m services.tryon_worker --parent-pid <api pid>``)
when it boots and stops it on shutdown. The worker polls ``tryon_renders`` for queued
jobs, renders them one at a time, unloads the diffusion model after 10 idle minutes,
deletes expired looks, and writes a heartbeat the API reads for ``/tryon/status``.
Keeping it in its own process means a render's multi-GB memory use, or a crash in the
diffusion stack, cannot take the API down with it.

The worker exits on its own if the API process goes away (no orphaned renderer).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time

from settings import ROOT, settings

LOGGER = logging.getLogger(__name__)
POLL_SECONDS = 2.0
HEARTBEAT_SECONDS = 15.0
CLEANUP_SECONDS = 3600.0


# -- worker process -------------------------------------------------------------------

def run_worker(parent_pid: int | None) -> None:
    from services import tryon_service

    tryon_service.recover_interrupted()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    last_job = time.time()
    last_heartbeat = last_cleanup = 0.0
    LOGGER.info("Try-on worker started (pid %s)", os.getpid())
    while not stop.is_set():
        if parent_pid is not None and os.getppid() != parent_pid:
            LOGGER.warning("API process is gone; try-on worker exiting")
            break
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_SECONDS:
            tryon_service.heartbeat()
            last_heartbeat = now
        if now - last_cleanup >= CLEANUP_SECONDS:
            removed = tryon_service.cleanup_expired()
            if removed:
                LOGGER.info("Deleted %d expired try-on looks", removed)
            last_cleanup = now
        if tryon_service.process_next():
            last_job = time.time()
            tryon_service.heartbeat()
            last_heartbeat = time.time()
            continue
        if tryon_service.model.loaded and time.time() - last_job > tryon_service.IDLE_UNLOAD_SECONDS:
            LOGGER.info("Unloading idle try-on model")
            tryon_service.model.unload()
            tryon_service.heartbeat()
        stop.wait(POLL_SECONDS)
    tryon_service.model.unload()
    LOGGER.info("Try-on worker stopped")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AURA try-on worker")
    parser.add_argument("--parent-pid", type=int, default=None)
    args = parser.parse_args(argv)
    from logging_config import configure_logging

    # Its own file: two processes must not rotate the same log file.
    configure_logging(settings.log_dir, filename="tryon-worker.log")
    run_worker(args.parent_pid)


# -- supervisor (runs inside the API process) -----------------------------------------

class WorkerSupervisor:
    """Starts the worker, restarts it if it dies (at most ``MAX_RESTARTS`` per
    ``RESTART_WINDOW`` seconds), and stops it on shutdown."""

    MAX_RESTARTS = 5
    RESTART_WINDOW = 600.0
    CHECK_SECONDS = 5.0

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._restarts: list[float] = []

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _spawn(self) -> None:
        self._process = subprocess.Popen(
            [sys.executable, "-m", "services.tryon_worker", "--parent-pid", str(os.getpid())],
            cwd=str(ROOT), env=worker_env(),
        )
        LOGGER.info("Started try-on worker (pid %s)", self._process.pid)

    def start(self) -> None:
        self._stop.clear()
        self._spawn()
        self._thread = threading.Thread(target=self._watch, name="tryon-supervisor", daemon=True)
        self._thread.start()

    def _watch(self) -> None:
        while not self._stop.wait(self.CHECK_SECONDS):
            if self._process is None or self._process.poll() is None:
                continue
            now = time.time()
            self._restarts = [t for t in self._restarts if now - t < self.RESTART_WINDOW]
            if len(self._restarts) >= self.MAX_RESTARTS:
                LOGGER.error("Try-on worker keeps exiting (code %s); not restarting it again",
                             self._process.returncode)
                self._process = None
                return
            LOGGER.warning("Try-on worker exited (code %s); restarting", self._process.returncode)
            self._restarts.append(now)
            self._spawn()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            LOGGER.warning("Try-on worker did not stop in %.0f s; killing it", timeout)
            process.kill()
            process.wait()


def worker_env() -> dict[str, str]:
    """The API's environment, with its resolved data paths pinned, so the worker always
    uses exactly the same database, uploads and models as the API that started it."""
    return {
        **os.environ,
        "AURA_DATABASE_PATH": str(settings.database_path),
        "AURA_UPLOAD_DIR": str(settings.upload_dir),
        "AURA_LOG_DIR": str(settings.log_dir),
        "AURA_TRYON_MODEL_DIR": str(settings.tryon_model_dir),
    }


supervisor = WorkerSupervisor()


def should_spawn() -> bool:
    """Spawn only when try-on is on and its models are installed."""
    from services import tryon_service

    return (
        settings.tryon_enabled
        and settings.tryon_spawn_worker
        and not tryon_service.model.missing_files()
    )


if __name__ == "__main__":
    main()

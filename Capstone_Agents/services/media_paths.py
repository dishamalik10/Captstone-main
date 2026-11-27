"""Stored media references are bare file names inside ``settings.upload_dir``.

Earlier versions stored absolute paths, which broke as soon as the database and the
uploads folder moved to another machine or folder. Names are resolved against the
upload folder at read time; ``Path(value).name`` also accepts the old absolute values,
and ``migrate_to_names`` rewrites them once at startup.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from settings import settings


def media_name(path: str | Path) -> str:
    """What to store in the database for a file in the upload folder."""
    return Path(path).name


def media_path(stored: str | Path) -> Path:
    """The file on disk for a stored media reference (name or legacy absolute path)."""
    return settings.upload_dir / Path(stored).name


def migrate_to_names(db: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> None:
    """Rewrite legacy path values in ``table.columns`` to bare file names (idempotent)."""
    for column in columns:
        legacy = db.execute(
            f"SELECT rowid, {column} FROM {table} WHERE {column} LIKE '%/%'"
        ).fetchall()
        for rowid, value in legacy:
            db.execute(f"UPDATE {table} SET {column}=? WHERE rowid=?", (media_name(value), rowid))

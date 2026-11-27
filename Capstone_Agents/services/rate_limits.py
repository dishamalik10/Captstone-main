"""Per-account and per-IP rate limits (ENGINEERING_PLAN 4.1, decision Q12).

Events are rows in ``rate_events`` so limits survive a server restart (a daily upload
limit that reset on every restart would not be a limit). Each check-and-record runs in
one ``BEGIN IMMEDIATE`` transaction, so concurrent requests cannot both slip under it.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from database import connection
from settings import settings

MINUTE, HOUR, DAY = 60, 3600, 86400


@dataclass(frozen=True)
class Limit:
    count: int
    window: int  # seconds
    message: str


LIMITS: dict[str, Limit] = {
    "login_failed": Limit(5, 15 * MINUTE, "Too many failed sign-in attempts for this account. Try again in a few minutes."),
    "signup": Limit(5, DAY, "Too many accounts were created from this network today. Try again tomorrow."),
    "chat": Limit(20, HOUR, "You've sent a lot of messages this hour. Take a short break and try again."),
    "recommend": Limit(30, HOUR, "You've asked for a lot of outfits this hour. Try again a little later."),
    "upload": Limit(50, DAY, "You've reached today's limit of 50 photo uploads. Try again tomorrow."),
    "link_import": Limit(10, HOUR, "You've imported 10 links this hour. Try again a little later."),
    "report": Limit(20, DAY, "You've sent a lot of reports today. Thank you; we'll review them."),
}


class RateLimited(Exception):
    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after(db, bucket: str, key: str, limit: Limit, now: float) -> int:
    oldest = db.execute(
        "SELECT MIN(at) FROM rate_events WHERE bucket=? AND key=? AND at>?",
        (bucket, key, now - limit.window),
    ).fetchone()[0]
    return max(1, math.ceil((oldest or now) + limit.window - now))


def _over(db, bucket: str, key: str, limit: Limit, now: float) -> bool:
    db.execute("DELETE FROM rate_events WHERE bucket=? AND key=? AND at<=?", (bucket, key, now - limit.window))
    used = db.execute(
        "SELECT COUNT(*) FROM rate_events WHERE bucket=? AND key=? AND at>?", (bucket, key, now - limit.window),
    ).fetchone()[0]
    return used >= limit.count


def hit(bucket: str, key: str, now: float | None = None) -> None:
    """Count one event; raise RateLimited (without counting) if the limit is already used up."""
    if not settings.rate_limits_enabled:
        return
    limit, now = LIMITS[bucket], time.time() if now is None else now
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if _over(db, bucket, key, limit, now):
            raise RateLimited(limit.message, _retry_after(db, bucket, key, limit, now))
        db.execute("INSERT INTO rate_events(bucket, key, at) VALUES (?, ?, ?)", (bucket, key, now))


def check(bucket: str, key: str, now: float | None = None) -> None:
    """Raise RateLimited if the limit is used up, without counting (e.g. before a login)."""
    if not settings.rate_limits_enabled:
        return
    limit, now = LIMITS[bucket], time.time() if now is None else now
    with connection() as db:
        if _over(db, bucket, key, limit, now):
            raise RateLimited(limit.message, _retry_after(db, bucket, key, limit, now))


def record(bucket: str, key: str, now: float | None = None) -> None:
    """Count an event that already happened (e.g. a failed login)."""
    if not settings.rate_limits_enabled:
        return
    with connection() as db:
        db.execute("INSERT INTO rate_events(bucket, key, at) VALUES (?, ?, ?)", (bucket, key, time.time() if now is None else now))


def client_ip(headers, peer: str | None) -> str:
    """The caller's IP. Behind the Cloudflare tunnel every request arrives from 127.0.0.1,
    and Cloudflare sets ``CF-Connecting-IP`` (and overwrites any value a client sends).
    Uvicorn listens on 127.0.0.1 only, so nothing else can reach it to forge the header."""
    forwarded = (headers.get("cf-connecting-ip") or "").strip()
    return forwarded[:64] if forwarded else (peer or "unknown")

"""Real-time events over WebSockets: marketplace chat messages, typing, read receipts,
online presence and order updates.

Messages are still *sent* through the REST API (which validates, stores and checks
access); this hub only *delivers* events to the people involved, instantly. Clients
fall back to polling if the socket is down, so nothing is lost when a push is missed.

Connections live in this process's memory, so run a single server process (uvicorn's
default). Several worker processes would need a shared broker such as Redis pub/sub.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import anyio
from fastapi import WebSocket

from database import rows

LOGGER = logging.getLogger(__name__)


class ConnectionHub:
    """Register/unregister are synchronous on purpose: they run on the single event loop
    with no awaits, so they are atomic, and unregistering can never be skipped by a task
    being cancelled mid-cleanup (which would leave a user "online" forever)."""

    def __init__(self) -> None:
        self._sockets: dict[str, set[WebSocket]] = defaultdict(set)

    def connect(self, user_id: str, socket: WebSocket) -> bool:
        """Register a socket; True when this is the user's first (they just came online)."""
        first = not self._sockets[user_id]
        self._sockets[user_id].add(socket)
        return first

    def disconnect(self, user_id: str, socket: WebSocket) -> bool:
        """Forget a socket; True when the user has no sockets left (they went offline)."""
        sockets = self._sockets.get(user_id)
        if not sockets:
            return False
        sockets.discard(socket)
        if sockets:
            return False
        del self._sockets[user_id]
        return True

    def socket_count(self, user_id: str) -> int:
        return len(self._sockets.get(user_id, ()))

    def is_online(self, user_id: str) -> bool:
        return bool(self._sockets.get(user_id))

    async def send(self, user_ids: list[str] | set[str], event: dict[str, Any]) -> None:
        for user_id in set(user_ids):
            for socket in list(self._sockets.get(user_id, ())):
                try:
                    await socket.send_json(event)
                except Exception:  # a dead socket is cleaned up by its own receive loop
                    LOGGER.debug("Dropping event for a closed socket of %s", user_id)

    def push(self, user_ids: list[str] | set[str], event: dict[str, Any]) -> None:
        """Deliver from synchronous code (FastAPI runs plain `def` endpoints in a worker
        thread). Never raises: a failed push must not fail the request that caused it."""
        if not any(self._sockets.get(user_id) for user_id in set(user_ids)):
            return
        try:
            anyio.from_thread.run(self.send, user_ids, event)
        except Exception:
            LOGGER.debug("Real-time push skipped", exc_info=True)


hub = ConnectionHub()


def chat_partners(user_id: str) -> set[str]:
    """Everyone this user has a marketplace conversation with (who should see their presence)."""
    records = rows(
        "SELECT buyer_id, seller_id FROM conversations WHERE buyer_id=? OR seller_id=?", (user_id, user_id),
    )
    return {other for record in records for other in (record["buyer_id"], record["seller_id"]) if other != user_id}


def conversation_members(conversation_id: str) -> tuple[str, str] | None:
    records = rows("SELECT buyer_id, seller_id FROM conversations WHERE conversation_id=?", (conversation_id,))
    return (records[0]["buyer_id"], records[0]["seller_id"]) if records else None

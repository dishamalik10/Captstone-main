"""ASGI middleware: request IDs, one access-log line per request, and a generic 500.

Kept as plain ASGI (not BaseHTTPMiddleware) so streaming and file responses pass
through untouched. WebSocket and lifespan traffic is passed straight on.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from logging_config import request_id_var

LOGGER = logging.getLogger("aura.request")
REQUEST_ID_HEADER = b"x-request-id"


class RequestLoggingMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:12]
        # Each request runs in its own task, so this value cannot leak to other requests.
        request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                message = {**message, "headers": [*message.get("headers", []), (REQUEST_ID_HEADER, request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            # Full details go to the log only; the client gets a generic body plus the
            # request ID so a report can be matched to the log line.
            LOGGER.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if response_started:
                raise
            status = 500
            body = json.dumps({"detail": "Internal server error.", "request_id": request_id}).encode()
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (REQUEST_ID_HEADER, request_id.encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
        finally:
            # Path only: query strings can carry media signatures and user IDs.
            LOGGER.info(
                "%s %s -> %s in %.0f ms",
                scope.get("method"), scope.get("path"), status, (time.perf_counter() - started) * 1000,
            )

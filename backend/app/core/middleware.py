"""Request ID and access-log middleware, written as plain ASGI (cheaper than BaseHTTPMiddleware)."""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import internal_error_response
from app.core.logging import request_id_var

log = logging.getLogger("app.request")
# Accept a caller's ID only if it is short and safe to log; otherwise generate one.
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                status, started = message["status"], True
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            log.exception("unhandled error")
            if started:  # headers already sent; nothing safe to add
                raise
            await internal_error_response()(scope, receive, send_with_id)
        finally:
            log.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],  # path only: query strings may carry personal data
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            request_id_var.reset(token)

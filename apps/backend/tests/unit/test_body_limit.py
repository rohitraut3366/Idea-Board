import asyncio

import pytest
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from idea_board.middleware import RequestBodyLimitMiddleware


@pytest.mark.parametrize("body_size,expected_status", [(16 * 1024, 200), (16 * 1024 + 1, 413)])
def test_body_limit_counts_bytes_across_chunks(body_size: int, expected_status: int) -> None:
    received_messages: list[Message] = [
        {"type": "http.request", "body": b"x" * 8000, "more_body": True},
        {"type": "http.request", "body": b"x" * (body_size - 8000), "more_body": False},
    ]
    sent_messages: list[Message] = []
    delivered_body: bytes | None = None

    async def receive() -> Message:
        return received_messages.pop(0)

    async def send(message: Message) -> None:
        sent_messages.append(message)

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal delivered_body
        delivered_body = (await receive())["body"]
        await JSONResponse({"ok": True})(scope, receive, send)

    middleware = RequestBodyLimitMiddleware(application)
    asyncio.run(middleware({"type": "http"}, receive, send))
    assert sent_messages[0]["status"] == expected_status
    if expected_status == 200:
        assert delivered_body == b"x" * body_size
    else:
        assert delivered_body is None

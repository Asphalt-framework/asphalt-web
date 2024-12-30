from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, cast
from urllib.parse import parse_qs

import pytest
from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    ASGISendEvent,
    HTTPScope,
    Scope,
    WebSocketScope,
)
from asphalt.core import (
    Context,
    add_resource,
    current_context,
    get_resource_nowait,
    inject,
    resource,
    start_component,
)
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from asphalt.web.asgi3 import ASGIComponent

pytestmark = pytest.mark.anyio


@inject
async def application(
    scope: HTTPScope,
    receive: ASGIReceiveCallable,
    send: ASGISendCallable,
    my_resource: str = resource(),
    another_resource: str = resource("another"),
):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    elif scope["type"] == "http":
        current_context().get_resource_nowait(HTTPScope)
        query = parse_qs(cast(bytes, scope["query_string"]))
        await receive()

        body = json.dumps(
            {
                "message": query[b"param"][0].decode(),
                "my resource": my_resource,
                "another resource": another_resource,
            }
        ).encode()

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", b"%d" % len(body)),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )
    elif scope["type"] == "websocket":
        current_context().get_resource_nowait(WebSocketScope)
        await receive()  # Receive connection
        await send(  # Accept connection
            {
                "type": "websocket.accept",
            }
        )
        packet = await receive()
        await send(
            {
                "type": "websocket.send",
                "text": json.dumps(
                    {
                        "message": "Hello " + packet["text"],
                        "my resource": my_resource,
                        "another resource": another_resource,
                    }
                ),
            }
        )


class TextReplacerMiddleware:
    def __init__(self, app: ASGI3Application, text: str, replacement: str):
        self.app = app
        self.text = text.encode()
        self.replacement = replacement.encode()

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        start_event: ASGISendEvent

        async def wrapped_send(event: ASGISendEvent) -> None:
            nonlocal start_event

            if event["type"] == "http.response.start":
                start_event = event
                return
            elif event["type"] == "http.response.body":
                event["body"] = event["body"].replace(self.text, self.replacement)
                for i, (key, value) in enumerate(start_event["headers"]):
                    if key == b"content-length":
                        start_event["headers"][i] = key, b"%d" % len(event["body"])
                        break

                await send(start_event)

            await send(event)

        await self.app(scope, receive, wrapped_send)


async def test_http(unused_tcp_port: int):
    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            ASGIComponent,
            {
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        get_resource_nowait(ASGI3Application)

        # Ensure that the application responds correctly to an HTTP request
        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.json() == {
            "message": "Hello World",
            "my resource": "foo",
            "another resource": "bar",
        }


async def test_ws(unused_tcp_port: int):
    async with Context():
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            ASGIComponent,
            {
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        get_resource_nowait(ASGI3Application)

        # Ensure that the application works correctly with a websocket connection
        async with aconnect_ws(f"http://localhost:{unused_tcp_port}/ws") as ws:
            await ws.send_text("World")
            response = json.loads(await ws.receive_text())
            assert response == {
                "message": "Hello World",
                "my resource": "foo",
                "another resource": "bar",
            }


@pytest.mark.parametrize("method", ["direct", "dict"])
async def test_middleware(unused_tcp_port: int, method: str):
    middlewares: Sequence[Callable[..., ASGI3Application] | dict[str, Any]]
    if method == "direct":
        middlewares = [lambda app: TextReplacerMiddleware(app, "World", "Middleware")]
    else:
        middlewares = [
            {
                "type": f"{__name__}:TextReplacerMiddleware",
                "text": "World",
                "replacement": "Middleware",
            }
        ]

    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            ASGIComponent,
            {
                "middlewares": middlewares,
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        get_resource_nowait(ASGI3Application)

        # Ensure that the application responds correctly to an HTTP request
        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.json() == {
            "message": "Hello Middleware",
            "my resource": "foo",
            "another resource": "bar",
        }


def test_bad_middleware_type():
    with pytest.raises(
        TypeError,
        match="middleware must be either a callable or a dict, not 'foo'",
    ):
        ASGIComponent(app=application, middlewares=["foo"])


def test_bad_middleware_dict():
    with pytest.raises(TypeError, match=r"Middleware \(1\) is not callable"):
        ASGIComponent(app=application, middlewares=[{"type": 1}])

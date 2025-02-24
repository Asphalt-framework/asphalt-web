from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

import pytest
import websockets
from asgiref.typing import ASGI3Application, HTTPScope, WebSocketScope
from httpx import AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.websockets import WebSocket

from asphalt.core import Component, Context, inject, require_resource, resource
from asphalt.web.starlette import StarletteComponent

from .test_asgi3 import TextReplacerMiddleware


@pytest.mark.parametrize("method", ["static", "dynamic"])
@pytest.mark.asyncio
async def test_http(unused_tcp_port: int, method: str):
    @inject
    async def root(
        request: Request,
        my_resource: str = resource(),
        another_resource: str = resource("another"),
    ) -> Response:
        require_resource(HTTPScope)
        require_resource(Request)
        return JSONResponse(
            {
                "message": request.query_params["param"],
                "my resource": my_resource,
                "another resource": another_resource,
            }
        )

    application = Starlette()
    if method == "static":
        application.add_route("/", root)
        components = {}
    else:

        class RouteComponent(Component):
            @inject
            async def start(self, ctx: Context, app: Starlette = resource()) -> None:
                app = require_resource(Starlette)
                app.add_route("/", root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context() as ctx, AsyncClient() as http:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await StarletteComponent(
            components=components, app=application, port=unused_tcp_port
        ).start(ctx)

        # Ensure that the application got added as a resource
        asgi_app = ctx.require_resource(ASGI3Application)
        starlette_app = ctx.require_resource(Starlette)
        assert starlette_app is asgi_app

        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.json() == {
            "message": "Hello World",
            "my resource": "foo",
            "another resource": "bar",
        }


@pytest.mark.parametrize("method", ["static", "dynamic"])
@pytest.mark.asyncio
async def test_ws(unused_tcp_port: int, method: str):
    @inject
    async def ws_root(
        websocket: WebSocket,
        my_resource: str = resource(),
        another_resource: str = resource("another"),
    ):
        require_resource(WebSocketScope)
        await websocket.accept()
        message = await websocket.receive_text()
        await websocket.send_json(
            {
                "message": f"Hello {message}",
                "my resource": my_resource,
                "another resource": another_resource,
            }
        )

    application = Starlette()
    if method == "static":
        application.add_websocket_route("/ws", ws_root)
        components = {}
    else:

        class RouteComponent(Component):
            @inject
            async def start(self, ctx: Context, app: Starlette = resource()) -> None:
                app = require_resource(Starlette)
                app.add_websocket_route("/ws", ws_root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context() as ctx:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await StarletteComponent(
            components=components, app=application, port=unused_tcp_port
        ).start(ctx)

        # Ensure that the application got added as a resource
        asgi_app = ctx.require_resource(ASGI3Application)
        starlette_app = ctx.require_resource(Starlette)
        assert starlette_app is asgi_app

        async with websockets.connect(f"ws://localhost:{unused_tcp_port}/ws") as ws:
            await ws.send("World")
            response = json.loads(await ws.recv())
            assert response == {
                "message": "Hello World",
                "my resource": "foo",
                "another resource": "bar",
            }


@pytest.mark.parametrize("method", ["direct", "dict"])
@pytest.mark.asyncio
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

    async def root(request: Request) -> Response:
        return PlainTextResponse("Hello World")

    application = Starlette()
    application.add_route("/", root)
    async with Context() as ctx, AsyncClient() as http:
        await StarletteComponent(
            port=unused_tcp_port, app=application, middlewares=middlewares
        ).start(ctx)

        # Ensure that the application responds correctly to an HTTP request
        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.text == "Hello Middleware"


def test_bad_middleware_type():
    with pytest.raises(
        TypeError,
        match="middleware must be either a callable or a dict, not 'foo'",
    ):
        StarletteComponent(middlewares=["foo"])


def test_bad_middleware_dict():
    with pytest.raises(TypeError, match=r"Middleware \(1\) is not callable"):
        StarletteComponent(middlewares=[{"type": 1}])

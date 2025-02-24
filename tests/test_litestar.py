from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, Dict

import pytest
import websockets
from asgiref.typing import ASGI3Application, HTTPScope, WebSocketScope
from httpx import AsyncClient

from asphalt.core import Component, Context, require_resource

try:
    from litestar import Litestar, MediaType, Request, get, websocket_listener

    from asphalt.web.litestar import AsphaltProvide, LitestarComponent

    skip = False
except ModuleNotFoundError:
    pytestmark = pytest.mark.skip("litestar not available")
    skip = True

from .test_asgi3 import TextReplacerMiddleware

if not skip:

    @get("/", media_type=MediaType.JSON)
    async def root(request: Request) -> Dict[str, Any]:  # noqa: UP006
        my_resource = require_resource(str)
        another_resource = require_resource(str, "another")
        require_resource(HTTPScope)
        require_resource(Request)
        return {
            "message": request.query_params["param"],
            "my resource": my_resource,
            "another resource": another_resource,
        }

    @websocket_listener("/ws")
    async def ws_root(data: str) -> Dict[str, Any]:  # noqa: UP006
        my_resource = require_resource(str)
        another_resource = require_resource(str, "another")
        require_resource(WebSocketScope)
        return {
            "message": f"Hello {data}",
            "my resource": my_resource,
            "another resource": another_resource,
        }


@pytest.mark.parametrize("method", ["static", "static-ref", "dynamic"])
@pytest.mark.asyncio
async def test_http(unused_tcp_port: int, method: str) -> None:
    route_handlers = []
    components = {}
    if method == "static":
        route_handlers.append(root)
    elif method == "static-ref":
        route_handlers.append(f"{__name__}:root")
    else:

        class RouteComponent(Component):
            async def start(self, ctx: Context) -> None:
                app = require_resource(Litestar)
                app.register(root)

        components["myroutes"] = {"type": RouteComponent}

    async with Context() as ctx, AsyncClient() as http:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await LitestarComponent(
            components=components, port=unused_tcp_port, route_handlers=route_handlers
        ).start(ctx)

        # Ensure that the application got added as a resource
        asgi_app = ctx.require_resource(ASGI3Application)
        litestar_app = ctx.require_resource(Litestar)
        assert litestar_app is asgi_app

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
async def test_ws(unused_tcp_port: int, method: str) -> None:
    route_handlers = []
    components = {}
    if method == "static":
        route_handlers.append(ws_root)
    else:

        class RouteComponent(Component):
            async def start(self, ctx: Context) -> None:
                app = require_resource(Litestar)
                app.register(ws_root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context() as ctx:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await LitestarComponent(
            components=components, port=unused_tcp_port, route_handlers=route_handlers
        ).start(ctx)

        # Ensure that the application got added as a resource
        asgi_app = ctx.require_resource(ASGI3Application)
        litestar_app = ctx.require_resource(Litestar)
        assert litestar_app is asgi_app

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
async def test_middleware(unused_tcp_port: int, method: str) -> None:
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

    @get("/")
    async def root() -> str:
        return "Hello World"

    async with Context() as ctx, AsyncClient() as http:
        await LitestarComponent(
            port=unused_tcp_port, middlewares=middlewares, route_handlers=[root]
        ).start(ctx)

        # Ensure that the application responds correctly to an HTTP request
        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.text == "Hello Middleware"


@pytest.mark.asyncio
async def test_dependency_injection(unused_tcp_port: int) -> None:
    @get(
        "/",
        media_type=MediaType.JSON,
        dependencies={
            "my_resource": AsphaltProvide(str),
            "another_resource": AsphaltProvide(str, "another"),
        },
    )
    async def root(request: Request, my_resource: str, another_resource: str) -> Dict[str, Any]:  # noqa: UP006
        my_resource = require_resource(str)
        another_resource = require_resource(str, "another")
        require_resource(HTTPScope)
        require_resource(Request)
        return {
            "message": request.query_params["param"],
            "my resource": my_resource,
            "another resource": another_resource,
        }

    async with Context() as ctx, AsyncClient() as http:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await LitestarComponent(port=unused_tcp_port, route_handlers=[root]).start(ctx)

        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.json() == {
            "message": "Hello World",
            "my resource": "foo",
            "another resource": "bar",
        }


def test_bad_middleware_type():
    with pytest.raises(
        TypeError,
        match="middleware must be either a callable or a dict, not 'foo'",
    ):
        LitestarComponent(middlewares=["foo"])


def test_bad_middleware_dict():
    with pytest.raises(TypeError, match=r"Middleware \(1\) is not callable"):
        LitestarComponent(middlewares=[{"type": 1}])

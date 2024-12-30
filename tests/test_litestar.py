from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from asgiref.typing import ASGI3Application, HTTPScope, WebSocketScope
from asphalt.core import Component, Context, add_resource, get_resource_nowait, start_component
from httpx import AsyncClient
from httpx_ws import aconnect_ws

try:
    from litestar import Litestar, MediaType, Request, get, websocket_listener

    from asphalt.web.litestar import AsphaltProvide, LitestarComponent

    skip = False
except ModuleNotFoundError:
    pytestmark = pytest.mark.skip("litestar not available")
    skip = True
else:
    pytestmark = pytest.mark.anyio

from .test_asgi3 import TextReplacerMiddleware

if not skip:

    @get("/", media_type=MediaType.JSON)
    async def root(request: Request) -> dict[str, Any]:
        my_resource = get_resource_nowait(str)
        another_resource = get_resource_nowait(str, "another")
        get_resource_nowait(HTTPScope)
        get_resource_nowait(Request)
        return {
            "message": request.query_params["param"],
            "my resource": my_resource,
            "another resource": another_resource,
        }

    @websocket_listener("/ws")
    async def ws_root(data: str) -> dict[str, Any]:
        my_resource = get_resource_nowait(str)
        another_resource = get_resource_nowait(str, "another")
        get_resource_nowait(WebSocketScope)
        return {
            "message": f"Hello {data}",
            "my resource": my_resource,
            "another resource": another_resource,
        }


@pytest.mark.parametrize("method", ["static", "static-ref", "dynamic"])
async def test_http(unused_tcp_port: int, method: str) -> None:
    route_handlers = []
    components = {}
    if method == "static":
        route_handlers.append(root)
    elif method == "static-ref":
        route_handlers.append(f"{__name__}:root")
    else:

        class RouteComponent(Component):
            async def start(self) -> None:
                app = get_resource_nowait(Litestar)
                app.register(root)

        components["myroutes"] = {"type": RouteComponent}

    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            LitestarComponent,
            {"components": components, "port": unused_tcp_port, "route_handlers": route_handlers},
        )

        # Ensure that the application got added as a resource
        asgi_app = get_resource_nowait(ASGI3Application)
        litestar_app = get_resource_nowait(Litestar)
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
async def test_ws(unused_tcp_port: int, method: str) -> None:
    route_handlers = []
    components = {}
    if method == "static":
        route_handlers.append(ws_root)
    else:

        class RouteComponent(Component):
            async def start(self) -> None:
                app = get_resource_nowait(Litestar)
                app.register(ws_root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context():
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            LitestarComponent,
            {"components": components, "port": unused_tcp_port, "route_handlers": route_handlers},
        )

        # Ensure that the application got added as a resource
        asgi_app = get_resource_nowait(ASGI3Application)
        litestar_app = get_resource_nowait(Litestar)
        assert litestar_app is asgi_app

        async with aconnect_ws(f"http://localhost:{unused_tcp_port}/ws") as ws:
            await ws.send_text("World")
            response = json.loads(await ws.receive_text())
            assert response == {
                "message": "Hello World",
                "my resource": "foo",
                "another resource": "bar",
            }


@pytest.mark.parametrize("method", ["direct", "dict"])
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

    async with Context(), AsyncClient() as http:
        await start_component(
            LitestarComponent,
            {"port": unused_tcp_port, "middlewares": middlewares, "route_handlers": [root]},
        )

        # Ensure that the application responds correctly to an HTTP request
        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.text == "Hello Middleware"


async def test_dependency_injection(unused_tcp_port: int) -> None:
    @get(
        "/",
        media_type=MediaType.JSON,
        dependencies={
            "my_resource": AsphaltProvide(str),
            "another_resource": AsphaltProvide(str, "another"),
        },
    )
    async def root(request: Request, my_resource: str, another_resource: str) -> dict[str, Any]:
        my_resource = get_resource_nowait(str)
        another_resource = get_resource_nowait(str, "another")
        get_resource_nowait(HTTPScope)
        get_resource_nowait(Request)
        return {
            "message": request.query_params["param"],
            "my resource": my_resource,
            "another resource": another_resource,
        }

    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            LitestarComponent, {"port": unused_tcp_port, "route_handlers": [root]}
        )

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

from __future__ import annotations

import json

import pytest
import websockets
from asphalt.core import (
    Component,
    Context,
    add_resource,
    get_resource_nowait,
    inject,
    resource,
    start_component,
)
from httpx import AsyncClient

try:
    from aiohttp.abc import Request
    from aiohttp.web_app import Application
    from aiohttp.web_middlewares import middleware
    from aiohttp.web_response import Response, json_response
    from aiohttp.web_ws import WebSocketResponse

    from asphalt.web.aiohttp import AIOHTTPComponent
except ModuleNotFoundError:
    pytestmark = pytest.mark.skip("aiohttp not available")
else:
    pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def setup_text_replacer(app, *, text: str, replacement: str) -> None:
    @middleware
    async def text_replacer(request: Request, handler) -> None:
        response = await handler(request)
        response.text = response.text.replace(text, replacement)
        return response

    app.middlewares.append(text_replacer)


@pytest.mark.parametrize("method", ["static", "dynamic"])
async def test_http(unused_tcp_port: int, method: str):
    @inject
    async def root(
        request,
        my_resource: str = resource(),
        another_resource: str = resource("another"),
    ):
        return json_response(
            {
                "message": request.query["param"],
                "my resource": my_resource,
                "another resource": another_resource,
            }
        )

    application = Application()
    if method == "static":
        application.router.add_route("GET", "/", root)
        components = {}
    else:

        class RouteComponent(Component):
            async def start(self) -> None:
                app = get_resource_nowait(Application)
                app.router.add_route("GET", "/", root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            AIOHTTPComponent,
            {
                "components": components,
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        get_resource_nowait(Application)

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
async def test_ws(unused_tcp_port: int, method: str):
    @inject
    async def ws_root(
        request,
        my_resource: str = resource(),
        another_resource: str = resource("another"),
    ):
        ws = WebSocketResponse()
        await ws.prepare(request)
        message = await ws.receive_str()
        await ws.send_json(
            {
                "message": f"Hello {message}",
                "my resource": my_resource,
                "another resource": another_resource,
            }
        )
        return ws

    application = Application()
    if method == "static":
        application.router.add_route("GET", "/", ws_root)
        components = {}
    else:

        class RouteComponent(Component):
            async def start(self) -> None:
                app = get_resource_nowait(Application)
                app.router.add_route("GET", "/", ws_root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context():
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            AIOHTTPComponent,
            {
                "components": components,
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        get_resource_nowait(Application)

        async with websockets.connect(f"ws://localhost:{unused_tcp_port}") as ws:
            await ws.send("World")
            response = json.loads(await ws.recv())
            assert response == {
                "message": "Hello World",
                "my resource": "foo",
                "another resource": "bar",
            }


@pytest.mark.parametrize("method", ["direct", "dict"])
async def test_middleware(unused_tcp_port: int, method: str):
    @middleware
    async def text_replacer(request: Request, handler) -> None:
        response = await handler(request)
        response.text = response.text.replace("Hello World", "Hello Middleware")
        return response

    async def root(request: Request) -> Response:
        return Response(text="Hello World")

    application = Application()
    application.router.add_route("GET", "/", root)

    if method == "direct":
        middlewares = [text_replacer]
    else:
        middlewares = [
            {
                "type": f"{__name__}:setup_text_replacer",
                "text": "Hello World",
                "replacement": "Hello Middleware",
            }
        ]

    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            AIOHTTPComponent,
            {
                "middlewares": middlewares,
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        get_resource_nowait(Application)

        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.text == "Hello Middleware"


def test_bad_middleware_type():
    with pytest.raises(
        TypeError,
        match="middleware must be either a coroutine function or a dict, not 'foo'",
    ):
        AIOHTTPComponent(middlewares=["foo"])


def test_bad_middleware_dict():
    with pytest.raises(TypeError, match=r"Setup function \(1\) is not callable"):
        AIOHTTPComponent(middlewares=[{"type": 1}])

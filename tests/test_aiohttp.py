from __future__ import annotations

import json

import pytest
import websockets
from httpx import AsyncClient

from asphalt.core import Component, Context, inject, require_resource, resource

try:
    from aiohttp.abc import Request
    from aiohttp.web_app import Application
    from aiohttp.web_middlewares import middleware
    from aiohttp.web_response import Response, json_response
    from aiohttp.web_ws import WebSocketResponse

    from asphalt.web.aiohttp import AIOHTTPComponent
except ModuleNotFoundError:
    pytestmark = pytest.mark.skip("aiohttp not available")


def setup_text_replacer(app, *, text: str, replacement: str) -> None:
    @middleware
    async def text_replacer(request: Request, handler) -> None:
        response = await handler(request)
        response.text = response.text.replace(text, replacement)
        return response

    app.middlewares.append(text_replacer)


@pytest.mark.parametrize("method", ["static", "dynamic"])
@pytest.mark.asyncio
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
            async def start(self, ctx: Context) -> None:
                app = require_resource(Application)
                app.router.add_route("GET", "/", root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context() as ctx, AsyncClient() as http:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await AIOHTTPComponent(components=components, app=application, port=unused_tcp_port).start(
            ctx
        )

        # Ensure that the application got added as a resource
        ctx.require_resource(Application)

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
            async def start(self, ctx: Context) -> None:
                app = require_resource(Application)
                app.router.add_route("GET", "/", ws_root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context() as ctx:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await AIOHTTPComponent(components=components, app=application, port=unused_tcp_port).start(
            ctx
        )

        # Ensure that the application got added as a resource
        ctx.require_resource(Application)

        async with websockets.connect(f"ws://localhost:{unused_tcp_port}") as ws:
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

    async with Context() as ctx, AsyncClient() as http:
        ctx.add_resource("foo")
        ctx.add_resource("bar", name="another")
        await AIOHTTPComponent(
            app=application, port=unused_tcp_port, middlewares=middlewares
        ).start(ctx)

        # Ensure that the application got added as a resource
        ctx.require_resource(Application)

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

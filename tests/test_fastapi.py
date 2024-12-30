from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from asgiref.typing import ASGI3Application, HTTPScope, WebSocketScope
from asphalt.core import (
    Component,
    ComponentStartError,
    Context,
    add_resource,
    get_resource_nowait,
    inject,
    resource,
    start_component,
)
from fastapi import FastAPI
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.websockets import WebSocket

from asphalt.web.fastapi import AsphaltDepends, FastAPIComponent

from .test_asgi3 import TextReplacerMiddleware

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("method", ["static", "dynamic"])
async def test_http(unused_tcp_port: int, method: str):
    async def root(
        request: Request,
        my_resource: str = AsphaltDepends(),
        another_resource: str = AsphaltDepends("another"),
    ) -> Response:
        get_resource_nowait(HTTPScope)
        get_resource_nowait(Request)
        return JSONResponse(
            {
                "message": request.query_params["param"],
                "my resource": my_resource,
                "another resource": another_resource,
            }
        )

    application = FastAPI()
    if method == "static":
        application.add_api_route("/", root)
        components = {}
    else:

        class RouteComponent(Component):
            @inject
            async def start(self, app: FastAPI = resource()) -> None:
                app.add_api_route("/", root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            FastAPIComponent,
            {
                "components": components,
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        asgi_app = get_resource_nowait(ASGI3Application)
        fastapi_app = get_resource_nowait(FastAPI)
        assert fastapi_app is asgi_app

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
    async def ws_root(
        websocket: WebSocket,
        my_resource: str = AsphaltDepends(),
        another_resource: str = AsphaltDepends("another"),
    ):
        get_resource_nowait(WebSocketScope)
        await websocket.accept()
        message = await websocket.receive_text()
        await websocket.send_json(
            {
                "message": f"Hello {message}",
                "my resource": my_resource,
                "another resource": another_resource,
            }
        )

    application = FastAPI()
    if method == "static":
        application.add_api_websocket_route("/ws", ws_root)
        components = {}
    else:

        class RouteComponent(Component):
            @inject
            async def start(self, app: FastAPI = resource()) -> None:
                app.add_api_websocket_route("/ws", ws_root)

        components = {"myroutes": {"type": RouteComponent}}

    async with Context():
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            FastAPIComponent,
            {
                "components": components,
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        asgi_app = get_resource_nowait(ASGI3Application)
        fastapi_app = get_resource_nowait(FastAPI)
        assert fastapi_app is asgi_app

        async with aconnect_ws(f"http://localhost:{unused_tcp_port}/ws") as ws:
            await ws.send_text("World")
            response = json.loads(await ws.receive_text())
            assert response == {
                "message": "Hello World",
                "my resource": "foo",
                "another resource": "bar",
            }


async def test_missing_type_annotation():
    async def bad_root(request: Request, bad_resource=AsphaltDepends()) -> Response:
        return Response("never seen")

    application = FastAPI()
    application.add_api_route("/", bad_root)

    async with Context():
        with pytest.raises(
            ComponentStartError,
            match="Dependency 'bad_resource' in endpoint / is missing a type annotation",
        ):
            await start_component(FastAPIComponent, {"app": application})


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

    async def root(request: Request) -> Response:
        return PlainTextResponse("Hello World")

    application = FastAPI()
    application.add_api_route("/", root)
    async with Context(), AsyncClient() as http:
        await start_component(
            FastAPIComponent,
            {"app": application, "port": unused_tcp_port, "middlewares": middlewares},
        )

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
        FastAPIComponent(middlewares=["foo"])


def test_bad_middleware_dict():
    with pytest.raises(TypeError, match=r"Middleware \(1\) is not callable"):
        FastAPIComponent(middlewares=[{"type": 1}])

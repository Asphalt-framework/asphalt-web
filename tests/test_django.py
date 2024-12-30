from __future__ import annotations

import pytest
from asgiref.typing import ASGI3Application
from asphalt.core import Context, add_resource, get_resource_nowait, start_component
from httpx import AsyncClient

try:
    from django.core.handlers.asgi import ASGIHandler

    from asphalt.web.django import DjangoComponent

    from .django_app.asgi import application
except ModuleNotFoundError:
    pytestmark = pytest.mark.skip("Django not available")
else:
    pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_http(unused_tcp_port: int):
    async with Context(), AsyncClient() as http:
        add_resource("foo")
        add_resource("bar", name="another")
        await start_component(
            DjangoComponent,
            {
                "app": application,
                "port": unused_tcp_port,
            },
        )

        # Ensure that the application got added as a resource
        asgi_app = get_resource_nowait(ASGI3Application)
        asgi_handler = get_resource_nowait(ASGIHandler)
        assert asgi_handler is asgi_app

        response = await http.get(
            f"http://127.0.0.1:{unused_tcp_port}", params={"param": "Hello World"}
        )
        response.raise_for_status()
        assert response.json() == {
            "message": "Hello World",
            "my resource": "foo",
            "another resource": "bar",
        }

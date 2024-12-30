from aiohttp.abc import Request
from aiohttp.web_app import Application
from aiohttp.web_response import Response
from asphalt.core import Component, inject, resource


async def root(request: Request) -> Response:
    return Response(text="Hello, world!")


class WebRootComponent(Component):
    @inject
    async def start(self, app: Application = resource()) -> None:
        app.router.add_route("GET", "/", root)

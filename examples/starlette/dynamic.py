from asphalt.core import Component, inject, resource
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


async def root(request: Request) -> Response:
    return PlainTextResponse("Hello, world!")


class WebRootComponent(Component):
    @inject
    async def start(self, app: Starlette = resource()) -> None:
        app.add_route("/", root)

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from asphalt.core import Component, Context, inject, resource


async def root(request: Request) -> Response:
    return PlainTextResponse("Hello, world!")


class WebRootComponent(Component):
    @inject
    async def start(self, ctx: Context, app: Starlette = resource()) -> None:
        app.add_route("/", root)

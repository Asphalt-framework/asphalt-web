from asphalt.core import Component, get_resource_nowait
from litestar import Litestar, get


@get("/")
async def root() -> str:
    return "Hello, world!"


class WebRootComponent(Component):
    async def start(self) -> None:
        get_resource_nowait(Litestar).register(root)

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Sequence
from inspect import iscoroutinefunction
from typing import Any

from aiohttp.web_app import Application
from aiohttp.web_middlewares import middleware
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_runner import AppRunner, TCPSite

from asphalt.core import (
    ContainerComponent,
    Context,
    context_teardown,
    resolve_reference,
)


@middleware
async def asphalt_middleware(request: Request, handler: Callable[..., Awaitable]) -> Response:
    async with Context() as ctx:
        ctx.add_resource(request, types=[Request])
        return await handler(request)


class AIOHTTPComponent(ContainerComponent):
    """
    A component that serves an aiohttp application.

    :param app: the application object, or a module:varname reference to one
    :param host: the IP address to bind to
    :param port: the port to bind to
    :param middlewares: list of compatible coroutine functions or dicts to be added as
        middleware using :meth:`add_middleware`
    """

    def __init__(
        self,
        components: dict[str, dict[str, Any] | None] | None = None,
        *,
        app: Application | str | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        middlewares: Sequence[Callable[..., Coroutine[Any, Any, Any]] | dict[str, Any]] = (),
    ) -> None:
        super().__init__(components)

        self.app = resolve_reference(app) or Application()
        self.host = host
        self.port = port

        self.add_middleware(asphalt_middleware)
        for mw in middlewares:
            self.add_middleware(mw)

    def add_middleware(
        self, middleware: Callable[..., Coroutine[Any, Any, Any]] | dict[str, Any]
    ) -> None:
        """
        Add middleware to the application.

        :param middleware: either a special coroutine function (as specified here_), or
            a dictionary containing a reference to a setup function. This dictionary
            must contain the key ``type`` which is a non-async callable (or a
            module:varname reference to one) and which will be called with the
            application object as the first positional argument and the rest of the keys
            in the dict as keyword arguments.

        .. _here: \
https://docs.aiohttp.org/en/stable/web_advanced.html#aiohttp-web-middlewares

        """
        if isinstance(middleware, dict):
            setup = resolve_reference(middleware.pop("type", None))
            if not callable(setup):
                raise TypeError(f"Setup function ({setup}) is not callable")

            setup(self.app, **middleware)
        elif iscoroutinefunction(middleware):
            self.app.middlewares.append(middleware)
        else:
            raise TypeError(
                f"middleware must be either a coroutine function or a dict, not {middleware!r}"
            )

    async def start(self, ctx: Context) -> None:
        ctx.add_resource(self.app)
        await super().start(ctx)
        await self.start_server(ctx)

    @context_teardown
    async def start_server(self, ctx: Context) -> AsyncGenerator[None, Exception | None]:
        """
        Start the HTTP server.

        This method is called by the component after the subcomponents have been
        started. If you need to add any middleware that requires resources provided by
        subcomponents, you can override this method and call the superclass
        implementation after the middleware has been added.

        """
        runner = AppRunner(self.app)
        await runner.setup()
        site = TCPSite(runner, host=self.host, port=self.port)
        await site.start()

        yield

        await runner.cleanup()

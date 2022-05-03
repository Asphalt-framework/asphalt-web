from __future__ import annotations

from asyncio import create_task, sleep
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from inspect import isfunction
from typing import Any, Generic, TypeVar

import uvicorn
from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    HTTPScope,
    Scope,
    WebSocketScope,
)
from asphalt.core import (
    ContainerComponent,
    Context,
    context_teardown,
    resolve_reference,
)
from uvicorn import Config

T_Application = TypeVar("T_Application", bound=ASGI3Application)


@dataclass
class AsphaltMiddleware:
    """
    Generic ASGI middleware for Asphalt integration.

    This middleware wraps both HTTP requests and websocket connections in their own
    contexts and exposes the ASGI scope object as a resource.

    :param asgiref.typing.ASGI3Application app: an ASGI 3.0 application
    """

    app: ASGI3Application

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        if scope["type"] in ("http", "websocket"):
            async with Context() as ctx:
                scope_type = HTTPScope if scope["type"] == "http" else WebSocketScope
                ctx.add_resource(scope, types=[scope_type])
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class ASGIComponent(ContainerComponent, Generic[T_Application]):
    """
    A component that serves the given ASGI 3.0 application via Uvicorn.

    :param app: the ASGI application to serve, or a module:varname reference to one
    :type app: asgiref.typing.ASGI3Application | None
    :param host: the IP address to bind to
    :param port: the port to bind to
    :param middlewares: list of callables or dicts to be added as middleware using
        :meth:`add_middleware`
    """

    def __init__(
        self,
        components: dict[str, dict[str, Any] | None] = None,
        *,
        app: T_Application,
        host: str = "127.0.0.1",
        port: int = 8000,
        middlewares: Sequence[Callable[..., ASGI3Application] | dict[str, Any]] = (),
    ) -> None:
        super().__init__(components)
        self.app: T_Application = resolve_reference(app)
        self.original_app = app
        self.host = host
        self.port = port

        self.add_middleware(self.setup_asphalt_middleware)
        for middleware in middlewares:
            self.add_middleware(middleware)

    def setup_asphalt_middleware(self, app: T_Application) -> ASGI3Application:
        return AsphaltMiddleware(app)

    def add_middleware(
        self, middleware: Callable[..., ASGI3Application] | dict[str, Any]
    ) -> None:
        """
        Add middleware to the application.

        :param middleware: either a callable that takes the application object and
            returns an ASGI 3.0 application, or a dictionary containing a reference to
            such a callable. This dictionary must contain the key ``type`` which is a
            non-async callable (or a module:varname reference to one) and which will be
            called with the application object as the first positional argument and the
            rest of the keys in the dict as keyword arguments.

        """
        if isinstance(middleware, dict):
            type_ = resolve_reference(middleware.pop("type", None))
            if not callable(type_):
                raise TypeError(f"Middleware ({type_}) is not callable")

            self.app = type_(self.app, **middleware)
        elif callable(middleware):
            self.app = middleware(self.app)
        else:
            raise TypeError(
                f"middleware must be either a callable or a dict, not {middleware!r}"
            )

    @context_teardown
    async def start(self, ctx: Context):
        config = Config(
            app=self.app,
            host=self.host,
            port=self.port,
            use_colors=False,
            log_config=None,
            lifespan="off",
        )

        types = [ASGI3Application]
        if not isfunction(self.original_app):
            types.append(type(self.original_app))

        ctx.add_resource(self.original_app, types=types)
        await super().start(ctx)

        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        server_task = create_task(server.serve())
        while not server.started:
            await sleep(0)

        yield

        server.should_exit = True
        await server_task

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from asgiref.typing import ASGI3Application, HTTPScope, WebSocketScope
from asphalt.core import Context, add_resource, get_resource_nowait, resolve_reference
from litestar import Litestar, Request
from litestar.middleware import AbstractMiddleware
from litestar.types import ControllerRouterHandler, Receive, Scope, Send

from asphalt.web.asgi3 import ASGIComponent


@dataclass(frozen=True)
class AsphaltProvide:
    """
    Asphalt's version of Litestar's :func:`~litestar.di.Provide`.

    This should be marked as the default value on a parameter that should receive an
    Asphalt resource.

    :param cls: the type of the resource
    :param name: the name of the resource within its unique type

    """

    cls: type
    name: str = "default"

    async def __call__(self) -> Any:
        return get_resource_nowait(self.cls, self.name)


class AsphaltMiddleware(AbstractMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with Context():
            if scope["type"] == "http":
                add_resource(scope, types=[HTTPScope])
                add_resource(Request(scope))
            elif scope["type"] == "websocket":
                add_resource(scope, types=[WebSocketScope])
                add_resource(Request(scope))

            await self.app(scope, receive, send)


class LitestarComponent(ASGIComponent[Litestar]):
    """
    A component that serves a Litestar application.

    :param host: the IP address to bind to
    :param port: the port to bind to
    :param route_handlers: list of callables or module:varname references that point
        to the routers / controolers / handlers that should be attached to the
        application
    :param middlewares: list of callables or dicts to be added as middleware using
        :meth:`add_middleware`

    .. note::
        The following options are preset here:

        * ``debug``: set to the value of
          `__debug__ <https://docs.python.org/3/library/constants.html#debug__>`_;
          unless overridden
        * ``logging_config``:  always set to ``None``, as Asphalt handles logging
          configuration

        If you supply the a pre-made application object that has route handlers already
        in it, know that any middleware added to it during the initialization of
        :class:`LitestarComponent` will **NOT** apply to the route handlers previously
        added to the application

    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        route_handlers: Sequence[ControllerRouterHandler | str] = (),
        middlewares: Sequence[Callable[..., ASGI3Application] | dict[str, Any]] = (),
        config: dict[str, Any] | None = None,
    ) -> None:
        config_ = config or {}
        config_.setdefault("debug", __debug__)
        config_["logging_config"] = None
        app = Litestar(**config_)
        super().__init__(app=app, middlewares=middlewares, host=host, port=port)

        for item in route_handlers:
            if isinstance(item, str):
                handler = resolve_reference(item)
            else:
                handler = item

            self.original_app.register(handler)

    def setup_asphalt_middleware(self, app: Litestar) -> ASGI3Application:
        return AsphaltMiddleware(app=app)

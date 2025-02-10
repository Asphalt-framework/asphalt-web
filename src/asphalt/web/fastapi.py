from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from inspect import Signature, signature
from typing import Any, get_type_hints

from asgiref.typing import ASGI3Application
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute

from asphalt.core import Context, require_resource, resolve_reference

from .asgi3 import ASGIComponent
from .starlette import AsphaltMiddleware


@dataclass
class _AsphaltDependency:
    name: str
    cls: type = field(init=False)

    async def __call__(self):
        return require_resource(self.cls, self.name)

    def __hash__(self) -> int:
        return hash((self.name, self.cls))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, _AsphaltDependency):
            return self.name == other.name and self.cls == other.cls

        return NotImplemented


def AsphaltDepends(name: str = "default") -> Any:
    """
    Asphalt's version of FastAPI's :func:`~fastapi.Depends`.

    This should be marked as the default value on a parameter that should receive an
    Asphalt resource.

    :param name: the name of the resource within its unique type

    """
    return Depends(_AsphaltDependency(name))


class FastAPIComponent(ASGIComponent[FastAPI]):
    """
    A component that serves a FastAPI application.

    :param app: the FastAPI application object, or a module:varname reference to one
    :param host: the IP address to bind to
    :param port: the port to bind to
    :param debug: whether to enable debug mode in an implicitly created application
        (default: the value of
        `__debug__ <https://docs.python.org/3/library/constants.html#debug__>`_;
        ignored if an application object is explicitly passed in)
    :param middlewares: list of callables or dicts to be added as middleware using
        :meth:`add_middleware`
    """

    def __init__(
        self,
        components: dict[str, dict[str, Any] | None] | None = None,
        *,
        app: FastAPI | str | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        debug: bool | None = None,
        middlewares: Sequence[Callable[..., ASGI3Application] | dict[str, Any]] = (),
    ) -> None:
        debug = debug if isinstance(debug, bool) else __debug__
        super().__init__(
            components,
            app=app or FastAPI(debug=debug),
            host=host,
            port=port,
            middlewares=middlewares,
        )

    def setup_asphalt_middleware(self, app: FastAPI) -> ASGI3Application:
        return AsphaltMiddleware(app)

    def add_middleware(self, middleware: Callable[..., ASGI3Application] | dict[str, Any]) -> None:
        """
        Add a middleware to the application.

        Unlike the raw ASGI version of this method, this one adds the middleware to
        FastAPI's own middleware stack instead of wrapping the application directly.

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

            self.app.add_middleware(type_, **middleware)
        elif callable(middleware):
            self.app.add_middleware(middleware)
        else:
            raise TypeError(f"middleware must be either a callable or a dict, not {middleware!r}")

    async def start_server(self, ctx: Context) -> None:
        # Convert Asphalt dependencies into FastAPI dependencies
        for route in self.original_app.router.routes:
            if isinstance(route, (APIRoute, APIWebSocketRoute)):
                sig: Signature | None = None
                type_hints: dict[str, Any]
                for dependency in route.dependant.dependencies:
                    if isinstance(dependency.call, _AsphaltDependency):
                        if sig is None:
                            sig = signature(route.endpoint)
                            type_hints = get_type_hints(route.endpoint)

                        try:
                            annotation = type_hints[dependency.name]
                        except KeyError:
                            raise TypeError(
                                f"Dependency {dependency.name!r} in endpoint "
                                f"{route.path} is missing a type annotation"
                            ) from None

                        dependency.call.cls = annotation

        await super().start_server(ctx)

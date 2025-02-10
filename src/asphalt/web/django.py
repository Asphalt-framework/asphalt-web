from __future__ import annotations

from collections.abc import Awaitable, Callable

from asgiref.typing import ASGI3Application, HTTPScope
from django.core.handlers.asgi import ASGIHandler, ASGIRequest
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import async_only_middleware

from asphalt.core import Context

from .asgi3 import ASGIComponent


@async_only_middleware
def AsphaltMiddleware(get_response: Callable[[HttpRequest], Awaitable[HttpResponse]]):
    async def middleware(request: HttpRequest) -> HttpResponse:
        async with Context() as ctx:
            ctx.add_resource(request)
            if isinstance(request, ASGIRequest):
                ctx.add_resource(request.scope, types=[HTTPScope])

            return await get_response(request)

    return middleware


class DjangoComponent(ASGIComponent[ASGIHandler]):
    """
    A component that serves a Django application.

    :param django.core.handlers.asgi.ASGIHandler app: the Django ASGI handler object
    :param host: the IP address to bind to
    :param port: the port to bind to
    :param middlewares: list of callables or dicts to be added as middleware using
        :meth:`add_middleware`
    """

    def setup_asphalt_middleware(self, app: ASGIHandler) -> ASGI3Application:
        # In Django, the middleware must be explicitly added to MIDDLEWARE in
        # settings.py
        return app

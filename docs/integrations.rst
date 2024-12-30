Integrations
============

.. py:currentmodule:: asphalt.web

ASGI 3.0
--------

Component: ``asgi3`` (:class:`~.asgi3.ASGIComponent`)

Example: :github:`examples/asgi3`

This is a generic integration for ASGI 3.0 applications.

Resources available on the global context:

* the application object

  * type: `asgiref.typing.ASGI3Application`_
  * name: ``default``

Resources available to request handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.HTTPScope`_ or `asgiref.typing.WebSocketScope`_
  * name: ``default``

Django
------

Component: ``django`` (:class:`~.django.DjangoComponent`)

Requires manual insertion of the ``asphalt.web.django.AsphaltMiddleware`` middleware
to the ``MIDDLEWARE`` list in ``settings.py`` for resource injection to work.

Example: :github:`examples/django`

This integration is based on the ASGI 3.0 integration.

Resources available on the global context:

* the application object

  * type: `asgiref.typing.ASGI3Application`_ or `django.core.handlers.asgi.ASGIHandler`_
  * name: ``default``

Resources available to request handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.HTTPScope`_
  * name: ``default``
* the request object

  * type: `django.http.HttpRequest`_
  * name: ``default``

.. note:: Websocket support via Django Channels has not been implemented.

Starlette
---------

Component: ``starlette`` (:class:`~.starlette.StarletteComponent`)

Example: :github:`examples/starlette`

This integration is based on the ASGI 3.0 integration.

Resources available on the global context:

* the application object

  * type: `asgiref.typing.ASGI3Application`_ or `starlette.applications.Starlette`_
  * name: ``default``

Resources available to HTTP request handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.HTTPScope`_
  * name: ``default``
* the request object

  * type: `starlette.requests.Request`_
  * name: ``default``

Resources available to websocket handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.WebSocketScope`_
  * name: ``default``

.. _FastAPI:

FastAPI
-------

Component: ``fastapi`` (:class:`~.fastapi.FastAPIComponent`)

Example: :github:`examples/fastapi`

This integration is based on the ASGI 3.0 integration.

FastAPI has its own dependency injection system which means Asphalt resources must be
injected a bit differently in FastAPI endpoints. Instead of using
:func:`~fastapi.Depends` as the default value for a resource parameter you wish to
inject, you need to use :func:`~.fastapi.AsphaltDepends` instead. The
machinery in :class:`~.fastapi.FastAPIComponent` will handle the appropriate
translation.

Resources available on the global context:

* the application object

  * type: `asgiref.typing.ASGI3Application`_ or `fastapi.FastAPI`_
  * name: ``default``

Resources available to HTTP request handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.HTTPScope`_
  * name: ``default``
* the request object

  * type: `starlette.requests.Request`_
  * name: ``default``

Resources available to websocket handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.WebSocketScope`_
  * name: ``default``

Litestar
--------

Component: ``litestar`` (:class:`~.litestar.LitestarComponent`)

Example: :github:`examples/litestar`

This integration is based on the ASGI 3.0 integration.

Litestar has its own dependency injection system which can optionally be used to inject
Asphalt resources in web endpoints. This can be done by using
:class:`~asphalt.web.litestar.AsphaltProvide` instead of :class:`~litestar.di.Provide`::

    from asphalt.web.litestar import AsphaltProvide
    from litestar import get

    @get("/endpointname", dependencies={"myresource": AsphaltProvide(SomeConnection)})
    async def myendpoint(myresource: SomeConnection) -> None:
        ...

This would be roughly equivalent to::

    from asphalt.core import get_resource_nowait
    from litestar import get

    @get("/endpointname")
    async def myendpoint() -> None:
        myresource = get_resource_nowait(SomeConnection)
        ...

Resources available on the global context:

* the application object

  * type: `asgiref.typing.ASGI3Application`_ or `litestar.Litestar`_
  * name: ``default``

Resources available to HTTP request handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.HTTPScope`_
  * name: ``default``

* the request object

  * type: `litestar.Request`_
  * name: ``default``

  .. note::
    The request resource is created from the ASGI scope object by the Asphalt
    middleware, and does **NOT** share state with any request object provided by the
    Litestar framework

Resources available to websocket handlers:

* the ASGI scope of the request

  * type: `asgiref.typing.WebSocketScope`_
  * name: ``default``

AIOHTTP
-------

Component: ``aiohttp`` (:class:`~.aiohttp.AIOHTTPComponent`)

Example: :github:`examples/aiohttp`

Unlike the other frameworks supported here, AIOHTTP is not based on the ASGI standard.

Resources available on the global context:

* the application object

  * type: `aiohttp.web_app.Application`_
  * name: ``default``

Resources available to request handlers:

* the request object

  * type: `aiohttp.web_request.Request`_
  * name: ``default``

.. _asgiref.typing.ASGI3Application: https://asgi.readthedocs.io/en/latest/specs/main.html#applications
.. _asgiref.typing.HTTPScope: https://asgi.readthedocs.io/en/latest/specs/www.html#http-connection-scope
.. _asgiref.typing.WebSocketScope: https://asgi.readthedocs.io/en/latest/specs/www.html#websocket-connection-scope
.. _django.core.handlers.asgi.ASGIHandler: https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/#the-application-object
.. _django.http.HttpRequest: https://docs.djangoproject.com/en/3.2/ref/request-response/#httprequest-objects
.. _starlette.requests.Request: https://www.starlette.io/requests/
.. _starlette.applications.Starlette: https://www.starlette.io/applications/
.. _fastapi.FastAPI: https://fastapi.tiangolo.com/tutorial/first-steps/
.. _litestar.Request: https://docs.litestar.dev/latest/usage/requests.html
.. _litestar.Litestar: https://docs.litestar.dev/latest/usage/applications.html
.. _aiohttp.web_app.Application: https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.Application
.. _aiohttp.web_request.Request: https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.Request

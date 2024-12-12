Version history
===============

This library adheres to `Semantic Versioning 2.0 <http://semver.org/>`_.

**UNRELEASED**

- Migrated to Asphalt 5
- Dropped Python 3.8 support

**1.3.1**

- Fixed Starlette/FastAPI request resource being added under the wrong type since
  Starlette v0.28.0

**1.3.0**

- Dropped Python 3.7 support
- Added support for the Litestar framework

**1.2.1**

- Fixed unintentional change where the asgiref dependency was dropped from the
  ``fastapi``, ``django`` and ``starlette`` extras

**1.2.0**

- Dropped Python 3.7 support
- Fixed type annotations on ``start_server()``

**1.1.0**

- Added the ``start_server()`` method to all web components

**1.0.0**

- Initial release

from socket import socket

import pytest


@pytest.fixture
def unused_tcp_port() -> int:
    with socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]

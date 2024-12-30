from anyio import connect_tcp


async def ensure_server_running(host: str, port: int) -> None:
    # Try to connect until we succeed – then we know the server has started
    while True:
        try:
            await connect_tcp(host, port)
        except OSError:
            pass
        else:
            break

"""Keep application networking blocked while supporting Windows asyncio IPC."""

import socket
import sys

import pytest

# Captured during collection, before pytest-socket installs its per-test guard.
_NATIVE_SOCKET = socket.socket


def _event_loop_socketpair(*args, **kwargs):
    """A connected pair on an ephemeral numeric loopback address, never a service.

    CPython 3.11 on Windows implements socketpair with TCP loopback. Calling
    its usual implementation under pytest-socket fails at socket creation.
    This factory is limited to that IPC primitive; socket.socket and DNS stay
    guarded for application code throughout the test.
    """
    if args or kwargs:
        raise ValueError("Only the default event-loop socket pair is supported")
    listener = _NATIVE_SOCKET(socket.AF_INET, socket.SOCK_STREAM)
    client = None
    try:
        listener.settimeout(5)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = _NATIVE_SOCKET(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5)
        client.connect(listener.getsockname())
        # socket.socket.accept re-wraps the descriptor through the guarded
        # constructor. Use the native accept only inside this local factory.
        descriptor, _ = listener._accept()
        try:
            server = _NATIVE_SOCKET(socket.AF_INET, socket.SOCK_STREAM, fileno=descriptor)
        except BaseException:
            socket.close(descriptor)
            raise
        client.settimeout(None)
        server.settimeout(None)
        return server, client
    except BaseException:
        if client is not None:
            client.close()
        raise
    finally:
        listener.close()


@pytest.fixture(autouse=True)
def windows_event_loop_ipc(monkeypatch):
    if sys.platform == "win32":
        monkeypatch.setattr(socket, "socketpair", _event_loop_socketpair)

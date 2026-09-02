
from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:


    def _blocked(*args: object, **kwargs: object):
        raise RuntimeError(
            "A unit test tried to open a network connection. Unit tests must "
            "run against fakes - move this to tests/integration/ if it really "
            "needs a database."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

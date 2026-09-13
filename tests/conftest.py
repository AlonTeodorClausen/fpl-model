"""Offline by default; only explicitly selected live tests may use the network."""

import socket

import pytest


@pytest.fixture(autouse=True)
def block_network_for_offline_tests(request, monkeypatch):
    if request.node.get_closest_marker("live") is not None:
        return

    def blocked(*args, **kwargs):
        pytest.fail("Network access is forbidden in offline tests; mock the HTTP session")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


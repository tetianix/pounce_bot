import socket

import pytest
from curl_cffi import requests

from tests.conftest import NetworkBlocked


def test_socket_connection_is_blocked():
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 80), timeout=1)


def test_curl_cffi_request_is_blocked():
    with pytest.raises(NetworkBlocked):
        requests.get("https://www.olx.ua/")


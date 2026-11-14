import os
import socket
from pathlib import Path
from unittest.mock import create_autospec, patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKENtesttokenTESTTOKENtesttoken")

import httpx
import pytest
from aiogram import Bot
from curl_cffi import requests as curl_requests
from sqlalchemy import event

import db
from api_client import ApiClient
from models import Base
from tests.helpers import FakeApi

ROOT = Path(__file__).resolve().parent.parent
BLOCKED_CURL_FUNCTIONS = ("get", "post", "put", "patch", "delete", "head", "request")


class NetworkBlocked(RuntimeError):
    pass


def blocked(*args, **kwargs):
    raise NetworkBlocked("network is blocked in tests: replace it with unittest.mock.patch")


@pytest.fixture(autouse=True)
def no_network():
    patches = [
        patch.object(socket.socket, "connect", blocked),
        patch.object(socket.socket, "connect_ex", blocked),
        patch.object(socket, "getaddrinfo", blocked),
        patch.object(curl_requests.Session, "request", blocked),
    ]
    patches += [patch.object(curl_requests, name, blocked) for name in BLOCKED_CURL_FUNCTIONS]
    for item in patches:
        item.start()
    yield
    for item in reversed(patches):
        item.stop()


@pytest.fixture(autouse=True)
def memory_db():
    new_engine = db.make_engine("sqlite://")

    @event.listens_for(new_engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    engine = db.use_engine(new_engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def bot_namespace():
    path = ROOT / "bot.py"
    source = path.read_text(encoding="utf-8").replace("asyncio.run(main())", "")
    namespace = {}
    exec(compile(source, str(path), "exec"), namespace)
    return namespace


@pytest.fixture
def app(bot_namespace):
    bot_namespace["message_results"].clear()
    yield bot_namespace
    bot_namespace["message_results"].clear()


@pytest.fixture
def telegram(app):
    fake = create_autospec(Bot, instance=True)
    with patch.dict(app, {"bot": fake}):
        yield fake


@pytest.fixture
def fake_api(app):
    api = FakeApi()
    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(api.handle))
    with patch.dict(app, {"api": ApiClient(client)}), patch.dict(app, {"load_photo": lambda url: "photo"}):
        yield api

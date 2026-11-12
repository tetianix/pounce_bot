import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = "sqlite:///database.db"

engine = None
Session = sessionmaker(expire_on_commit=False)


def get_database_url():
    load_dotenv()
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def make_engine(url):
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite"):
        options = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            options["poolclass"] = StaticPool
        return create_engine(url, **options)
    return create_engine(url, pool_pre_ping=True)


def use_engine(new_engine):
    global engine
    if engine is not None and engine is not new_engine:
        engine.dispose()
    engine = new_engine
    Session.configure(bind=new_engine)
    return new_engine


def init_engine(url=None):
    return use_engine(make_engine(url or get_database_url()))


init_engine()

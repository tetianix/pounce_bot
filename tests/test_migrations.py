import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

import db
from models import Base
from tests.conftest import ROOT


@pytest.fixture
def connection():
    engine = db.make_engine("sqlite://")
    with engine.begin() as connection:
        yield connection
    engine.dispose()


@pytest.fixture
def alembic_config(connection):
    config = Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.attributes["connection"] = connection
    return config


def test_upgrade_creates_every_table_and_matches_models(connection, alembic_config):
    command.upgrade(alembic_config, "head")
    tables = set(inspect(connection).get_table_names())
    diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert tables == {"ads", "watches", "price_history", "favorites", "alembic_version"}
    assert diff == []


def test_downgrade_removes_tables(connection, alembic_config):
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    assert set(inspect(connection).get_table_names()) == {"alembic_version"}


def test_upgrade_twice_changes_nothing(connection, alembic_config):
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")
    assert "ads" in set(inspect(connection).get_table_names())

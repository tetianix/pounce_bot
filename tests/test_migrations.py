import unittest
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

import db
from models import Base

ROOT = Path(__file__).resolve().parent.parent


def alembic_config(connection):
    config = Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.attributes["connection"] = connection
    return config


class MigrationsTest(unittest.TestCase):
    def setUp(self):
        self.engine = db.make_engine("sqlite://")

    def tearDown(self):
        self.engine.dispose()

    def test_upgrade_creates_every_table_and_matches_models(self):
        with self.engine.begin() as connection:
            command.upgrade(alembic_config(connection), "head")
            tables = set(inspect(connection).get_table_names())
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        self.assertEqual(tables, {"ads", "watches", "price_history", "favorites", "alembic_version"})
        self.assertEqual(diff, [])

    def test_downgrade_removes_tables(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "head")
            command.downgrade(config, "base")
            tables = set(inspect(connection).get_table_names())
        self.assertEqual(tables, {"alembic_version"})

    def test_upgrade_twice_changes_nothing(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            tables = set(inspect(connection).get_table_names())
        self.assertIn("ads", tables)


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

import db
from models import Base
from scripts import migrate_sqlite_to_postgres as script

OLD_SCHEMA = """
CREATE TABLE ads(id TEXT NOT NULL, source TEXT NOT NULL, name TEXT NOT NULL, price INTEGER, town TEXT,
    published_date TEXT, link TEXT NOT NULL, query TEXT, first_seen TEXT, photo TEXT, PRIMARY KEY (source, id));
CREATE TABLE watches(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, query TEXT, max_price INTEGER,
    min_price INTEGER, is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT,
    UNIQUE(user_id, query, max_price, min_price));
CREATE TABLE price_history(id INTEGER PRIMARY KEY AUTOINCREMENT, ad_id TEXT NOT NULL, ad_source TEXT NOT NULL,
    price INTEGER NOT NULL, changed_at TEXT);
CREATE TABLE favorites(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, ad_id TEXT NOT NULL,
    ad_source TEXT NOT NULL, saved_at TEXT, UNIQUE(user_id, ad_id, ad_source));
"""


def run_quietly(function, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args)


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "old.db"
        connection = sqlite3.connect(path)
        connection.executescript(OLD_SCHEMA)
        for number in range(1, 8):
            connection.execute("INSERT INTO ads (id, source, name, price, link) VALUES (?, 'olx', ?, ?, 'l')",
                               (str(number), f"Ad {number}", number * 100))
        connection.execute("INSERT INTO watches (user_id, query, max_price, min_price, created_at) "
                           "VALUES (7000000000, 'диван', 0, 0, '2026-10-01')")
        connection.execute("INSERT INTO watches (user_id, query, max_price, min_price) VALUES (1, 'лампа', 0, 0)")
        connection.execute("DELETE FROM watches WHERE query = 'лампа'")
        connection.execute("INSERT INTO price_history (ad_id, ad_source, price) VALUES ('1', 'olx', 100)")
        connection.execute("INSERT INTO price_history (ad_id, ad_source, price) VALUES ('404', 'olx', 1)")
        connection.execute("INSERT INTO favorites (user_id, ad_id, ad_source) VALUES (1, '2', 'olx')")
        connection.commit()
        connection.close()
        self.source = db.make_engine(f"sqlite:///{path}")
        self.destination = db.make_engine("sqlite://")
        Base.metadata.create_all(self.destination)

    def tearDown(self):
        self.source.dispose()
        self.destination.dispose()
        self.tmp.cleanup()

    def rows(self, sql):
        with self.destination.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql))]

    def test_copies_rows_in_small_batches(self):
        run_quietly(script.migrate, self.source, self.destination, 3)
        self.assertEqual(self.rows("SELECT count(*) FROM ads"), [(7,)])
        self.assertEqual(self.rows("SELECT name, price FROM ads WHERE id = '3'"), [("Ad 3", 300)])
        self.assertEqual(self.rows("SELECT count(*) FROM favorites"), [(1,)])

    def test_old_schema_gets_defaults_for_new_columns(self):
        run_quietly(script.migrate, self.source, self.destination)
        self.assertEqual(self.rows("SELECT user_id, city, state, exact FROM watches"), [(7000000000, "", "", 0)])
        self.assertEqual(self.rows("SELECT currency, price_converted FROM ads WHERE id = '1'"), [(None, 0)])

    def test_orphan_history_row_is_skipped_and_reported(self):
        skipped = run_quietly(script.migrate, self.source, self.destination)
        self.assertEqual(skipped["price_history"], 1)
        self.assertEqual(self.rows("SELECT ad_id FROM price_history"), [("1",)])
        rows = script.compare_counts(self.source, self.destination, skipped)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(script.print_report(rows))

    def test_id_counter_is_kept_so_deleted_ids_are_not_reused(self):
        run_quietly(script.migrate, self.source, self.destination)
        with self.destination.begin() as connection:
            connection.execute(text("INSERT INTO watches (user_id, query, max_price, min_price) "
                                    "VALUES (2, 'стіл', 0, 0)"))
        self.assertEqual(self.rows("SELECT id FROM watches WHERE query = 'стіл'"), [(3,)])

    def test_refuses_non_empty_destination(self):
        run_quietly(script.migrate, self.source, self.destination)
        with self.assertRaises(script.MigrationError):
            run_quietly(script.migrate, self.source, self.destination)

    def test_refuses_destination_without_schema(self):
        empty = db.make_engine("sqlite://")
        with self.assertRaises(script.MigrationError):
            run_quietly(script.migrate, self.source, empty)
        empty.dispose()

    def test_failure_rolls_back_everything(self):
        with patch.object(script, "restore_id_counters", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                run_quietly(script.migrate, self.source, self.destination)
        self.assertEqual(self.rows("SELECT count(*) FROM ads"), [(0,)])
        self.assertEqual(self.rows("SELECT count(*) FROM watches"), [(0,)])


if __name__ == "__main__":
    unittest.main()

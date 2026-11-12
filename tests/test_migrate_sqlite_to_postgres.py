import sqlite3
from unittest.mock import patch

import pytest
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


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "old.db"
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
    engine = db.make_engine(f"sqlite:///{path}")
    yield engine
    engine.dispose()


@pytest.fixture
def destination():
    engine = db.make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def rows(engine, sql):
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


def test_copies_rows_in_small_batches(source, destination):
    script.migrate(source, destination, 3)
    assert rows(destination, "SELECT count(*) FROM ads") == [(7,)]
    assert rows(destination, "SELECT name, price FROM ads WHERE id = '3'") == [("Ad 3", 300)]
    assert rows(destination, "SELECT count(*) FROM favorites") == [(1,)]


def test_old_schema_gets_defaults_for_new_columns(source, destination):
    script.migrate(source, destination)
    assert rows(destination, "SELECT user_id, city, state, exact FROM watches") == [(7000000000, "", "", 0)]
    assert rows(destination, "SELECT currency, price_converted FROM ads WHERE id = '1'") == [(None, 0)]


def test_orphan_history_row_is_skipped_and_reported(source, destination):
    skipped = script.migrate(source, destination)
    assert skipped["price_history"] == 1
    assert rows(destination, "SELECT ad_id FROM price_history") == [("1",)]
    assert script.print_report(script.compare_counts(source, destination, skipped)) is True


def test_id_counter_is_kept_so_deleted_ids_are_not_reused(source, destination):
    script.migrate(source, destination)
    with destination.begin() as connection:
        connection.execute(text("INSERT INTO watches (user_id, query, max_price, min_price) "
                                "VALUES (2, 'стіл', 0, 0)"))
    assert rows(destination, "SELECT id FROM watches WHERE query = 'стіл'") == [(3,)]


def test_refuses_non_empty_destination(source, destination):
    script.migrate(source, destination)
    with pytest.raises(script.MigrationError):
        script.migrate(source, destination)


def test_refuses_destination_without_schema(source):
    empty = db.make_engine("sqlite://")
    with pytest.raises(script.MigrationError):
        script.migrate(source, empty)
    empty.dispose()


def test_failure_rolls_back_everything(source, destination):
    with patch.object(script, "restore_id_counters", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            script.migrate(source, destination)
    assert rows(destination, "SELECT count(*) FROM ads") == [(0,)]
    assert rows(destination, "SELECT count(*) FROM watches") == [(0,)]

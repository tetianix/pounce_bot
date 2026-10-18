import os
import sqlite3
import tempfile
import unittest

import database

OLD_WATCHES = '''
    CREATE TABLE watches(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    query TEXT,
    max_price INTEGER,
    min_price INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    UNIQUE(user_id, query, max_price, min_price))'''


def query(sql, params=()):
    connection = sqlite3.connect("database.db")
    rows = connection.execute(sql, params).fetchall()
    connection.close()
    return rows


class WatchMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def create_old_table(self):
        connection = sqlite3.connect("database.db")
        connection.execute(OLD_WATCHES)
        for user_id, text in [(1, "диван"), (1, "лампа"), (2, "диван"), (1, "стіл")]:
            connection.execute("INSERT INTO watches (user_id, query, max_price, min_price, is_active, created_at) "
                               "VALUES (?, ?, 500, 0, 1, '2026-10-01')", (user_id, text))
        connection.execute("DELETE FROM watches WHERE query = 'стіл'")
        connection.execute("UPDATE watches SET is_active = 0 WHERE query = 'лампа'")
        connection.commit()
        connection.close()

    def test_keeps_rows_and_adds_empty_filters(self):
        self.create_old_table()
        database.migrate_watch_filters()
        rows = query("SELECT id, user_id, query, max_price, min_price, is_active, created_at, city, state, exact "
                     "FROM watches ORDER BY id")
        self.assertEqual(rows, [
            (1, 1, "диван", 500, 0, 1, "2026-10-01", "", "", 0),
            (2, 1, "лампа", 500, 0, 0, "2026-10-01", "", "", 0),
            (3, 2, "диван", 500, 0, 1, "2026-10-01", "", "", 0),
        ])

    def test_keeps_id_counter_so_deleted_ids_are_not_reused(self):
        self.create_old_table()
        database.migrate_watch_filters()
        database.save_watch(5, "крісло", None, None)
        self.assertEqual(query("SELECT id FROM watches WHERE query = 'крісло'"), [(5,)])

    def test_same_query_in_different_cities_are_separate_watches(self):
        self.create_old_table()
        database.migrate_watch_filters()
        database.save_watch(1, "диван", 500, None, city="kyiv")
        database.save_watch(1, "диван", 500, None, city="lviv", state="used", exact=True)
        database.save_watch(1, "диван", 500, None, city="lviv", state="used", exact=True)
        rows = query("SELECT city, state, exact FROM watches WHERE user_id = 1 AND query = 'диван' ORDER BY id")
        self.assertEqual(rows, [("", "", 0), ("kyiv", "", 0), ("lviv", "used", 1)])

    def test_delete_user_watch_matches_all_filters(self):
        self.create_old_table()
        database.migrate_watch_filters()
        database.save_watch(1, "диван", 500, None, city="kyiv")
        database.delete_user_watch(1, "диван", 500, None, city="kyiv")
        rows = query("SELECT city FROM watches WHERE user_id = 1 AND query = 'диван'")
        self.assertEqual(rows, [("",)])

    def test_second_run_changes_nothing(self):
        self.create_old_table()
        database.migrate_watch_filters()
        database.save_watch(1, "шафа", None, None, city="odesa")
        before = query("SELECT * FROM watches ORDER BY id")
        database.migrate_watch_filters()
        self.assertEqual(query("SELECT * FROM watches ORDER BY id"), before)

    def test_new_database_already_has_filters(self):
        database.create_watches_table()
        database.migrate_watch_filters()
        database.save_watch(1, "шафа", None, None, state="new")
        self.assertEqual(query("SELECT city, state, exact FROM watches"), [("", "new", 0)])


if __name__ == "__main__":
    unittest.main()

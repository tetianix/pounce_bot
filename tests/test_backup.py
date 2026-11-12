import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.engine import make_url

from scripts import backup_db


class BackupTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        patcher = patch.object(backup_db, "BACKUP_DIR", self.dir / "backups")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)


class SqliteBackupTest(BackupTestCase):
    def make_database(self):
        path = self.dir / "source.db"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE ads (id TEXT)")
        connection.execute("INSERT INTO ads VALUES ('1')")
        connection.commit()
        connection.close()
        return path

    def test_copies_database_with_data(self):
        path = self.make_database()
        with patch.object(backup_db.db, "get_database_url", return_value=f"sqlite:///{path}"):
            target = backup_db.backup()
        self.assertEqual(target.name, f"database-{datetime.now():%Y-%m-%d}.db")
        connection = sqlite3.connect(target)
        self.assertEqual(connection.execute("SELECT id FROM ads").fetchall(), [("1",)])
        connection.close()

    def test_missing_database_is_an_error(self):
        with patch.object(backup_db.db, "get_database_url", return_value=f"sqlite:///{self.dir / 'nope.db'}"):
            with self.assertRaises(FileNotFoundError):
                backup_db.backup()

    def test_relative_sqlite_path_is_resolved_from_project_root(self):
        self.assertEqual(backup_db.sqlite_path(make_url("sqlite:///database.db")), backup_db.ROOT / "database.db")

    def test_keeps_only_latest_backups_of_the_same_kind(self):
        (self.dir / "backups").mkdir()
        for day in range(1, 21):
            (self.dir / "backups" / f"database-2026-10-{day:02d}.db").write_text("x")
        (self.dir / "backups" / "database-2026-10-01.dump").write_text("x")
        removed = backup_db.remove_old(".db")
        self.assertEqual(removed, 6)
        self.assertEqual(len(list((self.dir / "backups").glob("*.db"))), backup_db.KEEP)
        self.assertEqual(len(list((self.dir / "backups").glob("*.dump"))), 1)


class PostgresBackupTest(BackupTestCase):
    URL = "postgresql+psycopg://bot:secret@db.example.com:5433/pounce?sslmode=require"

    def run_backup(self, run):
        with patch.object(backup_db.db, "get_database_url", return_value=self.URL), \
                patch.object(backup_db.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
                patch.object(backup_db.subprocess, "run", side_effect=run) as mocked:
            return backup_db.backup(), mocked

    def test_runs_pg_dump_with_password_in_environment_only(self):
        def run(command, **kwargs):
            if command[0].endswith("pg_dump"):
                Path(command[command.index("--file") + 1]).write_text("dump")
            return subprocess.CompletedProcess(command, 0, "", "")

        target, mocked = self.run_backup(run)
        self.assertEqual(target.name, f"database-{datetime.now():%Y-%m-%d}.dump")
        dump_command = mocked.call_args_list[0].args[0]
        self.assertEqual(dump_command[0], "/usr/bin/pg_dump")
        for expected in ("--dbname", "pounce", "--host", "db.example.com", "--port", "5433", "--username", "bot"):
            self.assertIn(expected, dump_command)
        self.assertNotIn("secret", " ".join(dump_command))
        self.assertEqual(mocked.call_args_list[0].kwargs["env"]["PGPASSWORD"], "secret")
        self.assertEqual(mocked.call_args_list[0].kwargs["env"]["PGSSLMODE"], "require")
        self.assertEqual(mocked.call_args_list[1].args[0][:2], ["/usr/bin/pg_restore", "--list"])

    def test_unreadable_dump_is_removed_and_reported(self):
        def run(command, **kwargs):
            if command[0].endswith("pg_dump"):
                Path(command[command.index("--file") + 1]).write_text("broken")
                return subprocess.CompletedProcess(command, 0, "", "")
            raise subprocess.CalledProcessError(1, command, stderr="not a valid archive")

        with self.assertRaises(RuntimeError) as caught:
            self.run_backup(run)
        self.assertIn("not a valid archive", str(caught.exception))
        self.assertEqual(list((self.dir / "backups").glob("*.dump")), [])

    def test_failed_pg_dump_is_reported(self):
        def run(command, **kwargs):
            raise subprocess.CalledProcessError(1, command, stderr="connection refused")

        with self.assertRaises(RuntimeError) as caught:
            self.run_backup(run)
        self.assertIn("connection refused", str(caught.exception))

    def test_missing_pg_dump_has_clear_message(self):
        with patch.object(backup_db.db, "get_database_url", return_value=self.URL), \
                patch.object(backup_db.shutil, "which", return_value=None):
            with self.assertRaises(FileNotFoundError) as caught:
                backup_db.backup()
        self.assertIn("pg_dump", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

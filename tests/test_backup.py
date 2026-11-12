import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.engine import make_url

from scripts import backup_db

TODAY = f"{datetime.now():%Y-%m-%d}"
POSTGRES_URL = "postgresql+psycopg://bot:secret@db.example.com:5433/pounce?sslmode=require"


@pytest.fixture
def backup_dir(tmp_path):
    with patch.object(backup_db, "BACKUP_DIR", tmp_path / "backups"):
        yield tmp_path / "backups"


@pytest.fixture
def use_url():
    def apply(url):
        return patch.object(backup_db.db, "get_database_url", return_value=url)

    return apply


@pytest.fixture
def sqlite_file(tmp_path):
    path = tmp_path / "source.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE ads (id TEXT)")
    connection.execute("INSERT INTO ads VALUES ('1')")
    connection.commit()
    connection.close()
    return path


def test_sqlite_backup_copies_database_with_data(backup_dir, use_url, sqlite_file):
    with use_url(f"sqlite:///{sqlite_file}"):
        target = backup_db.backup()
    assert target.name == f"database-{TODAY}.db"
    connection = sqlite3.connect(target)
    assert connection.execute("SELECT id FROM ads").fetchall() == [("1",)]
    connection.close()


def test_sqlite_missing_database_is_an_error(backup_dir, use_url, tmp_path):
    with use_url(f"sqlite:///{tmp_path / 'nope.db'}"), pytest.raises(FileNotFoundError):
        backup_db.backup()


def test_relative_sqlite_path_is_resolved_from_project_root():
    assert backup_db.sqlite_path(make_url("sqlite:///database.db")) == backup_db.ROOT / "database.db"


def test_keeps_only_latest_backups_of_the_same_kind(backup_dir):
    backup_dir.mkdir()
    for day in range(1, 21):
        (backup_dir / f"database-2026-10-{day:02d}.db").write_text("x")
    (backup_dir / "database-2026-10-01.dump").write_text("x")
    assert backup_db.remove_old(".db") == 6
    assert len(list(backup_dir.glob("*.db"))) == backup_db.KEEP
    assert len(list(backup_dir.glob("*.dump"))) == 1


@pytest.fixture
def postgres_tools(backup_dir, use_url):
    with use_url(POSTGRES_URL), \
            patch.object(backup_db.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
            patch.object(backup_db.subprocess, "run") as run:
        yield run


def fake_dump_file(command):
    if command[0].endswith("pg_dump"):
        Path(command[command.index("--file") + 1]).write_text("dump")
    return subprocess.CompletedProcess(command, 0, "", "")


def test_postgres_runs_pg_dump_with_password_in_environment_only(postgres_tools):
    postgres_tools.side_effect = lambda command, **kwargs: fake_dump_file(command)
    target = backup_db.backup()
    assert target.name == f"database-{TODAY}.dump"
    dump_call, restore_call = postgres_tools.call_args_list
    dump_command = dump_call.args[0]
    assert dump_command[0] == "/usr/bin/pg_dump"
    for expected in ("--dbname", "pounce", "--host", "db.example.com", "--port", "5433", "--username", "bot"):
        assert expected in dump_command
    assert "secret" not in " ".join(dump_command)
    assert dump_call.kwargs["env"]["PGPASSWORD"] == "secret"
    assert dump_call.kwargs["env"]["PGSSLMODE"] == "require"
    assert restore_call.args[0][:2] == ["/usr/bin/pg_restore", "--list"]


def test_postgres_unreadable_dump_is_removed_and_reported(postgres_tools, backup_dir):
    def run(command, **kwargs):
        if command[0].endswith("pg_dump"):
            return fake_dump_file(command)
        raise subprocess.CalledProcessError(1, command, stderr="not a valid archive")

    postgres_tools.side_effect = run
    with pytest.raises(RuntimeError, match="not a valid archive"):
        backup_db.backup()
    assert list(backup_dir.glob("*.dump")) == []


def test_postgres_failed_pg_dump_is_reported(postgres_tools):
    postgres_tools.side_effect = subprocess.CalledProcessError(1, ["/usr/bin/pg_dump"], stderr="connection refused")
    with pytest.raises(RuntimeError, match="connection refused"):
        backup_db.backup()


def test_postgres_missing_pg_dump_has_clear_message(backup_dir, use_url):
    with use_url(POSTGRES_URL), patch.object(backup_db.shutil, "which", return_value=None):
        with pytest.raises(FileNotFoundError, match="pg_dump"):
            backup_db.backup()

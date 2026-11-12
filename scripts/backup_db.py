import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy.engine import make_url

import db

BACKUP_DIR = ROOT / "backups"
KEEP = 14


def backup_sqlite(database, target):
    if not database.exists():
        raise FileNotFoundError(f"database not found: {database}")
    source = sqlite3.connect(database)
    destination = sqlite3.connect(target)
    with destination:
        source.backup(destination)
    source.close()
    status = destination.execute("PRAGMA integrity_check").fetchone()[0]
    destination.close()
    if status != "ok":
        target.unlink()
        raise RuntimeError(f"backup is corrupted: {status}")


def require_tool(name):
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(f"{name} not found: install the PostgreSQL client tools")
    return path


def backup_postgres(url, target):
    pg_dump = require_tool("pg_dump")
    pg_restore = require_tool("pg_restore")
    command = [pg_dump, "--format=custom", "--no-owner", "--file", str(target), "--dbname", url.database]
    if url.host:
        command += ["--host", url.host]
    if url.port:
        command += ["--port", str(url.port)]
    if url.username:
        command += ["--username", url.username]
    environment = dict(os.environ)
    if url.password:
        environment["PGPASSWORD"] = url.password
    if url.query.get("sslmode"):
        environment["PGSSLMODE"] = url.query["sslmode"]
    try:
        subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
        subprocess.run([pg_restore, "--list", str(target)], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"{Path(error.cmd[0]).name} failed: {error.stderr.strip()}") from error


def sqlite_path(url):
    path = Path(url.database or "")
    return path if path.is_absolute() else ROOT / path


def backup():
    url = make_url(db.get_database_url())
    BACKUP_DIR.mkdir(exist_ok=True)
    if url.get_backend_name() == "sqlite":
        suffix = ".db"
        target = BACKUP_DIR / f"database-{datetime.now():%Y-%m-%d}{suffix}"
        backup_sqlite(sqlite_path(url), target)
    elif url.get_backend_name() == "postgresql":
        suffix = ".dump"
        target = BACKUP_DIR / f"database-{datetime.now():%Y-%m-%d}{suffix}"
        backup_postgres(url, target)
    else:
        raise RuntimeError(f"unsupported database: {url.get_backend_name()}")
    return target


def remove_old(suffix):
    backups = sorted(BACKUP_DIR.glob(f"database-*{suffix}"))
    for old in backups[:-KEEP]:
        old.unlink()
    return len(backups[:-KEEP])


if __name__ == "__main__":
    target = backup()
    removed = remove_old(target.suffix)
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} saved {target.name} ({target.stat().st_size} bytes), removed {removed} old")

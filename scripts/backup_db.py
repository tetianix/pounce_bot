import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "database.db"
BACKUP_DIR = ROOT / "backups"
KEEP = 14


def backup():
    if not DATABASE.exists():
        raise FileNotFoundError(f"database not found: {DATABASE}")
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"database-{datetime.now():%Y-%m-%d}.db"
    source = sqlite3.connect(DATABASE)
    destination = sqlite3.connect(target)
    with destination:
        source.backup(destination)
    source.close()
    status = destination.execute("PRAGMA integrity_check").fetchone()[0]
    destination.close()
    if status != "ok":
        target.unlink()
        raise RuntimeError(f"backup is corrupted: {status}")
    return target


def remove_old():
    backups = sorted(BACKUP_DIR.glob("database-*.db"))
    for old in backups[:-KEEP]:
        old.unlink()
    return len(backups[:-KEEP])


if __name__ == "__main__":
    target = backup()
    removed = remove_old()
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} saved {target.name} ({target.stat().st_size} bytes), removed {removed} old")

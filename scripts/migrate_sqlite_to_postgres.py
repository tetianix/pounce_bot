import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, inspect, insert, select, text

import db
from models import Base

BATCH_SIZE = 500
TABLE_ORDER = ["ads", "watches", "price_history", "favorites"]
FOREIGN_KEY_TABLES = {"price_history", "favorites"}


class MigrationError(Exception):
    pass


def count_rows(connection, table):
    return connection.execute(select(func.count()).select_from(table)).scalar_one()


def source_columns(source, table):
    existing = {column["name"] for column in inspect(source).get_columns(table.name)}
    return [column for column in table.columns if column.name in existing]


def source_counters(source):
    exists = source.execute(text("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'")).first()
    if exists is None:
        return {}
    return dict(source.execute(text("SELECT name, seq FROM sqlite_sequence")).all())


def orphan_filter(source, table):
    ads = Base.metadata.tables["ads"]
    known = {(row.source, row.id) for row in source.execute(select(ads.c.source, ads.c.id))}
    return lambda row: (row["ad_source"], row["ad_id"]) in known


def copy_table(source, destination, table, batch_size):
    columns = source_columns(source, table)
    keep = orphan_filter(source, table) if table.name in FOREIGN_KEY_TABLES else (lambda row: True)
    copied = skipped = 0
    batch = []
    result = source.execute(select(*columns).order_by(*table.primary_key.columns))
    for row in result.mappings():
        row = dict(row)
        if not keep(row):
            skipped += 1
            continue
        batch.append(row)
        if len(batch) >= batch_size:
            destination.execute(insert(table), batch)
            copied += len(batch)
            batch = []
    if batch:
        destination.execute(insert(table), batch)
        copied += len(batch)
    return copied, skipped


def restore_id_counters(destination, counters):
    for name in ("watches", "price_history", "favorites"):
        table = Base.metadata.tables[name]
        highest = destination.execute(select(func.max(table.c.id))).scalar_one() or 0
        value = max(highest, counters.get(name, 0))
        if value == 0:
            continue
        if destination.dialect.name == "postgresql":
            destination.execute(text("SELECT setval(pg_get_serial_sequence(:table, 'id'), :value, true)"),
                                {"table": name, "value": value})
        else:
            destination.execute(text("DELETE FROM sqlite_sequence WHERE name = :table"), {"table": name})
            destination.execute(text("INSERT INTO sqlite_sequence (name, seq) VALUES (:table, :value)"),
                                {"table": name, "value": value})


def check_destination(destination):
    tables = set(inspect(destination).get_table_names())
    missing = [name for name in TABLE_ORDER if name not in tables]
    if missing:
        raise MigrationError(f"destination has no tables {', '.join(missing)}: run `alembic upgrade head` first")
    filled = [name for name in TABLE_ORDER if count_rows(destination, Base.metadata.tables[name])]
    if filled:
        raise MigrationError(f"destination tables are not empty: {', '.join(filled)}")


def migrate(source_engine, destination_engine, batch_size=BATCH_SIZE):
    skipped = {}
    with source_engine.connect() as source, destination_engine.begin() as destination:
        check_destination(destination)
        counters = source_counters(source)
        for name in TABLE_ORDER:
            table = Base.metadata.tables[name]
            copied, skipped_rows = copy_table(source, destination, table, batch_size)
            skipped[name] = skipped_rows
            print(f"{name}: copied {copied}" + (f", skipped {skipped_rows} without parent ad" if skipped_rows else ""))
        restore_id_counters(destination, counters)
    return skipped


def compare_counts(source_engine, destination_engine, skipped):
    rows = []
    with source_engine.connect() as source, destination_engine.connect() as destination:
        for name in TABLE_ORDER:
            table = Base.metadata.tables[name]
            rows.append((name, count_rows(source, table), count_rows(destination, table), skipped.get(name, 0)))
    return rows


def print_report(rows):
    print()
    print(f"{'table':<15}{'source':>10}{'destination':>13}{'skipped':>9}  status")
    ok = True
    for name, source_count, destination_count, skipped in rows:
        good = source_count - skipped == destination_count
        ok = ok and good
        print(f"{name:<15}{source_count:>10}{destination_count:>13}{skipped:>9}  {'OK' if good else 'MISMATCH'}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Copy all data from a SQLite file to the database in DATABASE_URL")
    parser.add_argument("--source", default=str(ROOT / "database.db"), help="path to the SQLite file")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        sys.exit(f"source not found: {source_path}")
    destination_engine = db.make_engine(db.get_database_url())
    source_engine = db.make_engine(f"sqlite:///{source_path.resolve()}")
    if destination_engine.url.drivername.startswith("sqlite") and \
            destination_engine.url.database and Path(destination_engine.url.database).resolve() == source_path.resolve():
        sys.exit("DATABASE_URL points to the same file as the source: set DATABASE_URL to the PostgreSQL address")

    try:
        skipped = migrate(source_engine, destination_engine, args.batch_size)
    except MigrationError as error:
        sys.exit(str(error))
    if not print_report(compare_counts(source_engine, destination_engine, skipped)):
        sys.exit("row counts differ: check the table above")


if __name__ == "__main__":
    main()

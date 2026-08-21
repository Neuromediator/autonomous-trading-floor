import sqlite3
import time

import pytest

import backend.database as database


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """A database of the same shape, so pruning runs against real SQL."""
    path = str(tmp_path / "test.db")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, "
            "datetime DATETIME, type TEXT, message TEXT)"
        )
        conn.execute("CREATE TABLE searches (query TEXT PRIMARY KEY, response TEXT, fetched_at REAL)")
        conn.commit()
    monkeypatch.setattr(database, "DB", path)
    return path


def add_log(path, days_ago):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO logs (name, datetime, type, message) "
            "VALUES ('warren', datetime('now', ?), 'trace', 'x')",
            (f"-{days_ago} days",),
        )
        conn.commit()


def add_search(path, days_ago):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO searches (query, response, fetched_at) VALUES (?, 'x', ?)",
            (f"q{days_ago}", time.time() - days_ago * 86400),
        )
        conn.commit()


def count(path, table):
    with sqlite3.connect(path) as conn:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_prunes_only_what_is_past_retention(temp_db, monkeypatch):
    monkeypatch.setattr(database, "LOG_RETENTION_DAYS", 90)
    monkeypatch.setattr(database, "SEARCH_RETENTION_DAYS", 7)
    add_log(temp_db, 100)
    add_log(temp_db, 10)
    add_search(temp_db, 30)
    add_search(temp_db, 1)

    logs, searches = database.prune_old_rows()

    assert (logs, searches) == (1, 1)
    assert count(temp_db, "logs") == 1
    assert count(temp_db, "searches") == 1


def test_zero_retention_keeps_everything(temp_db, monkeypatch):
    monkeypatch.setattr(database, "LOG_RETENTION_DAYS", 0)
    monkeypatch.setattr(database, "SEARCH_RETENTION_DAYS", 0)
    add_log(temp_db, 1000)
    add_search(temp_db, 1000)

    assert database.prune_old_rows() == (0, 0)
    assert count(temp_db, "logs") == 1
    assert count(temp_db, "searches") == 1

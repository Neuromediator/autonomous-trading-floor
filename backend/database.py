import os
import sqlite3
import json
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# Absolute by default: under a service manager the working directory is not the
# project, and a relative path would quietly create a second, empty database.
PROJECT_DIR = Path(__file__).resolve().parent.parent
# "or", not a getenv default: DB_PATH set to an empty string still reaches the
# environment (from .env, or from systemd's EnvironmentFile), and sqlite3 reads
# "" as a private temporary database that is discarded when the connection
# closes — every write would vanish without an error anywhere.
DB = os.getenv("DB_PATH") or str(PROJECT_DIR / "accounts.db")

# The engine, the API and seven MCP subprocesses all open this file, and each
# call below opens a connection of its own. Five seconds of contention is not
# enough when a round writes trace logs continuously for minutes.
CONNECT_TIMEOUT = 30


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB, timeout=CONNECT_TIMEOUT)


with connect() as conn:
    cursor = conn.cursor()
    # WAL so the dashboard's polling can read while a round is writing. Under
    # the default rollback journal a writer takes the whole file and readers got
    # "database is locked" for the length of the round. The setting is stored in
    # the database file, so every later connection inherits it.
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('CREATE TABLE IF NOT EXISTS accounts (name TEXT PRIMARY KEY, account TEXT)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            datetime DATETIME,
            type TEXT,
            message TEXT
        )
    ''')
    # Shared price cache: every process (engine, each trader's accounts server,
    # the API) sees the same last known price for a symbol.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prices (
            symbol TEXT PRIMARY KEY,
            price REAL,
            fetched_at REAL
        )
    ''')
    # Shared search cache: four traders in one round ask near-identical
    # questions, and each search costs a credit on the free plan.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS searches (
            query TEXT PRIMARY KEY,
            response TEXT,
            fetched_at REAL
        )
    ''')
    # Every strategy the traders have written, so the self-improvement loop
    # leaves a trail: change_strategy replaces the text outright.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            datetime DATETIME,
            strategy TEXT
        )
    ''')
    # The dashboard polls the log for every trader every few seconds; without
    # this the query is a full table scan plus a sort, which grows with history.
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_name_datetime ON logs (name, datetime)')
    conn.commit()

def write_account(name, account_dict):
    json_data = json.dumps(account_dict)
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO accounts (name, account)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET account=excluded.account
        ''', (name.lower(), json_data))
        conn.commit()

def read_account(name):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT account FROM accounts WHERE name = ?', (name.lower(),))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None
    
def write_price(symbol: str, price: float, fetched_at: float):
    """Store the latest known price for a symbol, with its unix fetch time."""
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO prices (symbol, price, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET price=excluded.price, fetched_at=excluded.fetched_at
        ''', (symbol.upper(), price, fetched_at))
        conn.commit()

def read_price(symbol: str):
    """Return (price, fetched_at) for a symbol, or None if never seen."""
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT price, fetched_at FROM prices WHERE symbol = ?', (symbol.upper(),))
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

def write_search(query: str, response: str, fetched_at: float):
    """Store a search response under its normalised query."""
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO searches (query, response, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(query) DO UPDATE SET response=excluded.response, fetched_at=excluded.fetched_at
        ''', (query, response, fetched_at))
        conn.commit()

def read_search(query: str):
    """Return (response, fetched_at) for a query, or None if never searched."""
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT response, fetched_at FROM searches WHERE query = ?', (query,))
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

def write_strategy(name: str, strategy: str):
    """Append a strategy revision for a trader."""
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO strategies (name, datetime, strategy)
            VALUES (?, datetime('now'), ?)
        ''', (name.lower(), strategy))
        conn.commit()

def read_strategies(name: str):
    """Every strategy revision for a trader, oldest first."""
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT datetime, strategy FROM strategies WHERE name = ? ORDER BY id
        ''', (name.lower(),))
        return cursor.fetchall()

# Retention, applied once when the engine starts. Traces are noise after a few
# months and cached searches are useless past their TTL, but the accounts,
# strategies and per-trader memory are the record of the experiment and are
# never pruned. Set either to 0 to keep everything.
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "90"))
SEARCH_RETENTION_DAYS = int(os.getenv("SEARCH_RETENTION_DAYS", "7"))


def prune_old_rows() -> tuple[int, int]:
    """Drop expired trace logs and cached searches. Returns how many of each."""
    with connect() as conn:
        cursor = conn.cursor()
        logs = searches = 0
        if LOG_RETENTION_DAYS > 0:
            cursor.execute(
                "DELETE FROM logs WHERE datetime < datetime('now', ?)",
                (f"-{LOG_RETENTION_DAYS} days",),
            )
            logs = cursor.rowcount
        if SEARCH_RETENTION_DAYS > 0:
            cursor.execute(
                "DELETE FROM searches WHERE fetched_at < ?",
                (time.time() - SEARCH_RETENTION_DAYS * 86400,),
            )
            searches = cursor.rowcount
        conn.commit()
        return logs, searches


def write_log(name: str, type: str, message: str):
    """
    Write a log entry to the logs table.
    
    Args:
        name (str): The name associated with the log
        type (str): The type of log entry
        message (str): The log message
    """
    now = datetime.now().isoformat()
    
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (name, datetime, type, message)
            VALUES (?, datetime('now'), ?, ?)
        ''', (name.lower(), type, message))
        conn.commit()

def read_log(name: str, last_n=10):
    """
    Read the most recent log entries for a given name.
    
    Args:
        name (str): The name to retrieve logs for
        last_n (int): Number of most recent entries to retrieve
        
    Returns:
        list: A list of tuples containing (datetime, type, message)
    """
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT datetime, type, message FROM logs 
            WHERE name = ? 
            ORDER BY datetime DESC
            LIMIT ?
        ''', (name.lower(), last_n))
        
        return reversed(cursor.fetchall())
"""SQLite schema initialization and file hashing utility."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
    name       TEXT NOT NULL,
    impl_class TEXT NOT NULL,
    source_file TEXT NOT NULL,
    PRIMARY KEY (name, impl_class)
);

CREATE TABLE IF NOT EXISTS java_classes (
    fqn        TEXT PRIMARY KEY,
    file_path  TEXT NOT NULL,
    raw_source TEXT NOT NULL,
    file_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS methods (
    class_fqn   TEXT NOT NULL,
    method_name TEXT NOT NULL,
    signature   TEXT NOT NULL,
    source_code TEXT NOT NULL,
    start_line  INTEGER NOT NULL,
    end_line    INTEGER NOT NULL,
    PRIMARY KEY (class_fqn, method_name)
);

CREATE TABLE IF NOT EXISTS method_invocations (
    caller_class   TEXT NOT NULL,
    caller_method  TEXT NOT NULL,
    target_expression TEXT NOT NULL,
    resolved_class TEXT,
    resolved_method TEXT
);

CREATE INDEX IF NOT EXISTS idx_invocations_caller
    ON method_invocations (caller_class, caller_method);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection and create the schema."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file's contents."""
    try:
        content = Path(file_path).read_bytes()
        return hashlib.sha256(content).hexdigest()
    except OSError:
        return ""

"""Test result history in SQLite: one row per run, one row per test result."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .junit import Result
from .signature import normalise, signature

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    seq        INTEGER NOT NULL,      -- order of commits on the branch
    source     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    run_id    TEXT NOT NULL REFERENCES runs(run_id),
    test_id   TEXT NOT NULL,
    outcome   TEXT NOT NULL CHECK (outcome IN ('passed', 'failed', 'error', 'skipped')),
    duration  REAL NOT NULL,
    message   TEXT NOT NULL,
    sig       TEXT NOT NULL,
    sig_text  TEXT NOT NULL,
    PRIMARY KEY (run_id, test_id)
);
CREATE INDEX IF NOT EXISTS results_test ON results (test_id);
"""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_run(conn: sqlite3.Connection, run_id: str, commit_sha: str, seq: int, source: str,
            results: list[Result]) -> int:
    """Store one run; re-ingesting the same run id replaces it rather than doubling it."""
    with conn:
        conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
        conn.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)", (run_id, commit_sha, seq, source))
        conn.executemany(
            "INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(run_id, r.test_id, r.outcome, r.duration, r.message, signature(r.message), normalise(r.message))
             for r in results])
    return len(results)

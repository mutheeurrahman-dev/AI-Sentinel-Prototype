"""database.py -- lightweight SQLite access layer (no ORM, kept simple &
transparent so it's easy to explain during judging Q&A)."""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sentinel.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    category TEXT,
    state TEXT,
    district TEXT,
    mp_name TEXT,
    sanctioned_cost REAL,
    actual_cost REAL,
    sanction_date TEXT,
    expected_completion_date TEXT,
    actual_completion_date TEXT,
    status TEXT,
    implementing_agency TEXT,
    financial_risk_score REAL DEFAULT 0,
    visual_risk_score REAL DEFAULT 0,
    overall_risk_score REAL DEFAULT 0,
    risk_level TEXT DEFAULT 'low'
);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(project_id),
    progress_percent_claimed REAL,
    photo_filename TEXT,
    receipt_filename TEXT,
    submission_date TEXT,
    visual_risk_score REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT REFERENCES projects(project_id),
    submission_id TEXT,
    flag_source TEXT,     -- 'financial' | 'visual'
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_risk ON projects(overall_risk_score);
CREATE INDEX IF NOT EXISTS idx_submissions_project ON submissions(project_id);
CREATE INDEX IF NOT EXISTS idx_flags_project ON flags(project_id);
"""


def init_db(reset: bool = False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

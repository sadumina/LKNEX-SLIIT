# Purpose of this file is to manage the SQLite connection and store verification runs and their results

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, get_args

from app.schemas.auth import UserRole

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# backend/app/database/db.py -> parents[2] is backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "aegis.db"

# Allowed values. Keep these identical across the whole team.
VERDICTS = ("supported", "contradicted", "unsupported")
ACTIONS = ("approve", "correct", "block", "human_review")
MODES = ("multi_agent", "single_agent", "passthrough")
RISK_LEVELS = ("low", "medium", "high")
RUN_STATUSES = ("running", "completed", "failed")
REVIEW_STATUSES = ("pending", "resolved")
REVIEW_DECISIONS = ("approve", "correct", "block")
USER_ROLES = get_args(UserRole)


def _in(values: tuple[str, ...]) -> str:
    """Build "('a', 'b')" for a CHECK constraint. Only used with the constants above, never with user input."""
    return "(" + ", ".join(repr(v) for v in values) + ")"


_USER_ROLE_COLUMN = f"account_role TEXT NOT NULL DEFAULT 'user' CHECK (account_role IN {_in(USER_ROLES)})"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    {_USER_ROLE_COLUMN}
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_expiry ON user_sessions(expires_at);

CREATE TABLE IF NOT EXISTS verification_runs (
    run_id       TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    completed_at TEXT,
    mode         TEXT NOT NULL CHECK (mode IN {_in(MODES)}),
    user_role    TEXT NOT NULL,
    question     TEXT,
    draft_answer TEXT,
    final_answer TEXT,
    action       TEXT CHECK (action IN {_in(ACTIONS)}),
    risk_level   TEXT CHECK (risk_level IN {_in(RISK_LEVELS)}),
    status       TEXT NOT NULL DEFAULT 'running' CHECK (status IN {_in(RUN_STATUSES)}),
    latency_ms   INTEGER,
    llm_calls    INTEGER,
    cost_usd     REAL
);

CREATE TABLE IF NOT EXISTS claim_results (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             TEXT NOT NULL REFERENCES verification_runs(run_id),
    claim_id           TEXT NOT NULL,
    claim_text         TEXT NOT NULL,
    verdict            TEXT NOT NULL CHECK (verdict IN {_in(VERDICTS)}),
    confidence         REAL,
    evidence_chunk_ids TEXT,
    UNIQUE (run_id, claim_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL REFERENCES verification_runs(run_id),
    agent      TEXT NOT NULL,
    event      TEXT NOT NULL,
    details    TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS human_reviews (
    review_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES verification_runs(run_id),
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN {_in(REVIEW_STATUSES)}),
    reviewer    TEXT,
    decision    TEXT CHECK (decision IN {_in(REVIEW_DECISIONS)}),
    notes       TEXT,
    created_at  TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id       TEXT NOT NULL,
    case_id        TEXT NOT NULL,
    mode           TEXT NOT NULL CHECK (mode IN {_in(MODES)}),
    expected_label TEXT NOT NULL CHECK (expected_label IN {_in(VERDICTS)}),
    predicted      TEXT NOT NULL CHECK (predicted IN {_in(VERDICTS)}),
    correct        INTEGER NOT NULL CHECK (correct IN (0, 1)),
    latency_ms     INTEGER,
    cost_usd       REAL,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_run  ON claim_results(run_id);
CREATE INDEX IF NOT EXISTS idx_events_run  ON audit_events(run_id);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON human_reviews(status);
CREATE INDEX IF NOT EXISTS idx_bench_batch ON benchmark_results(batch_id);
"""


def utc_now() -> str:
    """Current UTC time as ISO 8601 text, for example 2026-11-25T08:30:00+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return uuid.uuid4().hex


def _to_json(value: Any) -> str | None:
    """Lists and dicts are stored as JSON text. ensure_ascii=False keeps Sinhala, Tamil and other scripts readable."""
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


def _from_json(text: str | None) -> Any:
    return json.loads(text) if text else None


# Connection and setup
def _database_path(dp_path: Path | str | None) -> str:
    """Pick the database file. Order: argument, AEGIS_DB_PATH (environment or backend/.env), default file.

    A relative AEGIS_DB_PATH is resolved against backend/, so the result does not depend on the
    folder where uvicorn or pytest was started.
    """
    if dp_path:
        return str(dp_path)
    if not os.getenv("AEGIS_DB_PATH") and load_dotenv:
        load_dotenv(BACKEND_DIR / ".env")

    env_path = os.getenv("AEGIS_DB_PATH")
    if not env_path:
        return str(DEFAULT_DB_PATH)
    if env_path == ":memory:":
        return env_path
    return str(BACKEND_DIR / env_path)


def connect(dp_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection to the SQLite file chosen by _database_path.

    Use ":memory:" for tests. Every ":memory:" connection is its own empty database.
    """
    path = _database_path(dp_path)
    in_memory = path == ":memory:"
    if not in_memory:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")

    if not in_memory:
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes. Safe to call many times (IF NOT EXISTS). Call once at application start."""
    conn.executescript(_SCHEMA)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        columns = {column["name"] for column in conn.execute("PRAGMA table_info(users)")}
        if "account_role" not in columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {_USER_ROLE_COLUMN}")
        if "role" in columns:
            conn.execute("ALTER TABLE users DROP COLUMN role")


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, always closed afterwards.

    Usage:  def route(db: sqlite3.Connection = Depends(get_db)): ...
    """
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# Verification runs
def start_run(
    conn: sqlite3.Connection,
    *,
    mode: str,
    user_role: str,
    question: str | None = None,
    draft_answer: str | None = None,
    run_id: str | None = None,
) -> str:
    """Create the run row at intake. Events and claims need this row to exist first (foreign key)."""
    run_id = run_id or new_run_id()
    with conn:  # commits on success, rolls back on error
        conn.execute(
            "INSERT INTO verification_runs (run_id, created_at, mode, user_role, question, draft_answer, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'running')",
            (run_id, utc_now(), mode, user_role, question, draft_answer),
        )
    return run_id


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    action: str,
    final_answer: str | None = None,
    risk_level: str | None = None,
    latency_ms: int | None = None,
    llm_calls: int | None = None,
    cost_usd: float | None = None,
) -> None:
    """Record the policy decision and the measured latency and cost."""
    with conn:
        cur = conn.execute(
            "UPDATE verification_runs SET completed_at = ?, status = 'completed', action = ?, final_answer = ?, "
            "risk_level = ?, latency_ms = ?, llm_calls = ?, cost_usd = ? WHERE run_id = ?",
            (
                utc_now(),
                action,
                final_answer,
                risk_level,
                latency_ms,
                llm_calls,
                cost_usd,
                run_id,
            ),
        )
    if cur.rowcount == 0:
        raise KeyError(f"Unknown run_id: {run_id}")


def fail_run(conn: sqlite3.Connection, run_id: str, error: str) -> None:
    """Mark a run as failed and write the reason to the audit trail (one transaction).

    The supervisor can then call finish_run(..., action="human_review") if the case must go to a person.
    """
    with conn:
        cur = conn.execute(
            "UPDATE verification_runs SET completed_at = ?, status = 'failed' WHERE run_id = ?",
            (utc_now(), run_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Unknown run_id: {run_id}")
        _insert_event(conn, run_id, "supervisor", "run_failed", {"error": error})


def get_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM verification_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return dict(row) if row else None


def list_runs(
    conn: sqlite3.Connection, limit: int = 50, mode: str | None = None
) -> list[dict]:
    """Newest runs first. rowid breaks ties between runs created in the same second."""
    sql = "SELECT * FROM verification_runs"
    params: list[Any] = []
    if mode:
        sql += " WHERE mode = ?"
        params.append(mode)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def action_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many runs ended in each action. Feeds the dashboard chart."""
    rows = conn.execute(
        "SELECT action, COUNT(*) AS n FROM verification_runs WHERE action IS NOT NULL GROUP BY action"
    )
    return {r["action"]: r["n"] for r in rows}


# Claim verdicts
def save_claim_results(
    conn: sqlite3.Connection, run_id: str, claims: Iterable[dict]
) -> int:
    """Save one row per claim. Each dict needs claim_id, claim_text and verdict.

    Optional keys: confidence, evidence_chunk_ids (a list of chunk ids, not the text).
    Saving the same claim_id again replaces the old row, which is what happens when a corrected
    answer is verified a second time.
    """
    rows = [
        (
            run_id,
            c["claim_id"],
            c["claim_text"],
            c["verdict"],
            c.get("confidence"),
            _to_json(c.get("evidence_chunk_ids", [])),
        )
        for c in claims
    ]
    with conn:
        conn.executemany(
            "INSERT INTO claim_results (run_id, claim_id, claim_text, verdict, confidence, evidence_chunk_ids) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (run_id, claim_id) DO UPDATE SET claim_text = excluded.claim_text, "
            "verdict = excluded.verdict, confidence = excluded.confidence, "
            "evidence_chunk_ids = excluded.evidence_chunk_ids",
            rows,
        )
    return len(rows)


def get_claim_results(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM claim_results WHERE run_id = ? ORDER BY id", (run_id,)
    )
    results = []
    for row in rows:
        item = dict(row)
        item["evidence_chunk_ids"] = _from_json(item["evidence_chunk_ids"]) or []
        results.append(item)
    return results


# Audit trail
def _insert_event(
    conn: sqlite3.Connection, run_id: str, agent: str, event: str, details: Any = None
) -> None:
    """Insert without committing, so callers can group it with other writes."""
    conn.execute(
        "INSERT INTO audit_events (run_id, agent, event, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (run_id, agent, event, _to_json(details), utc_now()),
    )


def log_event(
    conn: sqlite3.Connection, run_id: str, agent: str, event: str, details: Any = None
) -> None:
    """Record one agent step, for example ("fact_verification", "verdicts_ready", {"contradicted": 2})."""
    with conn:
        _insert_event(conn, run_id, agent, event, details)


def get_audit_trail(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    """Events in the order they happened. We sort by id because many events share the same second."""
    rows = conn.execute(
        "SELECT * FROM audit_events WHERE run_id = ? ORDER BY id", (run_id,)
    )
    trail = []
    for row in rows:
        item = dict(row)
        item["details"] = _from_json(item["details"])
        trail.append(item)
    return trail


# Human review queue
def create_human_review(conn: sqlite3.Connection, run_id: str) -> int:
    """Put a run in the review queue. Returns the review id."""
    with conn:
        cur = conn.execute(
            "INSERT INTO human_reviews (run_id, status, created_at) VALUES (?, 'pending', ?)",
            (run_id, utc_now()),
        )
    return int(cur.lastrowid)


def list_pending_reviews(conn: sqlite3.Connection) -> list[dict]:
    """Pending reviews with the question and draft, so a reviewer sees what to judge."""
    rows = conn.execute(
        "SELECT h.review_id, h.run_id, h.created_at, r.question, r.draft_answer, r.risk_level "
        "FROM human_reviews h JOIN verification_runs r ON r.run_id = h.run_id "
        "WHERE h.status = 'pending' ORDER BY h.review_id"
    )
    return [dict(r) for r in rows]


def resolve_human_review(
    conn: sqlite3.Connection,
    review_id: int,
    *,
    reviewer: str,
    decision: str,
    notes: str | None = None,
) -> None:
    """Close a pending review. A review can only be resolved once."""
    with conn:
        cur = conn.execute(
            "UPDATE human_reviews SET status = 'resolved', reviewer = ?, decision = ?, notes = ?, resolved_at = ? "
            "WHERE review_id = ? AND status = 'pending'",
            (reviewer, decision, notes, utc_now(), review_id),
        )
    if cur.rowcount == 0:
        raise ValueError(f"Review {review_id} does not exist or is already resolved")


# Benchmark results
def save_benchmark_result(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
    case_id: str,
    mode: str,
    expected_label: str,
    predicted: str,
    latency_ms: int | None = None,
    cost_usd: float | None = None,
) -> bool:
    """Save one test case result. "correct" is computed here, never passed in, so results cannot be edited by hand.

    batch_id names one benchmark run (for example "2026-11-26-run1") so repeated runs never mix.
    """
    correct = expected_label == predicted
    with conn:
        conn.execute(
            "INSERT INTO benchmark_results "
            "(batch_id, case_id, mode, expected_label, predicted, correct, latency_ms, cost_usd, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                case_id,
                mode,
                expected_label,
                predicted,
                int(correct),
                latency_ms,
                cost_usd,
                utc_now(),
            ),
        )
    return correct


def benchmark_summary(
    conn: sqlite3.Connection, batch_id: str | None = None
) -> list[dict]:
    """One row per mode with accuracy, average latency and cost. This is your multi agent vs single agent table."""
    sql = (
        "SELECT mode, COUNT(*) AS cases, SUM(correct) AS correct, "
        "ROUND(1.0 * SUM(correct) / COUNT(*), 4) AS accuracy, "
        "ROUND(AVG(latency_ms), 1) AS avg_latency_ms, "
        "ROUND(AVG(cost_usd), 6) AS avg_cost_usd, "
        "ROUND(SUM(cost_usd), 6) AS total_cost_usd "
        "FROM benchmark_results"
    )
    params: list[Any] = []
    if batch_id:
        sql += " WHERE batch_id = ?"
        params.append(batch_id)
    sql += " GROUP BY mode ORDER BY mode"
    return [dict(r) for r in conn.execute(sql, params)]

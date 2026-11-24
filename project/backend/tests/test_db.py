# Purpose of this file is to test the SQLite operational database (runs, claims, audit trail, reviews, benchmarks)
"""Tests for app/database/db.py. They use in memory SQLite, so they are fast, free and need no API key."""
import sqlite3
import threading

import pytest

from app.database import db


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def _run(conn, **overrides):
    values = dict(mode="multi_agent", user_role="customer_service", question="Return window?", draft_answer="30 days")
    values.update(overrides)
    return db.start_run(conn, **values)


# Setup
def test_init_creates_all_tables(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"verification_runs", "claim_results", "audit_events", "human_reviews", "benchmark_results"} <= names


def test_init_is_idempotent(conn):
    run_id = _run(conn)
    db.init_db(conn)   # second call must not wipe data
    assert db.get_run(conn, run_id) is not None


def test_foreign_keys_are_enabled(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_file_database_uses_wal(tmp_path):
    connection = db.connect(tmp_path / "nested" / "aegis.db")   # parent folder is created automatically
    db.init_db(connection)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    connection.close()


def test_env_variable_sets_the_path(tmp_path, monkeypatch):
    target = tmp_path / "from_env.db"
    monkeypatch.setenv("AEGIS_DB_PATH", str(target))
    connection = db.connect()
    db.init_db(connection)
    connection.close()
    assert target.exists()


def test_relative_env_path_is_resolved_against_backend_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "BACKEND_DIR", tmp_path)
    monkeypatch.setenv("AEGIS_DB_PATH", "data/custom.db")
    connection = db.connect()
    db.init_db(connection)
    connection.close()
    assert (tmp_path / "data" / "custom.db").exists()


def test_env_file_in_backend_dir_is_read(tmp_path, monkeypatch):
    pytest.importorskip("dotenv")
    (tmp_path / ".env").write_text("AEGIS_DB_PATH=from_dotenv.db\n", encoding="utf-8")
    monkeypatch.setattr(db, "BACKEND_DIR", tmp_path)
    monkeypatch.setenv("AEGIS_DB_PATH", "placeholder")
    monkeypatch.delenv("AEGIS_DB_PATH")          # variable is now unset, and pytest cleans up afterwards
    connection = db.connect()
    db.init_db(connection)
    connection.close()
    assert (tmp_path / "from_dotenv.db").exists()


def test_real_environment_variable_beats_env_file(tmp_path, monkeypatch):
    pytest.importorskip("dotenv")
    (tmp_path / ".env").write_text("AEGIS_DB_PATH=loser.db\n", encoding="utf-8")
    monkeypatch.setattr(db, "BACKEND_DIR", tmp_path)
    monkeypatch.setenv("AEGIS_DB_PATH", "winner.db")
    connection = db.connect()
    db.init_db(connection)
    connection.close()
    assert (tmp_path / "winner.db").exists()
    assert not (tmp_path / "loser.db").exists()


def test_default_path_is_inside_backend_data():
    assert db.DEFAULT_DB_PATH.name == "aegis.db"
    assert db.DEFAULT_DB_PATH.parent.name == "data"


def test_connection_can_be_used_from_another_thread(tmp_path):
    connection = db.connect(tmp_path / "threads.db")
    db.init_db(connection)
    result = []
    thread = threading.Thread(target=lambda: result.append(_run(connection)))
    thread.start()
    thread.join()
    assert len(result) == 1
    connection.close()


def test_get_db_closes_the_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_DB_PATH", str(tmp_path / "dep.db"))
    generator = db.get_db()
    connection = next(generator)
    generator.close()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


# Runs
def test_run_lifecycle(conn):
    run_id = _run(conn)
    started = db.get_run(conn, run_id)
    assert started["status"] == "running"
    assert started["action"] is None and started["completed_at"] is None

    db.finish_run(conn, run_id, action="correct", final_answer="14 days", risk_level="high",
                  latency_ms=2400, llm_calls=3, cost_usd=0.0021)
    done = db.get_run(conn, run_id)
    assert done["status"] == "completed"
    assert done["action"] == "correct"
    assert done["final_answer"] == "14 days"
    assert done["latency_ms"] == 2400
    assert done["completed_at"] is not None


def test_finish_unknown_run_raises(conn):
    with pytest.raises(KeyError):
        db.finish_run(conn, "does-not-exist", action="approve")


def test_invalid_action_is_rejected_and_nothing_changes(conn):
    run_id = _run(conn)
    with pytest.raises(sqlite3.IntegrityError):
        db.finish_run(conn, run_id, action="delete_everything")
    assert db.get_run(conn, run_id)["status"] == "running"


def test_invalid_mode_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, mode="quantum_agent")


def test_fail_run_marks_failed_and_logs_reason(conn):
    run_id = _run(conn)
    db.fail_run(conn, run_id, "LLM timeout after 2 retries")
    assert db.get_run(conn, run_id)["status"] == "failed"
    trail = db.get_audit_trail(conn, run_id)
    assert trail[-1]["event"] == "run_failed"
    assert trail[-1]["details"] == {"error": "LLM timeout after 2 retries"}


def test_list_runs_filters_and_orders(conn):
    first = _run(conn, mode="single_agent")
    second = _run(conn, mode="multi_agent")
    third = _run(conn, mode="multi_agent")
    assert [r["run_id"] for r in db.list_runs(conn)] == [third, second, first]
    assert [r["run_id"] for r in db.list_runs(conn, mode="single_agent")] == [first]
    assert len(db.list_runs(conn, limit=2)) == 2


def test_action_counts(conn):
    for action in ("approve", "correct", "correct"):
        db.finish_run(conn, _run(conn), action=action)
    _run(conn)   # still running, must not be counted
    assert db.action_counts(conn) == {"approve": 1, "correct": 2}


def test_sql_injection_text_is_stored_as_plain_text(conn):
    evil = "x'); DROP TABLE verification_runs; --"
    run_id = _run(conn, question=evil)
    assert db.get_run(conn, run_id)["question"] == evil
    assert conn.execute("SELECT COUNT(*) FROM verification_runs").fetchone()[0] == 1


# Claims
def _claims():
    return [
        {"claim_id": "C1", "claim_text": "Return window is 30 days", "verdict": "contradicted",
         "confidence": 0.97, "evidence_chunk_ids": ["returns-policy:v3.2:p2:1", "returns-faq:v1.0:p1:1"]},
        {"claim_id": "C4", "claim_text": "Refunds take 5 business days", "verdict": "unsupported"},
    ]


def test_claims_round_trip(conn):
    run_id = _run(conn)
    assert db.save_claim_results(conn, run_id, _claims()) == 2
    saved = db.get_claim_results(conn, run_id)
    assert [c["claim_id"] for c in saved] == ["C1", "C4"]
    assert saved[0]["evidence_chunk_ids"] == ["returns-policy:v3.2:p2:1", "returns-faq:v1.0:p1:1"]
    assert saved[1]["evidence_chunk_ids"] == []      # missing key becomes an empty list
    assert saved[1]["confidence"] is None


def test_saving_a_claim_again_replaces_it(conn):
    run_id = _run(conn)
    db.save_claim_results(conn, run_id, _claims())
    db.save_claim_results(conn, run_id, [{"claim_id": "C1", "claim_text": "Return window is 14 days", "verdict": "supported"}])
    saved = {c["claim_id"]: c for c in db.get_claim_results(conn, run_id)}
    assert len(saved) == 2
    assert saved["C1"]["verdict"] == "supported"
    assert saved["C1"]["claim_text"] == "Return window is 14 days"


def test_claim_for_missing_run_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.save_claim_results(conn, "no-such-run", _claims())


def test_invalid_verdict_is_rejected(conn):
    run_id = _run(conn)
    bad = [{"claim_id": "C1", "claim_text": "x", "verdict": "maybe"}]
    with pytest.raises(sqlite3.IntegrityError):
        db.save_claim_results(conn, run_id, bad)


# Audit trail
def test_audit_trail_keeps_order_and_decodes_details(conn):
    run_id = _run(conn)
    db.log_event(conn, run_id, "claim_extraction", "claims_found", {"count": 4})
    db.log_event(conn, run_id, "evidence_retrieval", "evidence_ready", {"empty_claims": ["C4"]})
    db.log_event(conn, run_id, "policy_engine", "decision")   # no details
    trail = db.get_audit_trail(conn, run_id)
    assert [e["agent"] for e in trail] == ["claim_extraction", "evidence_retrieval", "policy_engine"]
    assert trail[0]["details"] == {"count": 4}
    assert trail[2]["details"] is None


def test_audit_details_keep_non_english_text(conn):
    run_id = _run(conn)
    db.log_event(conn, run_id, "claim_extraction", "note", {"text": "ආපසු ගෙවීම"})
    stored = conn.execute("SELECT details FROM audit_events").fetchone()["details"]
    assert "ආපසු ගෙවීම" in stored      # not escaped as \uXXXX
    assert db.get_audit_trail(conn, run_id)[0]["details"] == {"text": "ආපසු ගෙවීම"}


def test_audit_for_missing_run_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.log_event(conn, "no-such-run", "agent", "event")


# Human review
def test_human_review_lifecycle(conn):
    run_id = _run(conn, question="Can we waive the late fee?")
    review_id = db.create_human_review(conn, run_id)

    pending = db.list_pending_reviews(conn)
    assert len(pending) == 1
    assert pending[0]["question"] == "Can we waive the late fee?"

    db.resolve_human_review(conn, review_id, reviewer="alice", decision="block", notes="Regulated topic")
    assert db.list_pending_reviews(conn) == []
    row = conn.execute("SELECT * FROM human_reviews WHERE review_id = ?", (review_id,)).fetchone()
    assert row["status"] == "resolved" and row["reviewer"] == "alice" and row["decision"] == "block"
    assert row["resolved_at"] is not None


def test_review_cannot_be_resolved_twice(conn):
    review_id = db.create_human_review(conn, _run(conn))
    db.resolve_human_review(conn, review_id, reviewer="alice", decision="approve")
    with pytest.raises(ValueError):
        db.resolve_human_review(conn, review_id, reviewer="bob", decision="block")


def test_unknown_review_raises(conn):
    with pytest.raises(ValueError):
        db.resolve_human_review(conn, 999, reviewer="alice", decision="approve")


def test_invalid_review_decision_is_rejected(conn):
    review_id = db.create_human_review(conn, _run(conn))
    with pytest.raises(sqlite3.IntegrityError):
        db.resolve_human_review(conn, review_id, reviewer="alice", decision="ignore")
    assert len(db.list_pending_reviews(conn)) == 1   # still pending after the failed update


# Benchmarks
def test_benchmark_correct_is_computed_not_supplied(conn):
    assert db.save_benchmark_result(conn, batch_id="b1", case_id="t1", mode="multi_agent",
                                    expected_label="contradicted", predicted="contradicted") is True
    assert db.save_benchmark_result(conn, batch_id="b1", case_id="t2", mode="multi_agent",
                                    expected_label="supported", predicted="unsupported") is False
    flags = [r["correct"] for r in conn.execute("SELECT correct FROM benchmark_results ORDER BY id")]
    assert flags == [1, 0]


def test_benchmark_summary_per_mode_and_batch(conn):
    rows = [
        ("b1", "t1", "multi_agent", "supported", "supported", 3000, 0.004),
        ("b1", "t2", "multi_agent", "contradicted", "contradicted", 3200, 0.004),
        ("b1", "t1", "single_agent", "supported", "supported", 1500, 0.002),
        ("b1", "t2", "single_agent", "contradicted", "supported", 1700, 0.002),
        ("b2", "t1", "multi_agent", "supported", "unsupported", 9999, 0.5),   # other batch
    ]
    for batch, case, mode, expected, predicted, latency, cost in rows:
        db.save_benchmark_result(conn, batch_id=batch, case_id=case, mode=mode, expected_label=expected,
                                 predicted=predicted, latency_ms=latency, cost_usd=cost)

    summary = {r["mode"]: r for r in db.benchmark_summary(conn, batch_id="b1")}
    assert summary["multi_agent"]["cases"] == 2
    assert summary["multi_agent"]["accuracy"] == 1.0
    assert summary["multi_agent"]["avg_latency_ms"] == 3100.0
    assert summary["single_agent"]["accuracy"] == 0.5
    assert summary["single_agent"]["total_cost_usd"] == 0.004

    everything = {r["mode"]: r for r in db.benchmark_summary(conn)}
    assert everything["multi_agent"]["cases"] == 3


def test_benchmark_rejects_unknown_label(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.save_benchmark_result(conn, batch_id="b1", case_id="t1", mode="multi_agent",
                                 expected_label="supported", predicted="banana")
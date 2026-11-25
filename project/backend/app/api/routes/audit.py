"""Read-only audit and verification history API."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import db
from app.api.dependencies import require_audit_role, require_admin

router = APIRouter(
    prefix="/api/audit",
    tags=["Audit"],
    dependencies=[Depends(require_audit_role)],
)


@router.get("/runs")
def list_verification_runs(
    limit: int = Query(default=50, ge=1, le=100),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    return db.list_runs(conn, limit=limit)


@router.get("/runs/{run_id}")
def get_verification_run(
    run_id: str,
    conn: sqlite3.Connection = Depends(db.get_db),
):
    run = db.get_run(conn, run_id)

    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "run": run,
        "claims": db.get_claim_results(conn, run_id),
        "events": db.get_audit_trail(conn, run_id),
    }


@router.get("/stats/actions", dependencies=[Depends(require_admin)])
def get_action_statistics(
    conn: sqlite3.Connection = Depends(db.get_db),
):
    return db.action_counts(conn)

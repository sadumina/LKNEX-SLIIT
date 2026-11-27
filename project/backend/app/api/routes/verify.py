"""Verification API routes."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_admin
from app.database import db
from app.schemas.api import (
    PreparedVerifyRequest,
    VerifyRequest,
    VerifyResponse,
    WorkflowResultResponse,
)
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/api", tags=["Verification"])


@router.post(
    "/verify",
    response_model=VerifyResponse,
    responses={503: {"description": "Verification service not ready"}},
)
def verify_answer(request: VerifyRequest):
    """Validate a request and report supervisor availability."""
    raise HTTPException(
        status_code=503,
        detail="Verification supervisor is not integrated yet.",
    )


@router.post(
    "/verify/prepared",
    response_model=WorkflowResultResponse,
)
def verify_prepared(
    request: PreparedVerifyRequest,
    conn: sqlite3.Connection = Depends(db.get_db),
    role: str = Depends(require_admin),
):
    service = VerificationService(conn)

    return service.verify_prepared(
        question=request.question,
        draft_answer=request.draft_answer,
        user_role=role,
        claims=request.claims,
        evidence_chunks=request.evidence_chunks,
        mode=request.mode,
    )

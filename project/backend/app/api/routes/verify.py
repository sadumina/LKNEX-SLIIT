"""Verification API routes."""

import sqlite3

from fastapi import APIRouter, Depends

from app.database import db
from app.schemas.api import VerifyRequest, WorkflowResultResponse
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/api", tags=["Verification"])


@router.post(
    "/verify",
    response_model=WorkflowResultResponse,
)
def verify_answer(
    request: VerifyRequest,
    connection: sqlite3.Connection = Depends(db.get_db),
):
    """Run the complete verification pipeline for a draft answer."""
    return VerificationService(connection).verify_complete(
        question=request.question,
        draft_answer=request.draft_answer,
        user_role=request.user_role,
        mode=request.mode,
    )

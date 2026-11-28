"""Verification API routes."""

import sqlite3

from fastapi import APIRouter, Depends

from app.api.dependencies import require_account
from app.database import db
from app.schemas.api import VerifyRequest, WorkflowResultResponse
from app.schemas.auth import RegisteredUser
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/api", tags=["Verification"])


@router.post(
    "/verify",
    response_model=WorkflowResultResponse,
)
def verify_answer(
    request: VerifyRequest,
    account: RegisteredUser = Depends(require_account),
    connection: sqlite3.Connection = Depends(db.get_db),
):
    """Run the complete verification pipeline for a draft answer."""
    return VerificationService(connection).verify_complete(
        question=request.question,
        draft_answer=request.draft_answer,
        user_role=account.role,
        mode=request.mode,
    )

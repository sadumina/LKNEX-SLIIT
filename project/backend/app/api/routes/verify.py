"""Verification API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.api import VerifyRequest, VerifyResponse

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

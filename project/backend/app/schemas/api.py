"""Request and response models for the AEGIS AI API."""

from typing import Literal

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    question: str = Field(min_length=1)
    draft_answer: str = Field(min_length=1)
    mode: Literal["multi_agent", "single_agent", "pasthrough"] = "multi_agent"


class VerifyResponse(BaseModel):
    status: str
    message: str
    run_id: str | None = None

# Purpose of this file is to define the models for policy decisions and the final verification result

"""Deterministic decision and workflow-control contracts."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class FinalAction(str, Enum):
    """Only actions that the deterministic Policy Engine may select."""

    APPROVE = "approve"
    CORRECT = "correct"
    BLOCK = "block"
    HUMAN_REVIEW = "human_review"


class PolicyDecision(BaseModel):
    """Typed output produced by the deterministic Policy Decision Engine."""

    action: FinalAction
    reason: str = Field(..., min_length=1)
    requires_human_review: bool = False


class WorkflowError(BaseModel):
    """Safe error information used by the Supervisor for retry routing."""

    node: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    retryable: bool = False
    attempts: int = Field(default=1, ge=1)


class CorrectionStatus(BaseModel):
    """Bounded correction-loop state."""

    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def attempts_must_not_exceed_limit(self):
        if self.attempts > self.max_attempts:
            raise ValueError("correction attempts cannot exceed max_attempts")
        return self

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts

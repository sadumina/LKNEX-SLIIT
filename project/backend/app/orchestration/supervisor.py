# Purpose of this file is to coordinate the agents, handle retries and send the case to human review if an agent fails

"""Supervisor execution wrapper with bounded, fail-closed retries."""

from collections.abc import Callable

from app.core.llm_client import AllProvidersFailedError
from app.core.security import mask_sensitive_data
from app.schemas.decision import WorkflowError


MAX_AGENT_ATTEMPTS = 2
_RETRYABLE_STATUS_CODES = {408, 429}


def is_retryable_error(error: Exception) -> bool:
    """Return whether repeating an operation may resolve the failure."""
    if isinstance(error, AllProvidersFailedError):
        return True
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code in _RETRYABLE_STATUS_CODES or status_code >= 500
    return type(error).__name__ in {"APIConnectionError", "APITimeoutError"}


def _safe_error_message(error: Exception) -> str:
    message = str(error).strip() or type(error).__name__
    return mask_sensitive_data(f"{type(error).__name__}: {message}"[:500])


class Supervisor:
    """Execute workflow nodes with bounded retries and structured failures."""

    def __init__(self, max_attempts: int = MAX_AGENT_ATTEMPTS):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_attempts = max_attempts

    def execute(
        self,
        node_name: str,
        operation: Callable[[], dict],
        *,
        max_attempts: int | None = None,
    ) -> dict:
        attempt_limit = max_attempts or self.max_attempts
        if attempt_limit < 1:
            raise ValueError("max_attempts must be at least 1")

        for attempt in range(1, attempt_limit + 1):
            try:
                update = operation()
                return {**update, "retry_count": attempt - 1}
            except Exception as error:
                retryable = is_retryable_error(error)
                if retryable and attempt < attempt_limit:
                    continue
                return {
                    "workflow_error": WorkflowError(
                        node=node_name,
                        message=_safe_error_message(error),
                        retryable=retryable,
                        attempts=attempt,
                    ),
                    "retry_count": attempt,
                }

        raise AssertionError("Supervisor retry loop ended unexpectedly")

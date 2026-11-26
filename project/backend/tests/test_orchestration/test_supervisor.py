"""Tests for bounded Supervisor retries and safe failure conversion."""

from app.orchestration.supervisor import Supervisor, is_retryable_error


def test_supervisor_returns_success_without_retry():
    result = Supervisor().execute("test_node", lambda: {"value": "ok"})

    assert result == {"value": "ok", "retry_count": 0}


def test_supervisor_retries_transient_failure_then_succeeds():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary timeout")
        return {"value": "recovered"}

    result = Supervisor(max_attempts=2).execute("test_node", operation)

    assert result["value"] == "recovered"
    assert result["retry_count"] == 1
    assert "workflow_error" not in result


def test_supervisor_stops_immediately_for_nonretryable_failure():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid state")

    result = Supervisor(max_attempts=2).execute("test_node", operation)

    assert attempts == 1
    assert result["workflow_error"].retryable is False
    assert result["workflow_error"].attempts == 1


def test_supervisor_escalates_after_transient_retry_exhaustion():
    result = Supervisor(max_attempts=2).execute(
        "fact_verification",
        lambda: (_ for _ in ()).throw(ConnectionError("provider unavailable")),
    )

    assert result["workflow_error"].node == "fact_verification"
    assert result["workflow_error"].retryable is True
    assert result["workflow_error"].attempts == 2
    assert result["retry_count"] == 2


def test_supervisor_masks_sensitive_values_in_error_message():
    result = Supervisor().execute(
        "test_node",
        lambda: (_ for _ in ()).throw(RuntimeError("password=fictional-secret-value")),
    )

    message = result["workflow_error"].message
    assert "fictional-secret-value" not in message
    assert "[REDACTED]" in message


def test_retryable_status_codes():
    class ServiceError(Exception):
        status_code = 503

    assert is_retryable_error(ServiceError()) is True
    assert is_retryable_error(ValueError()) is False

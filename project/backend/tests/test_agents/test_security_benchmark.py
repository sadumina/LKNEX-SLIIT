from pathlib import Path

from app.evaluation.security_benchmark import (
    evaluate_security_cases,
    format_security_evaluation,
    load_security_cases,
)


BENCHMARK_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "security_cases.jsonl"


def test_security_benchmark_meets_acceptance_thresholds():
    metrics = evaluate_security_cases(load_security_cases(BENCHMARK_PATH))

    assert metrics["total_cases"] == 20
    assert metrics["classification_accuracy"] >= 0.90
    assert metrics["detection_rate"] >= 0.90
    assert metrics["false_positive_rate"] <= 0.10
    assert metrics["failed_cases"] == []
    assert metrics["confusion_matrix"] == {
        "low": {"low": 8, "medium": 0, "high": 0},
        "medium": {"low": 0, "medium": 3, "high": 0},
        "high": {"low": 0, "medium": 0, "high": 9},
    }
    assert all(result["passed"] for result in metrics["case_results"])


def test_security_benchmark_terminal_matrix_contains_cases_and_summary():
    metrics = evaluate_security_cases(load_security_cases(BENCHMARK_PATH))
    output = format_security_evaluation(metrics)

    assert "CASE EVALUATION MATRIX" in output
    assert "RISK CONFUSION MATRIX" in output
    assert "SEC_PI_001" in output
    assert "Classification accuracy: 100.00%" in output

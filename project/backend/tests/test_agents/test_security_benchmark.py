from pathlib import Path

from app.evaluation.security_benchmark import (
    evaluate_security_cases,
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

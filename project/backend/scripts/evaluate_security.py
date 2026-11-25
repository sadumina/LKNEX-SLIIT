"""Print Security Assessment benchmark metrics as JSON."""

import argparse
import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.security_benchmark import evaluate_security_cases, load_security_cases


DEFAULT_BENCHMARK = (
    BACKEND_ROOT
    / "tests"
    / "fixtures"
    / "security_cases.jsonl"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the Security Assessment Agent")
    parser.add_argument(
        "benchmark",
        nargs="?",
        type=Path,
        default=DEFAULT_BENCHMARK,
        help="Path to a labelled security benchmark JSONL file",
    )
    args = parser.parse_args()
    metrics = evaluate_security_cases(load_security_cases(args.benchmark))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

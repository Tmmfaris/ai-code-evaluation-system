import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.run_benchmark import check_thresholds, run_benchmark


def test_accuracy_benchmark_cases():
    summary = run_benchmark()
    assert not summary["failures"], f"Benchmark failures found: {summary['failures']}"
    threshold_errors = check_thresholds(summary)
    assert not threshold_errors, f"Benchmark threshold failures found: {threshold_errors}"

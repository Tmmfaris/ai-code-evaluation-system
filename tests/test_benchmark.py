import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.run_benchmark import run_benchmark


def test_accuracy_benchmark_cases():
    summary = run_benchmark()
    assert not summary["failures"], f"Benchmark failures found: {summary['failures']}"

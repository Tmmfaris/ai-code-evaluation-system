import json
import os
import sys
from collections import defaultdict


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluator.main_evaluator import evaluate_submission


def load_cases():
    path = os.path.join(os.path.dirname(__file__), "benchmark_cases.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def run_benchmark():
    cases = load_cases()
    total = 0
    passed = 0
    by_language = defaultdict(lambda: {"passed": 0, "total": 0})
    by_category = defaultdict(lambda: {"passed": 0, "total": 0})
    failures = []

    for case in cases:
        result = evaluate_submission(
            student_id=case["id"],
            question=case["question"],
            sample_answer=case["model_answer"],
            student_answer=case["student_answer"],
            language=case["language"],
        )
        score = result["score"]
        ok = case["expected_min_score"] <= score <= case["expected_max_score"]

        total += 1
        by_language[case["language"]]["total"] += 1
        by_category[case["category"]]["total"] += 1

        if ok:
            passed += 1
            by_language[case["language"]]["passed"] += 1
            by_category[case["category"]]["passed"] += 1
        else:
            failures.append({
                "id": case["id"],
                "language": case["language"],
                "category": case["category"],
                "score": score,
                "expected": [case["expected_min_score"], case["expected_max_score"]],
                "feedback": result.get("feedback", ""),
            })

    print("\n=== Accuracy Benchmark ===")
    print(f"Overall: {passed}/{total} passed ({(passed / total * 100):.1f}%)")

    print("\nBy language:")
    for language, stats in sorted(by_language.items()):
        pct = (stats["passed"] / stats["total"] * 100) if stats["total"] else 0.0
        print(f"- {language}: {stats['passed']}/{stats['total']} ({pct:.1f}%)")

    print("\nBy category:")
    for category, stats in sorted(by_category.items()):
        pct = (stats["passed"] / stats["total"] * 100) if stats["total"] else 0.0
        print(f"- {category}: {stats['passed']}/{stats['total']} ({pct:.1f}%)")

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(
                f"- {failure['id']} | {failure['language']} | {failure['category']} | "
                f"score={failure['score']} expected={failure['expected']} | {failure['feedback']}"
            )
    else:
        print("\nNo failures.")

    return {
        "passed": passed,
        "total": total,
        "by_language": dict(by_language),
        "by_category": dict(by_category),
        "failures": failures,
    }


def main():
    run_benchmark()


if __name__ == "__main__":
    main()

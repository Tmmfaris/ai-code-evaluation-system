import json
import os
import sys
from pathlib import Path


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluator.main_evaluator import evaluate_submission


def load_regression_cases():
    path = Path(__file__).with_name("regression_cases.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_regression_cases_hold():
    failures = []

    for case in load_regression_cases():
        result = evaluate_submission(
            student_id=case["student_id"],
            question=case["question"],
            sample_answer=case["model_answer"],
            student_answer=case["student_answer"],
            language=case["language"],
        )

        score = result.get("score", -1)
        feedback = (result.get("feedback") or "").lower()
        expected_text = case.get("expected_feedback_contains")
        expected_texts = []
        if isinstance(expected_text, list):
            expected_texts = [str(item).lower() for item in expected_text if str(item).strip()]
        elif isinstance(expected_text, str) and expected_text.strip():
            expected_texts = [expected_text.lower()]

        score_ok = case["expected_min_score"] <= score <= case["expected_max_score"]
        text_ok = True
        if expected_texts:
            text_ok = any(token in feedback for token in expected_texts)

        if not score_ok or not text_ok:
            failures.append(
                {
                    "id": case["id"],
                    "score": score,
                    "expected_score_range": [
                        case["expected_min_score"],
                        case["expected_max_score"],
                    ],
                    "feedback": result.get("feedback", ""),
                    "expected_feedback_contains": case.get("expected_feedback_contains"),
                }
            )

    assert not failures, f"Regression failures found: {failures}"

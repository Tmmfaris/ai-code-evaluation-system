import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluator.question_package.workflow import prepare_question_profiles_until_correct
from app import (
    DETERMINISTIC_FINAL_FEEDBACK_TEMPLATES,
    _evaluate_single_submission,
    _build_bad_package_detail,
    _build_fixed_evaluation_data,
    _collect_suspicious_reasons,
    _repair_package_backed_feedback,
)
from schemas import QuestionSubmission


def test_bad_package_detail_flags_generic_templates():
    detail = _build_bad_package_detail(
        {
            "question_id": "q-generic",
            "question": "Process a list",
            "package_status": "generated",
            "package_confidence": 0.2,
            "package_summary": "Weak package.",
            "review_required": True,
            "template_family": "python::generic",
        }
    )

    assert "generic_template_family" in detail["flags"]
    assert "package_not_ready" in detail["flags"]
    assert detail["reason"]


def test_suspicious_monitoring_flags_feedback_contradictions():
    evaluation_data = _build_fixed_evaluation_data(
        100,
        "Ensure the function correctly returns True only when the number is zero.",
        "The student used a different approach, but the logic is correct.",
        strong=True,
    )
    reasons = _collect_suspicious_reasons(
        question="Check if number is zero",
        student_answer="def is_zero(n): return n == 0",
        question_metadata={
            "language": "python",
            "package_status": "validated",
            "template_family": "python::zero_check",
            "accepted_solutions": ["def is_zero(n): return n == 0"],
            "incorrect_patterns": [],
        },
        evaluation_data=evaluation_data,
    )

    assert "full_credit_with_corrective_feedback" in reasons


def test_deterministic_final_feedback_registry_includes_guarded_templates():
    expected = {
        "python::zero_check",
        "python::list_length",
        "python::string_endswith",
        "python::uppercase_string",
        "python::odd_check",
        "python::empty_collection_check",
    }
    assert expected.issubset(DETERMINISTIC_FINAL_FEEDBACK_TEMPLATES)


def test_package_backed_generic_feedback_is_repaired_to_specific_pattern_feedback():
    repaired = _repair_package_backed_feedback(
        question="Check if number is odd",
        student_answer="def is_odd(n): return n % 2 == 0",
        question_metadata={
            "language": "python",
            "template_family": "python::odd_check",
            "accepted_solutions": ["def is_odd(n): return n % 2 != 0"],
            "incorrect_patterns": [
                {
                    "pattern": "return n % 2 == 0",
                    "match_type": "contains",
                    "feedback": "This checks even numbers instead of odd numbers.",
                    "score_cap": 20,
                }
            ],
            "test_sets": {
                "positive": [{"input": "[3]", "expected_output": "true"}],
                "negative": [{"input": "[2]", "expected_output": "false"}],
            },
        },
        evaluation_data=_build_fixed_evaluation_data(
            0,
            "The function produces incorrect output for all test cases.",
            "The student logic does not correctly solve the problem yet.",
            strong=False,
        ),
    )

    assert repaired.feedback == "This checks even numbers instead of odd numbers."


def test_register_supports_threshold_lowercase_and_second_element_questions():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q1",
                "question": "Check if number is greater than 10",
                "model_answer": "def greater_10(n): return n > 10",
                "language": "python",
            },
            {
                "question_id": "q2",
                "question": "Return lowercase version of string",
                "model_answer": "def lower(s): return s.lower()",
                "language": "python",
            },
            {
                "question_id": "q3",
                "question": "Return second element of list",
                "model_answer": "def second(lst): return lst[1]",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    by_id = {item["question_id"]: item for item in packages}

    assert by_id["q1"]["template_family"] == "python::greater_than_threshold"
    assert by_id["q1"]["package_status"] in {"validated", "live"}
    assert by_id["q1"]["review_required"] is False

    assert by_id["q2"]["template_family"] == "python::lowercase_string"
    assert by_id["q2"]["package_status"] in {"validated", "live"}
    assert by_id["q2"]["review_required"] is False

    assert by_id["q3"]["template_family"] == "python::second_element"
    assert by_id["q3"]["package_status"] in {"validated", "live"}
    assert by_id["q3"]["review_required"] is False


def test_register_can_infer_specific_family_from_model_answer_for_new_wording():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_new_threshold",
                "question": "Tell whether the value passes the cutoff",
                "model_answer": "def passes_cutoff(n): return n > 10",
                "language": "python",
            },
            {
                "question_id": "q_new_second",
                "question": "Give me the item after the first one in the sequence",
                "model_answer": "def pick(lst): return lst[1]",
                "language": "python",
            },
            {
                "question_id": "q_new_lower",
                "question": "Normalize the text to small letters",
                "model_answer": "def lower_text(s): return s.lower()",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    by_id = {item["question_id"]: item for item in packages}

    assert by_id["q_new_threshold"]["template_family"] == "python::greater_than_threshold"
    assert by_id["q_new_threshold"]["package_status"] in {"validated", "live"}
    assert by_id["q_new_threshold"]["review_required"] is False

    assert by_id["q_new_second"]["template_family"] == "python::second_element"
    assert by_id["q_new_second"]["package_status"] in {"validated", "live"}
    assert by_id["q_new_second"]["review_required"] is False

    assert by_id["q_new_lower"]["template_family"] == "python::lowercase_string"
    assert by_id["q_new_lower"]["package_status"] in {"validated", "live"}
    assert by_id["q_new_lower"]["review_required"] is False


def test_register_uses_model_answer_derived_fallback_for_new_python_question_shapes():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_fallback_python",
                "question": "Decide whether the custom divisibility rule passes",
                "model_answer": "def passes_rule(n): return n % 3 == 0",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::model_answer_derived"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["package_confidence"] >= 0.9


def test_evaluation_bootstraps_missing_package_when_inline_context_is_provided():
    submission = QuestionSubmission(
        question_id="q_bootstrap_eval",
        question="Decide whether the custom divisibility rule passes",
        model_answer="def passes_rule(n): return n % 3 == 0",
        student_answer="def passes_rule(n): return n % 3 == 0",
        language="python",
    )

    result = _evaluate_single_submission("student-bootstrap", submission, False, False, 1)

    assert "error" not in result
    assert result["question_metadata"]["template_family"] == "python::model_answer_derived"
    assert result["question_metadata"]["package_status"] in {"validated", "live"}
    assert result["data"].score == 100

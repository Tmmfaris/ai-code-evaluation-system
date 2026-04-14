import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import _evaluate_single_submission
from evaluator.question_package.workflow import prepare_question_profiles_until_correct
from evaluator.question_profile_repository import build_question_signature
from evaluator.question_profile_store import get_question_profile_fresh
from schemas import QuestionSubmission


def _register_core_packages():
    payload = [
        {
            "question_id": "q_zero_check",
            "question": "Check if number is zero",
            "model_answer": "def is_zero(n): return n == 0",
            "language": "python",
        },
        {
            "question_id": "q_list_length",
            "question": "Return number of elements in list",
            "model_answer": "def count(lst): return len(lst)",
            "language": "python",
        },
        {
            "question_id": "q_string_endswith",
            "question": "Check if string ends with 'z'",
            "model_answer": "def ends_z(s): return s.endswith('z')",
            "language": "python",
        },
        {
            "question_id": "q_odd_check",
            "question": "Check if number is odd",
            "model_answer": "def is_odd(n): return n % 2 != 0",
            "language": "python",
        },
        {
            "question_id": "q_empty_collection",
            "question": "Check if list is empty",
            "model_answer": "def empty(lst): return len(lst) == 0",
            "language": "python",
        },
        {
            "question_id": "q_greater_than_threshold",
            "question": "Check if number is greater than 10",
            "model_answer": "def greater_10(n): return n > 10",
            "language": "python",
        },
        {
            "question_id": "q_lowercase_string",
            "question": "Return lowercase version of string",
            "model_answer": "def lower(s): return s.lower()",
            "language": "python",
        },
        {
            "question_id": "q_second_element",
            "question": "Return second element of list",
            "model_answer": "def second(lst): return lst[1]",
            "language": "python",
        },
    ]
    return prepare_question_profiles_until_correct(payload, force_llm=False)


def test_signature_normalization_is_shared():
    signature = build_question_signature("Check if string ends with 'z'", "python")
    assert signature == "python::check if string ends with z"


def test_registered_packages_are_specific_and_ready():
    packages = _register_core_packages()
    package_map = {item["question_id"]: item for item in packages}

    assert package_map["q_zero_check"]["template_family"] == "python::zero_check"
    assert package_map["q_list_length"]["template_family"] == "python::list_length"
    assert package_map["q_string_endswith"]["template_family"] == "python::string_endswith"
    assert package_map["q_odd_check"]["template_family"] == "python::odd_check"
    assert package_map["q_empty_collection"]["template_family"] == "python::empty_collection_check"
    assert package_map["q_greater_than_threshold"]["template_family"] == "python::greater_than_threshold"
    assert package_map["q_lowercase_string"]["template_family"] == "python::lowercase_string"
    assert package_map["q_second_element"]["template_family"] == "python::second_element"

    for item in packages:
        assert item["package_status"] in {"validated", "live"}
        assert item["review_required"] is False
        assert item["package_confidence"] >= 0.9
        assert len((item.get("test_sets") or {}).get("positive", [])) >= 2
        assert len((item.get("test_sets") or {}).get("negative", [])) >= 1
        assert len(item.get("incorrect_patterns") or []) >= 2


def test_evaluation_uses_registered_package_metadata():
    _register_core_packages()
    signature = build_question_signature("Return number of elements in list", "python")
    profile = get_question_profile_fresh(signature)
    assert profile is not None
    assert profile["template_family"] == "python::list_length"

    submission = QuestionSubmission(
        question_id="q_list_length",
        question="Return number of elements in list",
        model_answer="def count(lst): return len(lst)",
        student_answer="def count(lst): return 1",
        language="python",
    )
    result = _evaluate_single_submission("student-a", submission, False, False, 1)

    assert result["question_metadata"]["template_family"] == "python::list_length"
    assert result["question_metadata"]["package_status"] in {"validated", "live"}


def test_deterministic_scoring_beats_llm_feedback():
    _register_core_packages()

    cases = [
        (
            QuestionSubmission(
                question_id="q_zero_check",
                question="Check if number is zero",
                model_answer="def is_zero(n): return n == 0",
                student_answer="def is_zero(n): return not n",
                language="python",
            ),
            100,
            "correctly checks whether the number is zero",
        ),
        (
            QuestionSubmission(
                question_id="q_list_length",
                question="Return number of elements in list",
                model_answer="def count(lst): return len(lst)",
                student_answer="def count(lst): return 1",
                language="python",
            ),
            0,
            "does not correctly count the number of elements in the list",
        ),
        (
            QuestionSubmission(
                question_id="q_string_endswith",
                question="Check if string ends with 'z'",
                model_answer="def ends_z(s): return s.endswith('z')",
                student_answer="def ends_z(s): return s[-1] == 'z'",
                language="python",
            ),
            0,
            "fail on empty strings",
        ),
    ]

    for submission, expected_score, feedback_snippet in cases:
        result = _evaluate_single_submission("student-b", submission, False, False, 1)
        assert result["data"].score == expected_score
        feedback = result["data"].feedback.lower()
        assert "safe fallback" not in feedback
        if feedback_snippet == "correctly checks whether the number is zero":
            assert feedback_snippet in feedback
        elif feedback_snippet == "fail on empty strings":
            assert "empty string" in feedback
        else:
            assert ("count" in feedback and "element" in feedback) or "test case" in feedback


def test_package_backed_evaluation_does_not_call_llm_scoring(monkeypatch):
    _register_core_packages()

    def _boom(*args, **kwargs):
        raise AssertionError("LLM scoring path should not be used for package-backed deterministic evaluation")

    monkeypatch.setattr("evaluator.comparison.llm_comparator.compare_answers_with_llm", _boom)
    monkeypatch.setattr("evaluator.comparison.llm_comparator.audit_evaluation_with_llm", _boom)

    submission = QuestionSubmission(
        question_id="q_list_length",
        question="Return number of elements in list",
        model_answer="def count(lst): return len(lst)",
        student_answer="def count(lst): return len(lst) + 0",
        language="python",
    )
    result = _evaluate_single_submission("student-c", submission, False, False, 1)
    assert result["data"].score == 100


@pytest.mark.parametrize(
    "submission, expected_feedback_contains",
    [
        (
            QuestionSubmission(
                question_id="q_odd_check",
                question="Check if number is odd",
                model_answer="def is_odd(n): return n % 2 != 0",
                student_answer="def is_odd(n): return n % 2 == 0",
                language="python",
            ),
            "even numbers instead of odd numbers",
        ),
        (
            QuestionSubmission(
                question_id="q_empty_collection",
                question="Check if list is empty",
                model_answer="def empty(lst): return len(lst) == 0",
                student_answer="def empty(lst): return lst",
                language="python",
            ),
            "returning the list itself does not check whether it is empty",
        ),
        (
            QuestionSubmission(
                question_id="q_uppercase_string",
                question="Return uppercase version of string",
                model_answer="def upper(s): return s.upper()",
                student_answer='def upper(s): return "ABC"',
                language="python",
            ),
            "returning a constant string does not convert the input string to uppercase",
        ),
        (
            QuestionSubmission(
                question_id="q_greater_than_threshold",
                question="Check if number is greater than 10",
                model_answer="def greater_10(n): return n > 10",
                student_answer="def greater_10(n): return n >= 10",
                language="python",
            ),
            "strictly greater than 10",
        ),
        (
            QuestionSubmission(
                question_id="q_lowercase_string",
                question="Return lowercase version of string",
                model_answer="def lower(s): return s.lower()",
                student_answer="def lower(s): return s.lower",
                language="python",
            ),
            "returns the lower method itself instead of calling it",
        ),
        (
            QuestionSubmission(
                question_id="q_lowercase_string",
                question="Return lowercase version of string",
                model_answer="def lower(s): return s.lower()",
                student_answer='def lower(s): return "abc"',
                language="python",
            ),
            "returning a constant string does not convert the input string to lowercase",
        ),
        (
            QuestionSubmission(
                question_id="q_second_element",
                question="Return second element of list",
                model_answer="def second(lst): return lst[1]",
                student_answer="def second(lst): return lst",
                language="python",
            ),
            "returning the list itself does not return the second element",
        ),
    ],
)
def test_new_package_backed_templates_keep_deterministic_feedback(submission, expected_feedback_contains):
    _register_core_packages()
    result = _evaluate_single_submission("student-d", submission, False, False, 1)
    assert result["data"].score == 0
    assert expected_feedback_contains in result["data"].feedback.lower()
    assert "safe fallback" not in result["data"].feedback.lower()

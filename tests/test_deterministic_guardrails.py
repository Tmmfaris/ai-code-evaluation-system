import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import _evaluate_single_submission, _match_incorrect_pattern
from evaluator.question_package.workflow import prepare_question_profiles_until_correct
from evaluator.question_profile_repository import build_question_signature
from evaluator.question_profile_store import get_question_profile_fresh
from evaluator.orchestration.pipeline import _match_package_incorrect_pattern
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
            "question_id": "q_divisible_by_four",
            "question": "Check if number is divisible by 4",
            "model_answer": "def div4(n): return n % 4 == 0",
            "language": "python",
        },
        {
            "question_id": "q_divisible_by_ten",
            "question": "Check if number is divisible by 10",
            "model_answer": "def div10(n): return n % 10 == 0",
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
        {
            "question_id": "q_non_empty_collection",
            "question": "Check if list has at least one element",
            "model_answer": "def has_items(lst): return len(lst) > 0",
            "language": "python",
        },
        {
            "question_id": "q_first_two_characters",
            "question": "Return first two characters of string",
            "model_answer": "def first2(s): return s[:2]",
            "language": "python",
        },
        {
            "question_id": "q_list_length_equals_five",
            "question": "Check if list length equals 5",
            "model_answer": "def len5(lst): return len(lst) == 5",
            "language": "python",
        },
        {
            "question_id": "q_first_three_characters",
            "question": "Return first three characters of string",
            "model_answer": "def first3(s): return s[:3]",
            "language": "python",
        },
        {
            "question_id": "q_third_element",
            "question": "Return third element of list",
            "model_answer": "def third(lst): return lst[2]",
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
    assert package_map["q_divisible_by_four"]["template_family"] == "python::divisible_by_constant"
    assert package_map["q_divisible_by_ten"]["template_family"] == "python::divisible_by_constant"
    assert package_map["q_list_length"]["template_family"] == "python::list_length"
    assert package_map["q_string_endswith"]["template_family"] == "python::string_endswith"
    assert package_map["q_odd_check"]["template_family"] == "python::odd_check"
    assert package_map["q_empty_collection"]["template_family"] == "python::empty_collection_check"
    assert package_map["q_greater_than_threshold"]["template_family"] == "python::greater_than_threshold"
    assert package_map["q_lowercase_string"]["template_family"] == "python::lowercase_string"
    assert package_map["q_second_element"]["template_family"] == "python::second_element"
    assert package_map["q_non_empty_collection"]["template_family"] == "python::non_empty_collection_check"
    assert package_map["q_first_two_characters"]["template_family"] == "python::first_two_characters"
    assert package_map["q_list_length_equals_five"]["template_family"] == "python::list_length_equals_constant"
    assert package_map["q_first_three_characters"]["template_family"] == "python::prefix_characters_constant"
    assert package_map["q_third_element"]["template_family"] == "python::element_at_index_constant"

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
    monkeypatch.setattr("evaluator.comparison.llm_comparator.rephrase_feedback_with_llm", _boom)
    monkeypatch.setattr("evaluator.orchestration.pipeline.is_llm_available", lambda: True)

    submission = QuestionSubmission(
        question_id="q_list_length",
        question="Return number of elements in list",
        model_answer="def count(lst): return len(lst)",
        student_answer="def count(lst): return len(lst) + 0",
        language="python",
    )
    result = _evaluate_single_submission("student-c", submission, False, False, 1)
    assert result["data"].score == 100


def test_expanded_positive_feedback_stays_explanatory():
    _register_core_packages()
    submission = QuestionSubmission(
        question_id="q_greater_than_threshold",
        question="Check if number is greater than 10",
        model_answer="def greater_10(n): return n > 10",
        student_answer="def greater_10(n): return n > 10",
        language="python",
    )

    result = _evaluate_single_submission("student-feedback-positive", submission, False, False, 1)
    feedback = result["data"].feedback.lower()
    assert result["data"].score == 100
    assert "strict comparison" in feedback
    assert "threshold value itself" in feedback


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
                question_id="q_divisible_by_four",
                question="Check if number is divisible by 4",
                model_answer="def div4(n): return n % 4 == 0",
                student_answer="def div4(n): return n % 2 == 0",
                language="python",
            ),
            "checking divisibility by 2 includes extra even numbers that are not necessarily divisible by 4",
        ),
        (
            QuestionSubmission(
                question_id="q_divisible_by_ten",
                question="Check if number is divisible by 10",
                model_answer="def div10(n): return n % 10 == 0",
                student_answer="def div10(n): return True",
                language="python",
            ),
            "always returning true does not check whether the number is divisible by 10",
        ),
        (
            QuestionSubmission(
                question_id="q_divisible_by_ten",
                question="Check if number is divisible by 10",
                model_answer="def div10(n): return n % 10 == 0",
                student_answer="def div10(n): return n % 5 == 0",
                language="python",
            ),
            "checking divisibility by 5 does not solve the stated problem",
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
        (
            QuestionSubmission(
                question_id="q_second_element",
                question="Return second element of list",
                model_answer="def second(lst): return lst[1]",
                student_answer="def second(lst): return lst[-len(lst)+1]",
                language="python",
            ),
            "the function correctly returns the second element of the list",
        ),
        (
            QuestionSubmission(
                question_id="q_non_empty_collection",
                question="Check if list has at least one element",
                model_answer="def has_items(lst): return len(lst) > 0",
                student_answer="def has_items(lst): return len(lst) == 0",
                language="python",
            ),
            "checking whether the list is empty solves the opposite problem",
        ),
        (
            QuestionSubmission(
                question_id="q_first_two_characters",
                question="Return first two characters of string",
                model_answer="def first2(s): return s[:2]",
                student_answer="def first2(s): return s[0:2]",
                language="python",
            ),
            "the function correctly returns the first two characters of the string",
        ),
        (
            QuestionSubmission(
                question_id="q_first_two_characters",
                question="Return first two characters of string",
                model_answer="def first2(s): return s[:2]",
                student_answer="def first2(s): return s[0]",
                language="python",
            ),
            "returning only the first character does not satisfy the requirement to return the first two characters",
        ),
        (
            QuestionSubmission(
                question_id="q_first_two_characters",
                question="Return first two characters of string",
                model_answer="def first2(s): return s[:2]",
                student_answer="def first2(s): return s[2:]",
                language="python",
            ),
            "returning the characters after index 1 does not satisfy the requirement to return the first two characters",
        ),
        (
            QuestionSubmission(
                question_id="q_list_length_equals_five",
                question="Check if list length equals 5",
                model_answer="def len5(lst): return len(lst) == 5",
                student_answer="def len5(lst): return len(lst)",
                language="python",
            ),
            "returning the list length itself does not answer the yes-or-no question",
        ),
        (
            QuestionSubmission(
                question_id="q_list_length_equals_five",
                question="Check if list length equals 5",
                model_answer="def len5(lst): return len(lst) == 5",
                student_answer="def len5(lst): return len(lst) >= 5",
                language="python",
            ),
            "using >= allows lists longer than 5, but this task requires the length to be exactly 5",
        ),
        (
            QuestionSubmission(
                question_id="q_list_length_equals_five",
                question="Check if list length equals 5",
                model_answer="def len5(lst): return len(lst) == 5",
                student_answer="def len5(lst): return False",
                language="python",
            ),
            "always returning false does not check whether the list length is exactly 5",
        ),
        (
            QuestionSubmission(
                question_id="q_list_length_equals_five",
                question="Check if list length equals 5",
                model_answer="def len5(lst): return len(lst) == 5",
                student_answer="def len5(lst): return lst",
                language="python",
            ),
            "returning the list itself does not answer whether its length is exactly 5",
        ),
        (
            QuestionSubmission(
                question_id="q_first_three_characters",
                question="Return first three characters of string",
                model_answer="def first3(s): return s[:3]",
                student_answer="def first3(s): return s[:2]",
                language="python",
            ),
            "returning fewer than 3 characters does not satisfy the requirement to return the first 3 characters",
        ),
        (
            QuestionSubmission(
                question_id="q_third_element",
                question="Return third element of list",
                model_answer="def third(lst): return lst[2]",
                student_answer="def third(lst): return lst[1]",
                language="python",
            ),
            "returning the item at index 1 does not satisfy the requirement to return the element at position 3",
        ),
    ],
)
def test_new_package_backed_templates_keep_deterministic_feedback(submission, expected_feedback_contains):
    _register_core_packages()
    result = _evaluate_single_submission("student-d", submission, False, False, 1)
    if "the function correctly" in expected_feedback_contains:
        assert result["data"].score == 100
    else:
        assert result["data"].score == 0
    assert expected_feedback_contains in result["data"].feedback.lower()
    assert "safe fallback" not in result["data"].feedback.lower()


def test_expanded_negative_feedback_stays_explanatory():
    _register_core_packages()
    submission = QuestionSubmission(
        question_id="q_lowercase_string",
        question="Return lowercase version of string",
        model_answer="def lower(s): return s.lower()",
        student_answer='def lower(s): return "abc"',
        language="python",
    )

    result = _evaluate_single_submission("student-feedback-negative", submission, False, False, 1)
    feedback = result["data"].feedback.lower()
    assert result["data"].score == 0
    assert "provided input" in feedback
    assert "ignoring it" in feedback


def test_bare_return_incorrect_patterns_do_not_overmatch_related_code():
    assert not _match_incorrect_pattern(
        "def first2(s): return s[0:2]",
        {"pattern": "return s", "match_type": "contains"},
    )
    assert not _match_incorrect_pattern(
        "def first2(s): return s[2:]",
        {"pattern": "return s", "match_type": "contains"},
    )
    assert not _match_incorrect_pattern(
        "def len5(lst): return len(lst) >= 5",
        {"pattern": "return len(lst)", "match_type": "contains"},
    )
    assert _match_incorrect_pattern(
        "def len5(lst): return len(lst)",
        {"pattern": "return len(lst)", "match_type": "contains"},
    )


def test_package_rule_bare_return_patterns_do_not_overmatch_related_code():
    assert not _match_package_incorrect_pattern(
        "def first2(s): return s[0:2]",
        {"pattern": "return s", "match_type": "contains"},
    )
    assert not _match_package_incorrect_pattern(
        "def len5(lst): return len(lst) >= 5",
        {"pattern": "return len(lst)", "match_type": "contains"},
    )
    assert _match_package_incorrect_pattern(
        "def len5(lst): return len(lst)",
        {"pattern": "return len(lst)", "match_type": "contains"},
    )

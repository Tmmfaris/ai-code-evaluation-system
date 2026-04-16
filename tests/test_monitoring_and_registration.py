import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import app as app_module
from evaluator.question_rule_generator import finalize_question_profile, merge_with_existing_profiles
from evaluator.question_package.workflow import prepare_question_profiles_until_correct
from evaluator.execution.shared import generate_universal_oracle_test_package_for_registration
from app import (
    DETERMINISTIC_FINAL_FEEDBACK_TEMPLATES,
    _evaluate_single_submission,
    _build_bad_package_detail,
    _build_fixed_evaluation_data,
    _collect_suspicious_reasons,
    _repair_package_backed_feedback,
    _sanitize_hidden_tests_for_template_family,
)
from schemas import QuestionSubmission


@pytest.fixture(autouse=True)
def _fast_register_llm(monkeypatch):
    def _fake_llm(_prompt):
        return """
        {
          "accepted_solutions": [],
          "test_sets": {"positive": [], "negative": []},
          "incorrect_patterns": []
        }
        """

    monkeypatch.setattr("evaluator.question_rule_generator.call_llm", _fake_llm)


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


def test_register_supports_non_empty_collection_question():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_has_items",
                "question": "Check if list has at least one element",
                "model_answer": "def has_items(lst): return len(lst) > 0",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::non_empty_collection_check"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["package_confidence"] >= 0.9
    assert any(
        item.get("input") == "[[]]" and item.get("expected_output") == "false"
        for item in (package.get("test_sets") or {}).get("negative", [])
    )


def test_register_supports_divisible_by_constant_question():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_div4",
                "question": "Check if number is divisible by 4",
                "model_answer": "def div4(n): return n % 4 == 0",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::divisible_by_constant"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["package_confidence"] >= 0.9
    assert len((package.get("test_sets") or {}).get("negative") or []) >= 1
    assert any(
        item.get("pattern") == "return n % 2 == 0"
        for item in (package.get("incorrect_patterns") or [])
    )


def test_register_supports_first_two_characters_question():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_first2",
                "question": "Return first two characters of string",
                "model_answer": "def first2(s): return s[:2]",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::first_two_characters"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["package_confidence"] >= 0.9
    assert any(
        item.get("pattern") == "return s[0]"
        for item in (package.get("incorrect_patterns") or [])
    )


def test_register_supports_middle_character_question():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_middle",
                "question": "Return middle character of string (assume odd length)",
                "model_answer": "def middle(s): return s[len(s)//2]",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::middle_character"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert any((item or {}).get("input") == "[\"abc\"]" for item in (package.get("test_sets") or {}).get("positive", []))
    assert not any("[[1,2,3]]" == (item or {}).get("input") for item in (package.get("hidden_tests") or []))


def test_register_first_and_last_character_does_not_include_non_string_oracle_tests():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_ends",
                "question": "Return first and last character of string",
                "model_answer": "def ends(s): return s[0] + s[-1]",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::first_and_last_character"
    assert not any(
        (item or {}).get("input") == "[[1,2,3]]"
        for item in (package.get("hidden_tests") or [])
    )
    assert not any(
        "f-string" in ((item or {}).get("feedback") or "").lower()
        for item in (package.get("incorrect_patterns") or [])
    )


def test_universal_oracle_registration_package_handles_snippet_model_answer():
    # A bare snippet (no def) must still be runnable via wrapping.
    oracle = generate_universal_oracle_test_package_for_registration(
        "Check if number is multiple of 3",
        "return n % 3 == 0",
        n_cases=8,
    )
    assert oracle is not None
    tests = (oracle.get("test_sets") or {}).get("positive") or []
    assert len(tests) >= 3


def test_sanitize_hidden_tests_filters_non_string_cases_for_first_and_last_family():
    cleaned = _sanitize_hidden_tests_for_template_family(
        "python::first_and_last_character",
        [
            {"input": "[\"python\"]", "expected_output": "pn", "required": True},
            {"input": "[[1,2,3]]", "expected_output": "4", "required": False},
            {"input": "[\"\"]", "expected_output": "", "required": False},
        ],
    )

    assert any(item.get("input") == "[\"python\"]" for item in cleaned)
    assert not any(item.get("input") == "[[1,2,3]]" for item in cleaned)

def test_register_supports_list_contains_constant_question():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_has5",
                "question": "Check if list contains value 5",
                "model_answer": "def has5(lst): return 5 in lst",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::list_contains_constant"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert any((item or {}).get("expected_output") == "true" and (item or {}).get("required") for item in (package.get("test_sets") or {}).get("positive", []))
    assert any((item or {}).get("expected_output") == "false" and (item or {}).get("required") for item in (package.get("test_sets") or {}).get("negative", []))


def test_finalize_middle_character_discards_stale_non_string_tests_from_reuse():
    merged = merge_with_existing_profiles(
        {
            "question_id": "q_middle",
            "question": "Return middle character of string (assume odd length)",
            "model_answer": "def middle(s): return s[len(s)//2]",
            "language": "python",
            "accepted_solutions": ["def middle(s): return s[len(s)//2]"],
            "test_sets": {
                "positive": [
                    {"input": "[\"abc\"]", "expected_output": "b", "description": "fresh middle test", "required": True},
                ],
                "negative": [
                    {"input": "[\"radar\"]", "expected_output": "d", "description": "fresh trap", "required": True},
                ],
            },
            "incorrect_patterns": [],
        },
        [
            {
                "question": "Return middle character of string (assume odd length)",
                "language": "python",
                "model_answer": "def middle(s): return s[len(s)//2]",
                "template_family": "python::middle_character",
                "package_status": "validated",
                "review_required": False,
                "package_confidence": 1.0,
                "accepted_solutions": ["def middle(s): return s[len(s)//2]"],
                "hidden_tests": [
                    {"input": "[[1,2,3]]", "expected_output": "2", "description": "stale bad test"},
                    {"input": "[\"Ab\"]", "expected_output": "b", "description": "stale even-length string"},
                ],
                "test_sets": {"positive": [], "negative": []},
                "incorrect_patterns": [],
            }
        ],
    )

    finalized = finalize_question_profile(merged)
    test_sets = finalized.get("test_sets") or {}
    all_items = list(test_sets.get("positive") or []) + list(test_sets.get("negative") or [])
    all_inputs = {(item or {}).get("input") for item in all_items}

    assert finalized["template_family"] == "python::middle_character"
    assert "[[1,2,3]]" not in all_inputs
    assert "[\"Ab\"]" not in all_inputs
    assert "[\"abc\"]" in all_inputs


def test_finalize_list_contains_constant_discards_stale_wrong_shape_tests_from_reuse():
    merged = merge_with_existing_profiles(
        {
            "question_id": "q_has5",
            "question": "Check if list contains value 5",
            "model_answer": "def has5(lst): return 5 in lst",
            "language": "python",
            "accepted_solutions": ["def has5(lst): return 5 in lst"],
            "test_sets": {
                "positive": [
                    {"input": "[[5,3,1]]", "expected_output": "true", "description": "fresh positive", "required": True},
                ],
                "negative": [
                    {"input": "[[1,2,3]]", "expected_output": "false", "description": "fresh negative", "required": True},
                ],
            },
            "incorrect_patterns": [],
        },
        [
            {
                "question": "Check if list contains value 5",
                "language": "python",
                "model_answer": "def has5(lst): return 5 in lst",
                "template_family": "python::list_contains_constant",
                "package_status": "validated",
                "review_required": False,
                "package_confidence": 1.0,
                "accepted_solutions": ["def has5(lst): return 5 in lst"],
                "hidden_tests": [
                    {"input": "[\"abc\"]", "expected_output": "true", "description": "stale wrong input shape"},
                    {"input": "[[1,2,3]]", "expected_output": "\"false\"", "description": "stale wrong output type"},
                ],
                "test_sets": {"positive": [], "negative": []},
                "incorrect_patterns": [],
            }
        ],
    )

    finalized = finalize_question_profile(merged)
    test_sets = finalized.get("test_sets") or {}
    all_items = list(test_sets.get("positive") or []) + list(test_sets.get("negative") or [])
    all_inputs = {(item or {}).get("input") for item in all_items}

    assert finalized["template_family"] == "python::list_contains_constant"
    assert "[\"abc\"]" not in all_inputs
    assert "[[5,3,1]]" in all_inputs
    assert any((item or {}).get("expected_output") == "true" for item in all_items)


def test_register_supports_list_length_equals_constant_question():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_len5",
                "question": "Check if list length equals 5",
                "model_answer": "def len5(lst): return len(lst) == 5",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::list_length_equals_constant"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["package_confidence"] >= 0.9
    assert any(
        item.get("input") == "[[0,1,2,3,4]]" and item.get("expected_output") == "true"
        for item in (package.get("test_sets") or {}).get("positive", [])
    )


def test_register_supports_first_last_character_and_exact_len_two_payload():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q1",
                "question": "Check if number is multiple of 3",
                "model_answer": "def mult3(n): return n % 3 == 0",
                "language": "python",
            },
            {
                "question_id": "q2",
                "question": "Return first and last character of string",
                "model_answer": "def ends(s): return s[0] + s[-1]",
                "language": "python",
            },
            {
                "question_id": "q3",
                "question": "Check if list length is exactly 2",
                "model_answer": "def len2(lst): return len(lst) == 2",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    by_id = {item["question_id"]: item for item in packages}

    assert by_id["q1"]["template_family"] in {"python::divisible_by_constant", "python::model_answer_derived"}
    assert by_id["q1"]["package_status"] in {"validated", "live"}
    assert by_id["q1"]["review_required"] is False

    assert by_id["q2"]["template_family"] == "python::first_and_last_character"
    assert by_id["q2"]["package_status"] in {"validated", "live"}
    assert by_id["q2"]["review_required"] is False
    assert by_id["q2"]["package_confidence"] >= 0.9

    assert by_id["q3"]["template_family"] == "python::list_length_equals_constant"
    assert by_id["q3"]["package_status"] in {"validated", "live"}
    assert by_id["q3"]["review_required"] is False
    assert by_id["q3"]["package_confidence"] >= 0.9


def test_boolean_expected_false_cases_are_rebucketed_to_negative_tests():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_div10_bucketing",
                "question": "Check if number is divisible by 10",
                "model_answer": "def div10(n): return n % 10 == 0",
                "language": "python",
            },
            {
                "question_id": "q_len5_bucketing",
                "question": "Check if list length equals 5",
                "model_answer": "def len5(lst): return len(lst) == 5",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    by_id = {item["question_id"]: item for item in packages}

    for package in by_id.values():
        positives = (package.get("test_sets") or {}).get("positive") or []
        negatives = (package.get("test_sets") or {}).get("negative") or []
        assert all(item.get("expected_output") != "false" for item in positives)
        assert any(item.get("expected_output") == "false" for item in negatives)


def test_hidden_tests_are_deduplicated_in_final_package_response():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_div10_no_dupes",
                "question": "Check if number is divisible by 10",
                "model_answer": "def div10(n): return n % 10 == 0",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    hidden_tests = (package.get("test_sets") or {}).get("positive", []) + (package.get("test_sets") or {}).get("negative", [])
    keys = [(item.get("input"), item.get("expected_output"), item.get("description")) for item in hidden_tests]
    assert len(keys) == len(set(keys))


def test_register_supports_prefix_and_element_parameterized_families():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_first3",
                "question": "Return first three characters of string",
                "model_answer": "def first3(s): return s[:3]",
                "language": "python",
            },
            {
                "question_id": "q_third",
                "question": "Return third element of list",
                "model_answer": "def third(lst): return lst[2]",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    by_id = {item["question_id"]: item for item in packages}
    assert by_id["q_first3"]["template_family"] == "python::prefix_characters_constant"
    assert by_id["q_first3"]["package_status"] in {"validated", "live"}
    assert by_id["q_third"]["template_family"] == "python::element_at_index_constant"
    assert by_id["q_third"]["package_status"] in {"validated", "live"}


def test_register_sanitizes_lowercase_and_second_element_incorrect_pattern_feedback():
    packages = prepare_question_profiles_until_correct(
        [
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

    lowercase_patterns = {
        (item["pattern"], item["feedback"])
        for item in by_id["q2"]["incorrect_patterns"]
    }
    second_element_patterns = {
        (item["pattern"], item["feedback"])
        for item in by_id["q3"]["incorrect_patterns"]
    }

    assert (
        "def lower(s): return s.lower",
        "Returning the lower method itself does not convert the input string. Call s.lower() to return the lowercase string.",
    ) in lowercase_patterns
    assert (
        "def lower(s): return \"abc\"",
        "Returning a constant string does not convert the input string to lowercase.",
    ) in lowercase_patterns
    assert (
        "def second(lst): return lst",
        "Returning the whole list does not return the second element. The task asks for a single item, so the function should return the value at index 1 instead of the entire list.",
    ) in second_element_patterns
    assert (
        "def second(lst): return lst[0]",
        "Returning the first element does not satisfy the second-element requirement. The task asks for the item at index 1, not the item at index 0.",
    ) in second_element_patterns


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


def test_register_builds_stronger_suffix_character_packages():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_suffix_two",
                "question": "Give back the last two characters of string",
                "model_answer": "def last2(s): return s[-2:]",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    positive = (package.get("test_sets") or {}).get("positive") or []
    negative = (package.get("test_sets") or {}).get("negative") or []
    patterns = package.get("incorrect_patterns") or []

    assert package["template_family"] == "python::suffix_characters_constant"
    assert package["package_status"] in {"validated", "live"}
    assert any((item or {}).get("input") == "[\"a\"]" for item in positive)
    assert any((item or {}).get("description") == "exact-length string input" for item in positive)
    assert any((item or {}).get("pattern") == "return s[-1:]" for item in patterns)
    assert any((item or {}).get("pattern") == "return s[:-2]" for item in patterns)
    assert len(negative) >= 1


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
    assert package["template_family"] in {"python::model_answer_derived", "python::divisible_by_constant"}
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["package_confidence"] >= 0.9


def test_register_builds_oracle_backed_model_answer_derived_package_for_new_python_transform():
    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_fallback_transform",
                "question": "Apply the faculty rule to the incoming value",
                "model_answer": "def transform(n): return n + 5",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::model_answer_derived"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert len((package.get("test_sets") or {}).get("positive") or []) >= 2
    assert len(package.get("accepted_solutions") or []) >= 1


def test_register_marks_package_as_llm_assisted_when_llm_generation_contributes(monkeypatch):
    def _fake_llm(_prompt):
        return """
        {
          "accepted_solutions": ["return n > 10"],
          "test_sets": {
            "positive": [{"input": "[11]", "expected_output": "true", "description": "llm positive"}],
            "negative": [{"input": "[10]", "expected_output": "false", "description": "llm negative"}]
          },
          "incorrect_patterns": [
            {
              "pattern": "return n >= 10",
              "match_type": "contains",
              "feedback": "Using >= includes 10.",
              "suggestion": "Use n > 10.",
              "score_cap": 20
            }
          ]
        }
        """

    monkeypatch.setattr("evaluator.question_rule_generator.call_llm", _fake_llm)

    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_llm_helped_threshold",
                "question": "Check if number is greater than 10",
                "model_answer": "def greater_10(n): return n > 10",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["llm_assisted"] is True
    assert "llm_generation" in (package.get("generation_sources") or [])


def test_register_accepts_fenced_json_as_llm_registration_contribution(monkeypatch):
    monkeypatch.setattr(
        "evaluator.question_rule_generator.call_llm",
        lambda _prompt: """
        ```json
        {"accepted_solutions":[],"test_sets":{"positive":[],"negative":[]},"incorrect_patterns":[]}
        ```
        """,
    )

    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_fenced_llm_json",
                "question": "Check if number is greater than 10",
                "model_answer": "def greater_10(n): return n > 10",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["llm_assisted"] is True
    assert "llm_generation" in (package.get("generation_sources") or [])
    assert package["package_status"] in {"validated", "live"}


def test_register_does_not_count_scoring_fallback_json_as_llm_package(monkeypatch):
    monkeypatch.setattr(
        "evaluator.question_rule_generator.call_llm",
        lambda _prompt: """
        {"score":50,"feedback":"fallback","concepts":{},"rubric":{"correctness":0}}
        """,
    )

    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_scoring_fallback_not_package",
                "question": "Check if the scoring fallback probe number is greater than 10",
                "model_answer": "def scoring_fallback_probe(n): return n > 10",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["llm_assisted"] is False
    assert package["package_status"] == "generated"
    assert "GGUF assistance is required" in package["package_summary"]


def test_register_uses_deterministic_primary_path_when_specific_package_is_exact(monkeypatch):
    monkeypatch.setattr("evaluator.question_rule_generator.call_llm", lambda _prompt: "not valid json")

    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_len5_deterministic_primary",
                "question": "Check if list length equals 5",
                "model_answer": "def len5(lst): return len(lst) == 5",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::list_length_equals_constant"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["llm_assisted"] is False
    assert "GGUF assistance is required" not in (package.get("package_summary") or "")


def test_register_uses_model_answer_analysis_for_new_shape_even_without_usable_llm(monkeypatch):
    monkeypatch.setattr("evaluator.question_rule_generator.call_llm", lambda _prompt: "not valid json")

    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_first3_deterministic_primary",
                "question": "Return first three characters of string",
                "model_answer": "def first3(s): return s[:3]",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["template_family"] == "python::prefix_characters_constant"
    assert package["package_status"] in {"validated", "live"}
    assert package["review_required"] is False
    assert package["llm_assisted"] is False
    assert "GGUF assistance is required" not in (package.get("package_summary") or "")


def test_register_uses_one_json_repair_call_for_malformed_gguf_output(monkeypatch):
    responses = iter(
        [
            "Here is the package: accepted solution is n > 10",
            '{"accepted_solutions":[],"test_sets":{"positive":[],"negative":[]},"incorrect_patterns":[]}',
        ]
    )

    monkeypatch.setattr("evaluator.question_rule_generator.call_llm", lambda _prompt: next(responses))

    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_llm_repair_package",
                "question": "Check if number is greater than 10",
                "model_answer": "def greater_10(n): return n > 10",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["llm_assisted"] is True
    assert "llm_generation_repair" in (package.get("generation_sources") or [])
    assert package["package_status"] in {"validated", "live"}


def test_reused_from_questions_hides_internal_probe_questions():
    merged = merge_with_existing_profiles(
        {
            "question_id": "q_clean_reuse",
            "question": "Check if number is greater than 10",
            "model_answer": "def greater_10(n): return n > 10",
            "language": "python",
        },
        [
            {
                "question": "Check if the guardrail probe number is greater than 10",
                "model_answer": "def guardrail_probe(n): return n > 10",
                "language": "python",
                "template_family": "python::greater_than_threshold",
                "package_status": "validated",
                "package_confidence": 1.0,
                "review_required": False,
            },
            {
                "question": "Check if the scoring fallback probe number is greater than 10",
                "model_answer": "def scoring_fallback_probe(n): return n > 10",
                "language": "python",
                "template_family": "python::greater_than_threshold",
                "package_status": "validated",
                "package_confidence": 1.0,
                "review_required": False,
            },
            {
                "question": "Tell whether the value passes the cutoff",
                "model_answer": "def passes_cutoff(n): return n > 10",
                "language": "python",
                "template_family": "python::greater_than_threshold",
                "package_status": "validated",
                "package_confidence": 1.0,
                "review_required": False,
            },
        ],
    )

    assert "Tell whether the value passes the cutoff" in merged["reused_from_questions"]
    assert all("probe" not in item.lower() for item in merged["reused_from_questions"])


def test_exact_signature_does_not_reuse_wrong_specific_family_package():
    merged = merge_with_existing_profiles(
        {
            "question_id": "q_same_signature_new_family",
            "question": "Check if list has at least one element",
            "model_answer": "def has_items(lst): return len(lst) > 0",
            "language": "python",
        },
        [
            {
                "question": "Check if list has at least one element",
                "model_answer": "def has_items(lst): return len(lst)",
                "language": "python",
                "template_family": "python::list_length",
                "package_status": "validated",
                "package_confidence": 1.0,
                "review_required": False,
                "test_sets": {
                    "positive": [
                        {"input": "[[1,2,3]]", "expected_output": "3", "description": "wrong stale length test"}
                    ],
                    "negative": [],
                },
                "incorrect_patterns": [
                    {
                        "pattern": "return len(lst)",
                        "match_type": "contains",
                        "feedback": "Returns length instead of boolean.",
                        "suggestion": "Return a boolean.",
                        "score_cap": 20,
                    }
                ],
            }
        ],
    )

    assert merged["template_family"] == "python::non_empty_collection_check"
    assert merged["test_sets"]["positive"] == []
    assert merged["test_sets"]["negative"] == []
    assert merged["incorrect_patterns"] == []


def test_parameterized_family_reuse_does_not_cross_divisors():
    merged = merge_with_existing_profiles(
        {
            "question_id": "q_div4_clean_reuse",
            "question": "Check if number is divisible by 4",
            "model_answer": "def div4(n): return n % 4 == 0",
            "language": "python",
        },
        [
            {
                "question": "Check if number is divisible by 3",
                "model_answer": "def div3(n): return n % 3 == 0",
                "language": "python",
                "template_family": "python::divisible_by_constant",
                "package_status": "validated",
                "package_confidence": 1.0,
                "review_required": False,
                "test_sets": {
                    "positive": [
                        {"input": "[3]", "expected_output": "true", "description": "divisible by 3 only"}
                    ],
                    "negative": [
                        {"input": "[4]", "expected_output": "false", "description": "not divisible by 3"}
                    ],
                },
            }
        ],
    )

    assert merged["template_family"] == "python::divisible_by_constant"
    assert merged["test_sets"]["positive"] == []
    assert merged["test_sets"]["negative"] == []


def test_parameterized_family_reuse_does_not_cross_length_constants():
    merged = merge_with_existing_profiles(
        {
            "question_id": "q_len5_clean_reuse",
            "question": "Check if list length equals 5",
            "model_answer": "def len5(lst): return len(lst) == 5",
            "language": "python",
        },
        [
            {
                "question": "Check if list length equals 3",
                "model_answer": "def len3(lst): return len(lst) == 3",
                "language": "python",
                "template_family": "python::list_length_equals_constant",
                "package_status": "validated",
                "package_confidence": 1.0,
                "review_required": False,
                "test_sets": {
                    "positive": [
                        {"input": "[[0,1,2]]", "expected_output": "true", "description": "length three only"}
                    ],
                    "negative": [
                        {"input": "[[0,1,2,3]]", "expected_output": "false", "description": "not length three"}
                    ],
                },
            }
        ],
    )

    assert merged["template_family"] == "python::list_length_equals_constant"
    assert merged["test_sets"]["positive"] == []
    assert merged["test_sets"]["negative"] == []


def test_question_package_response_hides_stored_internal_probe_questions():
    response = app_module._question_package_response(
        {
            "question_id": "q_clean_response",
            "question": "Check if number is greater than 10",
            "model_answer": "def greater_10(n): return n > 10",
            "language": "python",
            "profile": {
                "language": "python",
                "category": "general",
                "task_type": "unknown",
                "risk": "medium",
                "markers": [],
            },
            "question_signature": "python::check if number is greater than 10",
            "reused_from_questions": [
                "Check if the guardrail probe number is greater than 10",
                "Tell whether the value passes the cutoff",
                "Check if the scoring fallback probe number is greater than 10",
            ],
            "validation_options": {
                "reused_from_questions": [
                    "Check if the guardrail probe number is greater than 10",
                    "Tell whether the value passes the cutoff",
                ]
            },
        }
    )

    assert response.reused_from_questions == ["Tell whether the value passes the cutoff"]
    assert response.validation_options["reused_from_questions"] == ["Tell whether the value passes the cutoff"]


def test_register_does_not_silently_accept_package_without_required_llm_assistance(monkeypatch):
    monkeypatch.setattr("evaluator.question_rule_generator.call_llm", lambda _prompt: "not valid json")

    packages = prepare_question_profiles_until_correct(
        [
            {
                "question_id": "q_no_llm_guardrail_probe",
                "question": "Check if the guardrail probe number is greater than 10",
                "model_answer": "def guardrail_probe(n): return n > 10",
                "language": "python",
            },
        ],
        force_llm=True,
    )

    package = packages[0]
    assert package["llm_assisted"] is False
    assert package["package_status"] == "generated"
    assert package["review_required"] is True
    assert package["package_confidence"] < 0.9
    assert "GGUF assistance is required" in package["package_summary"]


def test_bad_package_detail_flags_missing_llm_assistance_for_registration():
    detail = _build_bad_package_detail(
        {
            "question_id": "q-no-llm",
            "question": "Check if number is greater than 10",
            "package_status": "validated",
            "package_confidence": 1.0,
            "package_summary": "Validated package without llm flag.",
            "review_required": False,
            "template_family": "python::greater_than_threshold",
            "llm_assisted": False,
        }
    )

    assert "llm_assistance_missing" in detail["flags"]
    assert "GGUF-assisted" in (detail["reason"] or "")


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
    assert result["question_metadata"]["template_family"] in {"python::model_answer_derived", "python::divisible_by_constant"}
    assert result["question_metadata"]["package_status"] in {"validated", "live"}
    assert result["data"].score == 100


def test_evaluation_uses_inline_temporary_package_when_bootstrap_cannot_register(monkeypatch):
    monkeypatch.setattr(app_module, "_try_bootstrap_package_from_inline_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "get_question_profile_fresh", lambda *args, **kwargs: None)

    submission = QuestionSubmission(
        question_id="q_inline_temp_eval",
        question="Apply the faculty rule to the incoming value",
        model_answer="def transform(n): return n + 5",
        student_answer="def transform(n): return n + 5",
        language="python",
    )

    result = _evaluate_single_submission("student-inline-temp", submission, False, False, 1)

    assert "error" not in result
    assert result["question_metadata"]["template_family"] == "python::model_answer_derived"
    assert result["question_metadata"]["package_status"] == "validated"
    assert result["question_metadata"]["inline_temporary_package"] is True
    assert result["data"].score == 100


def test_evaluation_uses_emergency_python_package_when_temporary_generation_fails(monkeypatch):
    monkeypatch.setattr(app_module, "_try_bootstrap_package_from_inline_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "get_question_profile_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "generate_question_package", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    submission = QuestionSubmission(
        question_id="q_inline_emergency_eval",
        question="Compute the custom score for a value",
        model_answer="def score(x): return x * 3 + 1",
        student_answer="def score(x): return x * 3 + 1",
        language="python",
    )

    result = _evaluate_single_submission("student-inline-emergency", submission, False, False, 1)

    assert "error" not in result
    assert result["question_metadata"]["template_family"] == "python::model_answer_derived"
    assert result["question_metadata"]["package_status"] == "validated"
    assert result["question_metadata"]["inline_temporary_package"] is True
    assert result["data"].score == 100


def test_evaluation_handles_new_python_topic_without_registered_package():
    submission = QuestionSubmission(
        question_id="q_new_python_topic_eval",
        question="Calculate mean squared error between two lists",
        model_answer="def mse(y_true, y_pred): return sum((a-b)**2 for a, b in zip(y_true, y_pred)) / len(y_true)",
        student_answer="def mse(y_true, y_pred): return sum((a-b)**2 for a, b in zip(y_true, y_pred)) / len(y_true)",
        language="python",
    )

    result = _evaluate_single_submission("student-new-topic", submission, False, False, 1)

    assert "error" not in result
    assert result["question_metadata"]["package_status"] in {"validated", "live"}
    assert isinstance(result["question_metadata"]["template_family"], str)
    assert result["question_metadata"]["template_family"].startswith("python::")
    assert result["data"].score == 100

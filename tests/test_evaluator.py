import sys
import os

# =========================
# 🔥 FIX: ADD PROJECT ROOT TO PATH
# =========================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evaluator.main_evaluator import evaluate_submission
from evaluator.execution.shared import evaluate_python_hidden_tests


# =========================
# TEST CASE 1: VALID PYTHON CODE
# =========================
def test_valid_python():
    print("\n=== TEST 1: VALID PYTHON CODE ===\n")

    result = evaluate_submission(
        student_id="101",
        question="Write a function to find factorial",
        sample_answer="def fact(n): return 1 if n==0 else n*fact(n-1)",
        student_answer="""
def factorial(n):
    result = 1
    for i in range(1, n+1):
        result *= i
    return result
""",
        language="python"
    )

    print(result)

    assert result["status"] == "success"
    assert "score" in result
    assert result["score"] >= 0

    print("✅ Test 1 Passed")


# =========================
# TEST CASE 2: SYNTAX ERROR
# =========================
def test_syntax_error():
    print("\n=== TEST 2: SYNTAX ERROR ===\n")

    result = evaluate_submission(
        student_id="102",
        question="Write a function to add two numbers",
        sample_answer="def add(a,b): return a+b",
        student_answer="""
def add(a,b)
    return a+b
""",
        language="python"
    )

    print(result)

    assert result["status"] in ["success", "error"]

    print("✅ Test 2 Passed")


# =========================
# TEST CASE 3: HTML INPUT
# =========================
def test_html():
    print("\n=== TEST 3: HTML INPUT ===\n")

    result = evaluate_submission(
        student_id="103",
        question="Create a simple HTML page",
        sample_answer="<html><body><h1>Hello</h1></body></html>",
        student_answer="<div><h1>Hello</h1></div>",
        language="html"
    )

    print(result)

    assert result["status"] == "success"

    print("✅ Test 3 Passed")


# =========================
# TEST CASE 4: JAVASCRIPT INPUT
# =========================
def test_javascript():
    print("\n=== TEST 4: JAVASCRIPT INPUT ===\n")

    result = evaluate_submission(
        student_id="104",
        question="Write a JavaScript function to add two numbers",
        sample_answer="function add(a,b){ return a+b; }",
        student_answer="function add(a,b){ return a+b; }",
        language="javascript"
    )

    print(result)

    assert result["status"] == "success"

    print("✅ Test 4 Passed")


# =========================
# TEST CASE 5: EMPTY INPUT
# =========================
def test_empty_input():
    print("\n=== TEST 5: EMPTY INPUT ===\n")

    result = evaluate_submission(
        student_id="105",
        question="Write any code",
        sample_answer="print('hello')",
        student_answer="",
        language="python"
    )

    print(result)

    assert result["status"] in ["error", "success"]

    print("✅ Test 5 Passed")


# =========================
# TEST CASE 6: EXACT MATCH FEEDBACK SHOULD NOT CLAIM DIFFERENT APPROACH
# =========================
def test_exact_match_feedback_is_precise():
    print("\n=== TEST 6: EXACT MATCH FEEDBACK PRECISION ===\n")

    result = evaluate_submission(
        student_id="106",
        question="Check if number is multiple of 3",
        sample_answer="def mult3(n): return n % 3 == 0",
        student_answer="def mult3(n): return n % 3 == 0",
        language="python"
    )

    print(result)

    assert result["status"] == "success"
    assert result["score"] >= 90
    assert "different approach" not in result.get("feedback", "").lower()

    print("✅ Test 6 Passed")


# =========================
# TEST CASE 7: EQUIVALENT STRING SOLUTION SHOULD NOT GET IRRELEVANT FEEDBACK
# =========================
def test_equivalent_string_solution_feedback_and_score():
    print("\n=== TEST 7: EQUIVALENT STRING SOLUTION ===\n")

    result = evaluate_submission(
        student_id="107",
        question="Return first and last character of string",
        sample_answer="def ends(s): return s[0] + s[-1]",
        student_answer="def ends(s): return s[:1] + s[-1:]",
        language="python"
    )

    print(result)

    feedback = result.get("feedback", "").lower()
    suggestions = result.get("suggestions", "").lower()

    assert result["status"] == "success"
    assert result["score"] >= 90
    assert "f-string" not in feedback
    assert "f string" not in feedback
    assert "f-string" not in suggestions
    assert "f string" not in suggestions

    print("✅ Test 7 Passed")


# =========================
# TEST CASE 8: ZERO MUST BE TREATED AS MULTIPLE OF 3 EDGE CASE
# =========================
def test_multiple_of_three_zero_edge_case():
    print("\n=== TEST 8: MULTIPLE OF 3 ZERO EDGE CASE ===\n")

    result = evaluate_submission(
        student_id="108",
        question="Check if number is multiple of 3",
        sample_answer="def mult3(n): return n % 3 == 0",
        student_answer="def mult3(n): return n % 3 == 0 if n else False",
        language="python"
    )

    print(result)

    assert result["status"] == "success"
    assert result["score"] <= 70
    assert "0" in result.get("feedback", "") or "zero" in result.get("feedback", "").lower()

    print("✅ Test 8 Passed")


def test_zero_pass_hidden_tests_caps_score_at_zero():
    finding = evaluate_python_hidden_tests(
        student_answer="def f(n): return False",
        hidden_tests=[{"input": "[1]", "expected_output": "true", "required": True, "weight": 1.0}],
    )

    assert finding is not None
    assert finding.get("result_type") == "zero_pass"
    assert finding.get("correctness_max") == 0


# =========================
# RUN ALL TESTS
# =========================
def run_all_tests():
    print("\n🚀 Running All Tests...\n")

    try:
        test_valid_python()
        test_syntax_error()
        test_html()
        test_javascript()
        test_empty_input()
        test_exact_match_feedback_is_precise()
        test_equivalent_string_solution_feedback_and_score()
        test_multiple_of_three_zero_edge_case()

        print("\n🎉 All Tests Completed Successfully!\n")

    except AssertionError as e:
        print("\n❌ Test Failed:", str(e))


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    run_all_tests()

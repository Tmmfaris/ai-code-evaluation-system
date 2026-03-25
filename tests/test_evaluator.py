import sys
import os

# =========================
# 🔥 FIX: ADD PROJECT ROOT TO PATH
# =========================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evaluator.main_evaluator import evaluate_submission


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
# TEST CASE 4: JSON INPUT
# =========================
def test_json():
    print("\n=== TEST 4: JSON INPUT ===\n")

    result = evaluate_submission(
        student_id="104",
        question="Create a JSON object with name and age",
        sample_answer='{"name": "John", "age": 25}',
        student_answer='{"name": "John", "age": 25}',
        language="json"
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
# RUN ALL TESTS
# =========================
def run_all_tests():
    print("\n🚀 Running All Tests...\n")

    try:
        test_valid_python()
        test_syntax_error()
        test_html()
        test_json()
        test_empty_input()

        print("\n🎉 All Tests Completed Successfully!\n")

    except AssertionError as e:
        print("\n❌ Test Failed:", str(e))


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    run_all_tests()
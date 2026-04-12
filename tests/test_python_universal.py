import pytest
import os
import sys

# Ensure evaluating modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evaluator.execution.shared import (
    analyze_python_execution,
    _universal_python_oracle_evaluate,
    _smart_outputs_equal,
    _infer_param_types,
    _generate_oracle_test_cases
)

def test_smart_outputs_equal():
    # Direct equality
    assert _smart_outputs_equal(1, 1)
    assert _smart_outputs_equal("hello", "hello")
    assert not _smart_outputs_equal(1, 2)
    
    # Float tolerance
    assert _smart_outputs_equal(1.0000000001, 1.0)
    assert not _smart_outputs_equal(1.001, 1.0)
    
    # Unordered list equivalence for certain questions
    assert _smart_outputs_equal([1, 2, 3], [3, 2, 1], question_text="find common elements")
    assert not _smart_outputs_equal([1, 2, 3], [3, 2, 1], question_text="sort the list")
    
    # String normalization
    assert _smart_outputs_equal("  hello  ", "hello")

def test_universal_oracle_gcd():
    question = "Write a function to compute GCD of two numbers"
    model = "import math\ndef gcd(a, b):\n    return math.gcd(a, b)"
    
    # Fully correct iterative version
    student_correct = "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return abs(a)"
    res = _universal_python_oracle_evaluate(question, model, student_correct)
    assert res is not None
    assert res["result_type"] == "full_pass"
    
    # Incorrect version
    student_incorrect = "def gcd(a, b):\n    return a + b"
    res2 = _universal_python_oracle_evaluate(question, model, student_incorrect)
    assert res2["result_type"] in {"zero_pass", "partial_pass"}

def test_integration_through_analyze_execution():
    question = "Write a function to return the square of a number"
    model_answer = "def square(n):\n    return n * n"
    
    student_answer = "def square(n):\n    return n ** 2"
    res = analyze_python_execution(question, model_answer, student_answer)
    assert res["result_type"] == "full_pass"
    
    student_incorrect = "def square(n):\n    return n + 2"
    res2 = analyze_python_execution(question, model_answer, student_incorrect)
    assert res2["result_type"] in {"zero_pass", "partial_pass"}

def test_oop_family():
    question = "Create a User class with a username property"
    model_answer = "class User:\n    def __init__(self, username):\n        self._username = username\n    @property\n    def username(self):\n        return self._username"
    # the oracle doesn't process classes, so analyze_python_execution delegates to family
    
    student_correct = model_answer
    res = analyze_python_execution(question, model_answer, student_correct)
    assert res["result_type"] == "full_pass"
    
    student_no_prop = "class User:\n    def __init__(self, username):\n        self._username = username\n    def username(self):\n        return self._username"
    res2 = analyze_python_execution(question, model_answer, student_no_prop)
    assert res2["result_type"] == "zero_pass"

def test_generator_family():
    question = "Write a generator function that yields squares"
    model_answer = "def gen_squares(n):\n    for i in range(n):\n        yield i*i"
    
    student_correct = model_answer
    res = analyze_python_execution(question, model_answer, student_correct)
    assert res["result_type"] == "full_pass"
    
    student_list = "def gen_squares(n):\n    return [i*i for i in range(n)]"
    res2 = analyze_python_execution(question, model_answer, student_list)
    assert res2["result_type"] == "zero_pass"

if __name__ == "__main__":
    pytest.main([__file__])

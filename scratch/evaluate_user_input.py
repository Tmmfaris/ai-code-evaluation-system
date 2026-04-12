import json
import sys
import os

# Add current directory to path so we can import app and evaluator
sys.path.append(os.getcwd())

from app import _evaluate_single_submission
from evaluator.bulk_processor import process_bulk_evaluations
from schemas import MultiStudentEvaluationRequest

user_input = {
  "students": [
    {
      "student_id": "101",
      "submissions": [
        {
          "question_id": "q1",
          "question": "Write a function to add two numbers",
          "model_answer": "def add(a, b): return a + b",
          "student_answer": "def add(a, b): return a + b",
          "language": "python"
        },
        {
          "question_id": "q2",
          "question": "Write a function to check if a number is even",
          "model_answer": "def is_even(n): return n % 2 == 0",
          "student_answer": "def is_even(n): return n % 2 == 0",
          "language": "python"
        },
        {
          "question_id": "q3",
          "question": "Write a function to reverse a string",
          "model_answer": "def reverse(s): return s[::-1]",
          "student_answer": "def reverse(s): return ''.join(reversed(s))",
          "language": "python"
        }
      ]
    },
    {
      "student_id": "102",
      "submissions": [
        {
          "question_id": "q1",
          "question": "Write a function to add two numbers",
          "model_answer": "def add(a, b): return a + b",
          "student_answer": "def add(a, b): return a - b",
          "language": "python"
        },
        {
          "question_id": "q2",
          "question": "Write a function to find factorial using recursion",
          "model_answer": "def fact(n): return 1 if n == 0 else n * fact(n - 1)",
          "student_answer": "def fact(n): return n * n",
          "language": "python"
        },
        {
          "question_id": "q3",
          "question": "Write a function to remove spaces from a string",
          "model_answer": "def remove_spaces(s): return s.replace(' ', '')",
          "student_answer": "def remove_spaces(s): return ''.join(s.split())",
          "language": "python"
        }
      ]
    },
    {
      "student_id": "103",
      "submissions": [
        {
          "question_id": "q1",
          "question": "Write a function to check if a string is a palindrome",
          "model_answer": "def is_palindrome(s): return s == s[::-1]",
          "student_answer": "def is_palindrome(s): return True",
          "language": "python"
        },
        {
          "question_id": "q2",
          "question": "Write a function to find the minimum element in a list",
          "model_answer": "def min_list(lst): return min(lst)",
          "student_answer": "def min_list(lst): return sorted(lst)[0]",
          "language": "python"
        },
        {
          "question_id": "q3",
          "question": "Write a function to convert string to lowercase",
          "model_answer": "def to_lower(s): return s.lower()",
          "student_answer": "def to_lower(s): return s.lower()",
          "language": "python"
        }
      ]
    }
  ]
}

def run_manual_eval():
    req = MultiStudentEvaluationRequest(**user_input)
    results_raw = process_bulk_evaluations(req, _evaluate_single_submission)
    
    # process_bulk_evaluations returns a dict, but some nested objects might be Pydantic models
    # We'll use a helper to ensure everything is serializable
    def json_serializable(obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if isinstance(obj, dict):
            return {k: json_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [json_serializable(i) for i in obj]
        return obj

    print(json.dumps(json_serializable(results_raw), indent=2))

if __name__ == "__main__":
    run_manual_eval()

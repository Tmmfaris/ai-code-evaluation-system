import json
import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluator.question_package.workflow import prepare_question_profiles


payload = [
    {
        "question_id": "q1",
        "question": "Check if string is palindrome",
        "model_answer": "def pal(s): return s == s[::-1]",
        "language": "python",
    },
    {
        "question_id": "q2",
        "question": "Find maximum in list",
        "model_answer": "def max_val(lst): return max(lst)",
        "language": "python",
    },
    {
        "question_id": "q3",
        "question": "Count vowels in string",
        "model_answer": "def count_vowels(s): return sum(1 for c in s if c in \"aeiouAEIOU\")",
        "language": "python",
    },
]

result = prepare_question_profiles(payload, force_llm=False)

with open("tests/generated_question_packages_pal_max_vowels.json", "w", encoding="utf-8") as handle:
    json.dump(result, handle, indent=2, ensure_ascii=True)

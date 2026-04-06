import json
import re

from config import (
    AUTO_ACTIVATE_VALIDATED_QUESTIONS,
    AUTO_GENERATE_MAX_ALTERNATIVES,
    AUTO_GENERATE_MAX_HIDDEN_TESTS,
    AUTO_GENERATE_QUESTION_RULES,
    MIN_PACKAGE_CONFIDENCE_FOR_EXAM,
    REQUIRE_FACULTY_APPROVAL_FOR_LIVE,
)
from analysis.syntax_checker.css_checker import check_css_syntax
from analysis.syntax_checker.html_checker import check_html_syntax
from analysis.syntax_checker.javascript_checker import check_javascript_syntax
from analysis.syntax_checker.mongodb_checker import check_mongodb_syntax
from analysis.syntax_checker.mysql_checker import check_mysql_syntax
from analysis.syntax_checker.react_checker import check_react_syntax
from evaluator.execution.shared import (
    _extract_first_function_name,
    _run_code_with_timeout,
    evaluate_java_hidden_tests,
    evaluate_javascript_hidden_tests,
)
from evaluator.question_learning_store import list_recent_learning_signals
from llm.llm_engine import call_llm


def _extract_first_json_object(text):
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _normalize_question_signature(question, language):
    normalized_question = re.sub(r"\s+", " ", (question or "").strip().lower())
    normalized_question = re.sub(r"[^a-z0-9 ]", "", normalized_question)
    return f"{(language or '').strip().lower()}::{normalized_question}"


def _infer_template_family(question, language):
    question_text = (question or "").lower()
    language = (language or "").strip().lower()
    if "factorial" in question_text:
        return f"{language}::factorial"
    if "recursive" in question_text or "recursion" in question_text:
        return f"{language}::recursion"
    if _contains_all(question_text, "add", "two", "numbers"):
        return f"{language}::add_two_numbers"
    if _contains_all(question_text, "reverse", "string"):
        return f"{language}::reverse_string"
    if "palindrome" in question_text:
        return f"{language}::palindrome"
    if language == "mysql" and "join" in question_text:
        return "mysql::sql_join"
    if language == "mongodb" and ("aggregate" in question_text or "$group" in question_text):
        return "mongodb::aggregation"
    if language == "react" and ("hook" in question_text or "usestate" in question_text or "useeffect" in question_text):
        return "react::hooks"
    if language == "css" and ("layout" in question_text or "flex" in question_text or "grid" in question_text):
        return "css::layout"
    if "even" in question_text:
        return f"{language}::even_check"
    if ("maximum" in question_text or "max" in question_text) and "array" in question_text:
        return f"{language}::maximum_array"
    if ("minimum" in question_text or "min" in question_text) and "array" in question_text:
        return f"{language}::minimum_array"
    if (_contains_all(question_text, "sum", "array")) or (_contains_all(question_text, "sum", "list")):
        return f"{language}::sum_collection"
    if "array" in question_text:
        return f"{language}::array_ops"
    if "string" in question_text:
        return f"{language}::string_ops"
    if language in {"html", "css", "react", "mysql", "mongodb"}:
        return f"{language}::static_template"
    return f"{language}::generic"


def _normalize_test_case(item):
    if not isinstance(item, dict):
        return None
    return {
        "input": item.get("input"),
        "expected_output": item.get("expected_output"),
        "description": item.get("description"),
        "kind": (item.get("kind") or "normal").strip().lower() if isinstance(item.get("kind"), str) else "normal",
        "weight": float(item.get("weight", 1.0) or 1.0),
        "required": bool(item.get("required", False)),
    }


def _normalize_incorrect_pattern(item):
    if not isinstance(item, dict):
        return None
    pattern = (item.get("pattern") or "").strip()
    if not pattern:
        return None
    return {
        "pattern": pattern,
        "match_type": (item.get("match_type") or "contains").strip().lower(),
        "feedback": (item.get("feedback") or "").strip(),
        "suggestion": (item.get("suggestion") or "").strip(),
        "score_cap": int(item.get("score_cap", 20) or 20),
    }


def _build_generation_prompt(question, model_answer, language):
    return f"""
You are generating a reusable evaluation package for a coding question.

Return ONLY valid JSON in this exact shape:
{{
  "accepted_solutions": ["..."],
  "test_sets": {{
    "positive": [
      {{"input": "...", "expected_output": "...", "description": "..."}}
    ],
    "negative": [
      {{"input": "...", "expected_output": "...", "description": "..."}}
    ]
  }},
  "incorrect_patterns": [
    {{
      "pattern": "...",
      "match_type": "contains",
      "feedback": "...",
      "suggestion": "...",
      "score_cap": 20
    }}
  ]
}}

Rules:
- Keep the same language as the model answer.
- accepted_solutions must be logically equivalent correct code solutions.
- Do not repeat the original model answer.
- Generate at most {AUTO_GENERATE_MAX_ALTERNATIVES} accepted_solutions.
- Generate at most {AUTO_GENERATE_MAX_HIDDEN_TESTS} positive tests and {AUTO_GENERATE_MAX_HIDDEN_TESTS} negative tests.
- test inputs and outputs must be compact and machine-usable.
- incorrect_patterns should capture common obviously wrong student variants.
- If uncertain, return empty arrays.

Question:
{question}

Language:
{language}

Model answer:
{model_answer}
""".strip()


def _dedupe_strings(items, limit=None):
    results = []
    for item in items or []:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned not in results:
                results.append(cleaned)
    return results[:limit] if limit else results


def _build_case(input_value, expected_output, description, kind="normal", weight=1.0, required=False):
    return {
        "input": json.dumps(input_value, separators=(",", ":")) if not isinstance(input_value, str) else input_value,
        "expected_output": json.dumps(expected_output, separators=(",", ":")) if not isinstance(expected_output, str) else expected_output,
        "description": description,
        "kind": kind,
        "weight": weight,
        "required": required,
    }


def _contains_all(text, *parts):
    lowered = (text or "").lower()
    return all(part in lowered for part in parts)


def _deterministic_code_baselines(question, language):
    question_text = (question or "").lower()

    if "factorial" in question_text:
        return {
            "accepted_solutions": [
                "def fact(n):\n    if n == 0:\n        return 1\n    return n * fact(n - 1)" if language == "python" else "",
                "function fact(n){ if(n===0) return 1; return n * fact(n-1); }" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([0], 1, "base case", kind="edge", weight=1.5, required=True),
                    _build_case([1], 1, "small positive", kind="normal", weight=1.0),
                    _build_case([5], 120, "representative positive", kind="normal", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case([3], 6, "non-trivial recursive or iterative case", kind="trap", weight=1.1),
                    _build_case([6], 720, "larger positive case", kind="edge", weight=1.2),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return 1;",
                    "match_type": "contains",
                    "feedback": "Returning 1 for every input does not compute factorial values.",
                    "suggestion": "Handle the base case and multiply by smaller values for n > 1.",
                    "score_cap": 20,
                }
            ],
        }

    if _contains_all(question_text, "add", "two", "numbers"):
        return {
            "accepted_solutions": ["return a + b;", "return (a+b);"],
            "test_sets": {
                "positive": [
                    _build_case([1, 2], 3, "small positive integers", kind="normal", weight=1.0, required=True),
                    _build_case([0, 5], 5, "zero plus positive", kind="edge", weight=1.1),
                ],
                "negative": [
                    _build_case([-2, 3], 1, "mixed sign values", kind="edge", weight=1.2, required=True),
                    _build_case([10, 15], 25, "larger integers", kind="normal", weight=1.0),
                    _build_case([100, -100], 0, "sum to zero", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return a;",
                    "match_type": "contains",
                    "feedback": "Returning only the first argument does not add the two inputs.",
                    "suggestion": "Return the sum of both input values.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return b;",
                    "match_type": "contains",
                    "feedback": "Returning only the second argument does not add the two inputs.",
                    "suggestion": "Return the sum of both input values.",
                    "score_cap": 20,
                },
            ],
        }

    if "square of a number" in question_text or "return square of a number" in question_text:
        return {
            "accepted_solutions": [
                "return n * n;" if language == "javascript" else "",
                "return Math.pow(n, 2);" if language == "javascript" else "",
                "return n ** 2;" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([2], 4, "positive square case", kind="normal", weight=1.0, required=True),
                    _build_case([-3], 9, "negative square case", kind="edge", weight=1.3, required=True),
                    _build_case([0], 0, "zero square case", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case([5], 25, "non-trivial square trap", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return n + n;",
                    "match_type": "contains",
                    "feedback": "Adding the number to itself does not compute its square.",
                    "suggestion": "Multiply the number by itself, for example with n * n.",
                    "score_cap": 20,
                }
            ],
        }

    if _contains_all(question_text, "reverse", "string"):
        return {
            "accepted_solutions": [
                "return s[::-1]" if language == "python" else "",
                "return ''.join(reversed(s))" if language == "python" else "",
                "return s.split('').reverse().join('')" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case(["abc"], "cba", "simple lowercase string", kind="normal", weight=1.0, required=True),
                    _build_case(["racecar"], "racecar", "palindrome string", kind="edge", weight=1.0),
                ],
                "negative": [
                    _build_case(["hello world"], "dlrow olleh", "string with space", kind="normal", weight=1.2, required=True),
                    _build_case([""], "", "empty string", kind="edge", weight=1.3),
                    _build_case(["a"], "a", "single character string", kind="trap", weight=0.9),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s;",
                    "match_type": "contains",
                    "feedback": "Returning the original string does not reverse it.",
                    "suggestion": "Reverse the character order before returning the result.",
                    "score_cap": 20,
                }
            ],
        }

    if "uppercase" in question_text and "string" in question_text:
        return {
            "accepted_solutions": [
                "return s.toUpperCase();" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case(["ab"], "AB", "lowercase to uppercase", kind="normal", weight=1.0, required=True),
                    _build_case([""], "", "empty string uppercase", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case(["Ab"], "AB", "mixed-case normalization trap", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return s;",
                    "match_type": "contains",
                    "feedback": "Returning the original string does not convert it to uppercase.",
                    "suggestion": "Call s.toUpperCase() before returning the result.",
                    "score_cap": 20,
                }
            ],
        }

    if "palindrome" in question_text:
        return {
            "accepted_solutions": [
                "return s == s[::-1]" if language == "python" else "",
                "return s === s.split('').reverse().join('')" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case(["madam"], True, "palindrome string", kind="normal", weight=1.0, required=True),
                    _build_case(["level"], True, "another palindrome", kind="normal", weight=1.0),
                ],
                "negative": [
                    _build_case(["hello"], False, "non-palindrome", kind="normal", weight=1.2, required=True),
                    _build_case(["ab"], False, "short non-palindrome", kind="trap", weight=1.0),
                    _build_case([""], True, "empty string edge case", kind="edge", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return true;",
                    "match_type": "contains",
                    "feedback": "Always returning true does not actually check whether the value is a palindrome.",
                    "suggestion": "Compare the value with its reverse or mirrored characters.",
                    "score_cap": 20,
                }
            ],
        }

    if "even" in question_text:
        return {
            "accepted_solutions": ["return n % 2 == 0;", "return (n & 1) == 0;"],
            "test_sets": {
                "positive": [
                    _build_case([2], True, "positive even", kind="normal", weight=1.0, required=True),
                    _build_case([0], True, "zero is even", kind="edge", weight=1.1),
                ],
                "negative": [
                    _build_case([3], False, "positive odd", kind="normal", weight=1.0, required=True),
                    _build_case([-5], False, "negative odd", kind="edge", weight=1.1),
                    _build_case([-2], True, "negative even", kind="trap", weight=1.2),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "% 2 == 1",
                    "match_type": "contains",
                    "feedback": "This checks odd numbers instead of even numbers.",
                    "suggestion": "Use a modulo check against 0 for evenness.",
                    "score_cap": 20,
                },
                {
                    "pattern": "return true;",
                    "match_type": "contains",
                    "feedback": "Always returning true does not check whether the number is even.",
                    "suggestion": "Return the result of an actual even-number check.",
                    "score_cap": 20,
                },
            ],
        }

    if ("maximum" in question_text or "max" in question_text) and "array" in question_text:
        return {
            "accepted_solutions": [
                "return max(arr)" if language == "python" else "",
                "return Math.max(...arr)" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([[1, 5, 3]], 5, "mixed positive values", kind="normal", weight=1.0, required=True),
                    _build_case([[-4, -2, -9]], -2, "all negative values", kind="edge", weight=1.4, required=True),
                ],
                "negative": [
                    _build_case([[7]], 7, "single element array", kind="edge", weight=1.0),
                    _build_case([[2, 2, 2]], 2, "duplicate maximum values", kind="trap", weight=1.0),
                    _build_case([[0, -1, -2]], 0, "includes zero", kind="normal", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return arr[0];",
                    "match_type": "contains",
                    "feedback": "Returning only the first element does not find the maximum in general.",
                    "suggestion": "Scan every element and keep track of the largest value.",
                    "score_cap": 20,
                }
            ],
        }

    if ("minimum" in question_text or "min" in question_text) and "array" in question_text:
        return {
            "accepted_solutions": [
                "return min(arr)" if language == "python" else "",
                "return Math.min(...arr)" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([[1, 5, 3]], 1, "mixed positive values", kind="normal", weight=1.0, required=True),
                    _build_case([[-4, -2, -9]], -9, "all negative values", kind="edge", weight=1.4, required=True),
                ],
                "negative": [
                    _build_case([[7]], 7, "single element array", kind="edge", weight=1.0),
                    _build_case([[2, 2, 2]], 2, "duplicate minimum values", kind="trap", weight=1.0),
                    _build_case([[0, -1, -2]], -2, "includes zero", kind="normal", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return arr[arr.length-1];",
                    "match_type": "normalized_contains",
                    "feedback": "Returning only the last element does not generally find the minimum value.",
                    "suggestion": "Scan every element and keep track of the smallest value.",
                    "score_cap": 20,
                }
            ],
        }

    if (_contains_all(question_text, "sum", "array")) or (_contains_all(question_text, "sum", "list")):
        return {
            "accepted_solutions": [
                "return sum(arr)" if language == "python" else "",
                "return arr.reduce((a,b)=>a+b,0)" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([[1, 2, 3]], 6, "small integer list", kind="normal", weight=1.0, required=True),
                    _build_case([[0, 5, 7]], 12, "includes zero", kind="edge", weight=1.1),
                ],
                "negative": [
                    _build_case([[-2, 3, -1]], 0, "mixed sign values", kind="edge", weight=1.2, required=True),
                    _build_case([[]], 0, "empty input collection", kind="edge", weight=1.3),
                    _build_case([[5]], 5, "single value collection", kind="trap", weight=0.9),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return arr[0];",
                    "match_type": "contains",
                    "feedback": "Returning only the first element does not compute the sum of the whole collection.",
                    "suggestion": "Accumulate all values before returning the result.",
                    "score_cap": 20,
                }
            ],
        }

    if "array is empty" in question_text:
        return {
            "accepted_solutions": [
                "return arr.length === 0;" if language == "javascript" else "",
                "return !arr.length;" if language == "javascript" else "",
            ],
            "test_sets": {
                "positive": [
                    _build_case([[]], True, "empty array case", kind="edge", weight=1.2, required=True),
                    _build_case([[1]], False, "non-empty array case", kind="normal", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case([[0]], False, "truthy array trap case", kind="trap", weight=1.1),
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": "return arr == [];",
                    "match_type": "contains",
                    "feedback": "Comparing an array directly with [] does not correctly check whether it is empty.",
                    "suggestion": "Check arr.length === 0 or use !arr.length instead.",
                    "score_cap": 20,
                }
            ],
        }

    if "array" in question_text:
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    _build_case([[1, 2, 3]], None, "representative array input", kind="normal", weight=1.0),
                    _build_case([[]], None, "empty array edge case", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case([[0, -1, 5]], None, "mixed-sign trap array", kind="trap", weight=1.2),
                    _build_case([[7]], None, "single-element edge case", kind="edge", weight=1.0),
                ],
            },
            "incorrect_patterns": [],
        }

    if "string" in question_text:
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    _build_case(["hello"], None, "representative string input", kind="normal", weight=1.0),
                    _build_case([""], None, "empty string edge case", kind="edge", weight=1.2, required=True),
                ],
                "negative": [
                    _build_case(["a"], None, "single-character trap case", kind="trap", weight=0.9),
                    _build_case(["hello world"], None, "string containing space", kind="edge", weight=1.1),
                ],
            },
            "incorrect_patterns": [],
        }

    if "recursive" in question_text or "recursion" in question_text:
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    _build_case([0], None, "base-case recursion input", kind="edge", weight=1.4, required=True),
                    _build_case([3], None, "small recursive step", kind="normal", weight=1.0),
                ],
                "negative": [
                    _build_case([5], None, "deeper recursion trap case", kind="trap", weight=1.2),
                ],
            },
            "incorrect_patterns": [],
        }

    return {
        "accepted_solutions": [],
        "test_sets": {
            "positive": [
                _build_case([], None, "faculty model answer baseline positive case"),
                _build_case([], None, "faculty model answer baseline edge-case positive"),
            ],
            "negative": [
                _build_case([], None, "faculty model answer baseline negative case"),
                _build_case([], None, "faculty model answer baseline edge case"),
            ],
        },
        "incorrect_patterns": [],
    }


def _deterministic_markup_baselines(question, language):
    question_text = (question or "").lower()
    if language == "html":
        expected_markers = []
        if "button" in question_text:
            expected_markers.append("<button")
        if "heading" in question_text or "h1" in question_text:
            expected_markers.append("<h1")
        if "form" in question_text:
            expected_markers.append("<form")
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    {"input": "static", "expected_output": "valid_html", "description": "well-formed html structure"},
                    {"input": "static", "expected_output": "semantic_layout", "description": "semantic layout structure"},
                ],
                "negative": [
                    {"input": "static", "expected_output": "required_markers", "description": "contains expected semantic tags"},
                    {"input": "static", "expected_output": "question_text_alignment", "description": "matches the requested html intent"},
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": marker,
                    "match_type": "contains",
                    "feedback": f"The submission is missing the expected HTML marker {marker}.",
                    "suggestion": "Use the semantic tag requested by the question.",
                    "score_cap": 40,
                }
                for marker in expected_markers
            ],
        }

    if language == "css":
        expected_bits = []
        if "red" in question_text:
            expected_bits.append("red")
        if "color" in question_text:
            expected_bits.append("color")
        if "center" in question_text:
            expected_bits.append("center")
        if "flex" in question_text:
            expected_bits.append("display:flex")
        if "grid" in question_text:
            expected_bits.append("display:grid")
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    {"input": "static", "expected_output": "valid_css", "description": "valid css rule block"},
                    {"input": "static", "expected_output": "balanced_css", "description": "balanced selector/declaration structure"},
                ],
                "negative": [
                    {"input": "static", "expected_output": "required_properties", "description": "contains requested properties"},
                    {"input": "static", "expected_output": "question_style_intent", "description": "matches the requested css intent"},
                ],
            },
            "incorrect_patterns": [
                {
                    "pattern": bit,
                    "match_type": "contains",
                    "feedback": f"The stylesheet appears to miss the requested CSS detail '{bit}'.",
                    "suggestion": "Include the required selector/property/value from the question.",
                    "score_cap": 45,
                }
                for bit in expected_bits
            ],
        }

    if language == "react":
        if "hook" in question_text or "usestate" in question_text or "useeffect" in question_text:
            return {
                "accepted_solutions": [],
                "test_sets": {
                    "positive": [
                        {"input": "static", "expected_output": "hook_usage", "description": "uses the requested React hook"},
                        {"input": "static", "expected_output": "component_render", "description": "component renders valid JSX"},
                    ],
                    "negative": [
                        {"input": "static", "expected_output": "state_update_path", "description": "state or effect path is present"},
                        {"input": "static", "expected_output": "question_alignment", "description": "matches the requested React behavior"},
                    ],
                },
                "incorrect_patterns": [],
            }
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    {"input": "static", "expected_output": "valid_react", "description": "valid component syntax"},
                    {"input": "static", "expected_output": "component_shape", "description": "component shape looks valid"},
                ],
                "negative": [
                    {"input": "static", "expected_output": "jsx_return", "description": "returns JSX or equivalent UI output"},
                    {"input": "static", "expected_output": "question_ui_intent", "description": "matches the requested react intent"},
                ],
            },
            "incorrect_patterns": [],
        }

    if language == "mysql":
        if "join" in question_text:
            return {
                "accepted_solutions": [],
                "test_sets": {
                    "positive": [
                        {"input": "seeded", "expected_output": "joined_rows", "description": "returns expected joined rows"},
                        {"input": "seeded", "expected_output": "column_projection", "description": "returns requested join columns"},
                    ],
                    "negative": [
                        {"input": "seeded", "expected_output": "join_condition", "description": "uses an appropriate join condition"},
                        {"input": "seeded", "expected_output": "row_count_alignment", "description": "does not duplicate or drop expected rows"},
                    ],
                },
                "incorrect_patterns": [],
            }
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    {"input": "static", "expected_output": "valid_sql", "description": "recognizable sql statement"},
                    {"input": "static", "expected_output": "balanced_sql", "description": "balanced query structure"},
                ],
                "negative": [
                    {"input": "static", "expected_output": "question_intent", "description": "contains key sql clauses from the question intent"},
                    {"input": "static", "expected_output": "operation_alignment", "description": "matches the requested SQL operation"},
                ],
            },
            "incorrect_patterns": [],
        }

    if language == "mongodb":
        if "aggregate" in question_text or "$group" in question_text:
            return {
                "accepted_solutions": [],
                "test_sets": {
                    "positive": [
                        {"input": "seeded", "expected_output": "aggregation_result", "description": "returns expected aggregation result"},
                        {"input": "seeded", "expected_output": "pipeline_shape", "description": "uses the requested pipeline shape"},
                    ],
                    "negative": [
                        {"input": "seeded", "expected_output": "group_stage", "description": "includes grouping or aggregation logic"},
                        {"input": "seeded", "expected_output": "field_alignment", "description": "matches requested MongoDB fields"},
                    ],
                },
                "incorrect_patterns": [],
            }
        return {
            "accepted_solutions": [],
            "test_sets": {
                "positive": [
                    {"input": "static", "expected_output": "valid_mongodb", "description": "recognizable mongodb command"},
                    {"input": "static", "expected_output": "balanced_mongodb", "description": "balanced query structure"},
                ],
                "negative": [
                    {"input": "static", "expected_output": "question_intent", "description": "contains key mongodb operations from the question intent"},
                    {"input": "static", "expected_output": "operation_alignment", "description": "matches the requested MongoDB operation"},
                ],
            },
            "incorrect_patterns": [],
        }

    return {"accepted_solutions": [], "test_sets": {"positive": [], "negative": []}, "incorrect_patterns": []}


def _build_deterministic_baseline_package(question, model_answer, language):
    language = (language or "").strip().lower()
    if language in {"python", "java", "javascript"}:
        return _deterministic_code_baselines(question, language)
    return _deterministic_markup_baselines(question, language)


def _merge_generated_package(base_payload, generated_payload):
    merged = dict(base_payload or {})
    merged.setdefault("accepted_solutions", [])
    merged.setdefault("incorrect_patterns", [])
    merged.setdefault("test_sets", {"positive": [], "negative": []})

    merged["accepted_solutions"] = _dedupe_strings(
        [*merged.get("accepted_solutions", []), *(generated_payload.get("accepted_solutions", []) or [])],
        limit=AUTO_GENERATE_MAX_ALTERNATIVES,
    )

    existing_patterns = list(merged.get("incorrect_patterns", []) or [])
    for item in generated_payload.get("incorrect_patterns", []) or []:
        normalized = _normalize_incorrect_pattern(item)
        if normalized and normalized not in existing_patterns:
            existing_patterns.append(normalized)
    merged["incorrect_patterns"] = existing_patterns

    existing_tests = merged.get("test_sets") or {"positive": [], "negative": []}
    combined_tests = {"positive": [], "negative": []}
    for bucket in ("positive", "negative"):
        seen = []
        for item in (existing_tests.get(bucket) or []) + (generated_payload.get("test_sets", {}).get(bucket) or []):
            normalized = _normalize_test_case(item)
            if normalized and normalized not in seen:
                seen.append(normalized)
        combined_tests[bucket] = seen[:AUTO_GENERATE_MAX_HIDDEN_TESTS]
    merged["test_sets"] = combined_tests
    return merged


def merge_with_existing_profiles(payload, existing_profiles):
    merged = dict(payload or {})
    signature = _normalize_question_signature(merged.get("question"), merged.get("language"))
    template_family = merged.get("template_family") or _infer_template_family(merged.get("question"), merged.get("language"))
    merged["question_signature"] = signature
    merged["template_family"] = template_family

    accepted = []
    incorrect_patterns = []
    test_sets = {"positive": [], "negative": []}
    reused_from_questions = []

    for profile in existing_profiles or []:
        profile_signature = _normalize_question_signature(profile.get("question"), profile.get("language"))
        profile_family = profile.get("template_family") or _infer_template_family(profile.get("question"), profile.get("language"))
        if profile_signature != signature and profile_family != template_family:
            continue
        profile_question = (profile.get("question") or "").strip()
        if profile_question and profile_question not in reused_from_questions:
            reused_from_questions.append(profile_question)
        for answer in profile.get("accepted_solutions", []) or profile.get("alternative_answers", []) or []:
            if isinstance(answer, str) and answer.strip() and answer not in accepted:
                accepted.append(answer.strip())
        for item in (profile.get("incorrect_patterns") or []):
            normalized = _normalize_incorrect_pattern(item)
            if normalized and normalized not in incorrect_patterns:
                incorrect_patterns.append(normalized)
        profile_test_sets = profile.get("test_sets") or {}
        legacy_hidden = profile.get("hidden_tests") or []
        for item in profile_test_sets.get("positive", []) + legacy_hidden:
            normalized = _normalize_test_case(item)
            if normalized and normalized not in test_sets["positive"]:
                test_sets["positive"].append(normalized)
        for item in profile_test_sets.get("negative", []):
            normalized = _normalize_test_case(item)
            if normalized and normalized not in test_sets["negative"]:
                test_sets["negative"].append(normalized)

    merged.setdefault("accepted_solutions", [])
    merged.setdefault("incorrect_patterns", [])
    merged.setdefault("test_sets", {"positive": [], "negative": []})

    for item in merged["accepted_solutions"]:
        if isinstance(item, str) and item.strip() and item.strip() not in accepted:
            accepted.append(item.strip())
    for item in merged["incorrect_patterns"]:
        normalized = _normalize_incorrect_pattern(item)
        if normalized and normalized not in incorrect_patterns:
            incorrect_patterns.append(normalized)
    for bucket in ("positive", "negative"):
        for item in merged["test_sets"].get(bucket, []):
            normalized = _normalize_test_case(item)
            if normalized and normalized not in test_sets[bucket]:
                test_sets[bucket].append(normalized)

    merged["accepted_solutions"] = accepted[:AUTO_GENERATE_MAX_ALTERNATIVES]
    merged["incorrect_patterns"] = incorrect_patterns
    merged["test_sets"] = {
        "positive": test_sets["positive"][:AUTO_GENERATE_MAX_HIDDEN_TESTS],
        "negative": test_sets["negative"][:AUTO_GENERATE_MAX_HIDDEN_TESTS],
    }
    merged["reused_from_questions"] = reused_from_questions
    return merged


def _promote_learning_patterns(payload):
    promoted = []
    promoted_answers = []
    promoted_tests = {"positive": [], "negative": []}
    signature = _normalize_question_signature(payload.get("question"), payload.get("language"))
    template_family = payload.get("template_family") or _infer_template_family(payload.get("question"), payload.get("language"))
    repeated_bad = {}
    repeated_good = {}
    low_score_hits = 0

    for item in list_recent_learning_signals(limit=500):
        if (item.get("language") or "").strip().lower() != (payload.get("language") or "").strip().lower():
            continue
        metadata = item.get("metadata") or {}
        if metadata.get("question_signature") != signature and metadata.get("template_family") != template_family:
            continue
        raw_answer = (item.get("student_answer_text") or "").strip()
        if item.get("status") != "error" and item.get("score", 0) >= 90 and raw_answer:
            entry = repeated_good.setdefault(raw_answer, {"count": 0})
            entry["count"] += 1
            continue
        if item.get("score", 0) > 20 and item.get("status") != "error":
            continue
        answer = (item.get("normalized_student_answer") or "").strip()
        if not answer:
            continue
        low_score_hits += 1
        entry = repeated_bad.setdefault(answer, {"count": 0, "feedback": item.get("feedback", "")})
        entry["count"] += 1

    for answer, data in repeated_good.items():
        if data["count"] < 2:
            continue
        promoted_answers.append(answer)

    for answer, data in repeated_bad.items():
        if data["count"] < 2:
            continue
        promoted.append({
            "pattern": answer,
            "match_type": "normalized_contains",
            "feedback": data["feedback"] or "A repeated incorrect answer pattern was detected from earlier evaluations.",
            "suggestion": "Use the registered hidden tests and accepted solutions to replace this repeated low-scoring pattern.",
            "score_cap": 20,
        })

    if low_score_hits >= 2:
        promoted_test_map = {
            "python::maximum_array": {"positive": [], "negative": [_build_case([[-4, -2, -9]], -2, "learning-added all-negative max trap", kind="trap", weight=1.4, required=True)]},
            "javascript::maximum_array": {"positive": [], "negative": [_build_case([[-4, -2, -9]], -2, "learning-added all-negative max trap", kind="trap", weight=1.4, required=True)]},
            "python::minimum_array": {"positive": [], "negative": [_build_case([[4, 2, 9]], 2, "learning-added positive-only min trap", kind="trap", weight=1.3, required=True)]},
            "javascript::minimum_array": {"positive": [], "negative": [_build_case([[4, 2, 9]], 2, "learning-added positive-only min trap", kind="trap", weight=1.3, required=True)]},
            "python::reverse_string": {"positive": [], "negative": [_build_case([""], "", "learning-added empty-string reverse trap", kind="edge", weight=1.2, required=True)]},
            "javascript::reverse_string": {"positive": [], "negative": [_build_case([""], "", "learning-added empty-string reverse trap", kind="edge", weight=1.2, required=True)]},
            "python::sum_collection": {"positive": [], "negative": [_build_case([[]], 0, "learning-added empty-collection sum trap", kind="edge", weight=1.3, required=True)]},
            "javascript::sum_collection": {"positive": [], "negative": [_build_case([[]], 0, "learning-added empty-collection sum trap", kind="edge", weight=1.3, required=True)]},
            "mysql::sql_join": {"positive": [{"input": "seeded", "expected_output": "joined_rows_required", "description": "learning-added required join case", "kind": "trap", "weight": 1.3, "required": True}], "negative": []},
            "mongodb::aggregation": {"positive": [{"input": "seeded", "expected_output": "aggregation_required", "description": "learning-added required aggregation case", "kind": "trap", "weight": 1.3, "required": True}], "negative": []},
        }
        promoted_tests = promoted_test_map.get(template_family, {"positive": [], "negative": []})

    if promoted or promoted_answers or promoted_tests["positive"] or promoted_tests["negative"]:
        payload = _merge_generated_package(
            payload,
            {
                "accepted_solutions": promoted_answers,
                "test_sets": promoted_tests,
                "incorrect_patterns": promoted,
            },
        )
    return payload


def enrich_question_profile(payload):
    enriched = dict(payload or {})
    enriched["question_signature"] = enriched.get("question_signature") or _normalize_question_signature(
        enriched.get("question"),
        enriched.get("language"),
    )
    enriched["template_family"] = enriched.get("template_family") or _infer_template_family(
        enriched.get("question"),
        enriched.get("language"),
    )
    enriched.setdefault("accepted_solutions", [])
    enriched.setdefault("incorrect_patterns", [])
    enriched.setdefault("test_sets", {"positive": [], "negative": []})

    question = (enriched.get("question") or "").strip()
    model_answer = (enriched.get("model_answer") or "").strip()
    language = (enriched.get("language") or "").strip().lower()

    if not question or not model_answer or not language:
        return enriched

    baseline_package = _build_deterministic_baseline_package(question, model_answer, language)
    enriched = _merge_generated_package(enriched, baseline_package)
    enriched = _promote_learning_patterns(enriched)

    if not AUTO_GENERATE_QUESTION_RULES:
        return enriched

    raw = call_llm(_build_generation_prompt(question, model_answer, language))
    parsed = _extract_first_json_object(raw)
    if not isinstance(parsed, dict):
        return enriched

    accepted = []
    for item in parsed.get("accepted_solutions", []):
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned != model_answer and cleaned not in accepted:
                accepted.append(cleaned)

    test_sets = {"positive": [], "negative": []}
    for bucket in ("positive", "negative"):
        for item in (parsed.get("test_sets") or {}).get(bucket, []):
            normalized = _normalize_test_case(item)
            if normalized:
                test_sets[bucket].append(normalized)

    incorrect_patterns = []
    for item in parsed.get("incorrect_patterns", []):
        normalized = _normalize_incorrect_pattern(item)
        if normalized:
            incorrect_patterns.append(normalized)

    return _merge_generated_package(
        enriched,
        {
            "accepted_solutions": accepted[:AUTO_GENERATE_MAX_ALTERNATIVES],
            "test_sets": {
                "positive": test_sets["positive"][:AUTO_GENERATE_MAX_HIDDEN_TESTS],
                "negative": test_sets["negative"][:AUTO_GENERATE_MAX_HIDDEN_TESTS],
            },
            "incorrect_patterns": incorrect_patterns,
        },
    )


def _parse_hidden_test_input(raw_value):
    if raw_value is None:
        return tuple()
    if isinstance(raw_value, (list, tuple)):
        return tuple(raw_value)
    if isinstance(raw_value, (int, float, bool)):
        return (raw_value,)
    if not isinstance(raw_value, str):
        return (raw_value,)
    text = raw_value.strip()
    if not text:
        return tuple()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return (text,)
    if isinstance(parsed, list):
        return tuple(parsed)
    return (parsed,)


def _parse_expected_output(raw_value):
    if isinstance(raw_value, (list, dict, int, float, bool)) or raw_value is None:
        return raw_value
    if not isinstance(raw_value, str):
        return raw_value
    text = raw_value.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _finalize_from_validation_result(finalized, total, passed, summary_prefix):
    if total == 0:
        finalized["package_status"] = "draft"
        finalized["package_summary"] = "No generated tests available for validation."
        finalized["package_confidence"] = 0.2
        finalized["review_required"] = True
        finalized["exam_ready"] = False
        return finalized

    confidence = passed / total
    finalized["package_confidence"] = round(confidence, 3)
    if passed == total:
        finalized["package_status"] = "validated"
        finalized["package_summary"] = f"{summary_prefix} Validated {passed}/{total} generated tests."
        finalized["review_required"] = False
        finalized["exam_ready"] = (
            finalized.get("approval_status") == "approved"
            and confidence >= MIN_PACKAGE_CONFIDENCE_FOR_EXAM
            and not finalized["review_required"]
        )
        if (
            AUTO_ACTIVATE_VALIDATED_QUESTIONS
            and finalized["exam_ready"]
            and (not REQUIRE_FACULTY_APPROVAL_FOR_LIVE or finalized.get("approval_status") == "approved")
        ):
            finalized["package_status"] = "live"
        return finalized

    if passed >= max(1, total - 1):
        finalized["package_status"] = "validated"
        finalized["package_summary"] = f"{summary_prefix} Validated {passed}/{total} generated tests, but review is recommended."
        finalized["review_required"] = True
        finalized["exam_ready"] = False
        return finalized

    finalized["package_status"] = "generated"
    finalized["package_summary"] = f"{summary_prefix} Only {passed}/{total} generated tests validated against the model answer."
    finalized["review_required"] = True
    finalized["exam_ready"] = False
    return finalized


def _finalize_from_syntax_result(finalized, syntax_result, summary_prefix, confidence=0.7):
    if not syntax_result.get("valid"):
        finalized["package_status"] = "draft"
        finalized["package_summary"] = f"{summary_prefix} Syntax validation failed: {syntax_result.get('error', 'unknown error')}."
        finalized["package_confidence"] = 0.15
        finalized["review_required"] = True
        finalized["exam_ready"] = False
        return finalized

    finalized["package_status"] = "validated"
    finalized["package_summary"] = f"{summary_prefix} Static validation passed for the faculty model answer."
    finalized["package_confidence"] = confidence
    finalized["review_required"] = False if confidence >= 0.75 else True
    finalized["exam_ready"] = (
        finalized.get("approval_status") == "approved"
        and confidence >= MIN_PACKAGE_CONFIDENCE_FOR_EXAM
        and not finalized["review_required"]
    )
    if (
        AUTO_ACTIVATE_VALIDATED_QUESTIONS
        and finalized["exam_ready"]
        and (not REQUIRE_FACULTY_APPROVAL_FOR_LIVE or finalized.get("approval_status") == "approved")
    ):
        finalized["package_status"] = "live"
    return finalized


def finalize_question_profile(payload):
    finalized = dict(payload or {})
    finalized["template_family"] = finalized.get("template_family") or _infer_template_family(
        finalized.get("question"),
        finalized.get("language"),
    )
    finalized["approval_status"] = (finalized.get("approval_status") or "pending").strip().lower()
    finalized["approved_by"] = (finalized.get("approved_by") or "").strip() or None
    finalized["exam_ready"] = False
    accepted = [item for item in finalized.get("accepted_solutions", []) if isinstance(item, str) and item.strip()]
    if finalized.get("model_answer"):
        accepted = [finalized["model_answer"].strip(), *accepted]
    dedup_accepted = []
    for item in accepted:
        cleaned = item.strip()
        if cleaned and cleaned not in dedup_accepted:
            dedup_accepted.append(cleaned)
    finalized["accepted_solutions"] = dedup_accepted[: AUTO_GENERATE_MAX_ALTERNATIVES + 1]

    test_sets = finalized.get("test_sets") or {"positive": [], "negative": []}
    positive_tests = [_normalize_test_case(item) for item in test_sets.get("positive", []) if _normalize_test_case(item)]
    negative_tests = [_normalize_test_case(item) for item in test_sets.get("negative", []) if _normalize_test_case(item)]
    finalized["test_sets"] = {"positive": positive_tests, "negative": negative_tests}
    finalized["positive_test_count"] = len(positive_tests)
    finalized["negative_test_count"] = len(negative_tests)

    language = (finalized.get("language") or "").strip().lower()
    model_answer = (finalized.get("model_answer") or "").strip()
    all_tests = positive_tests + negative_tests

    finalized["package_status"] = "generated" if all_tests else "draft"
    finalized["package_confidence"] = 0.35 if all_tests else 0.1
    finalized["review_required"] = True
    finalized["package_summary"] = "Generated package content pending validation."

    if language in {"html", "css", "react", "mysql", "mongodb"}:
        if language == "html":
            return _finalize_from_syntax_result(
                finalized,
                check_html_syntax(model_answer),
                "HTML package ready for static review.",
                confidence=0.72,
            )
        if language == "css":
            return _finalize_from_syntax_result(
                finalized,
                check_css_syntax(model_answer),
                "CSS package ready for static review.",
                confidence=0.72,
            )
        if language == "react":
            return _finalize_from_syntax_result(
                finalized,
                check_react_syntax(model_answer),
                "React package ready for static review.",
                confidence=0.7,
            )
        if language == "mysql":
            return _finalize_from_syntax_result(
                finalized,
                check_mysql_syntax(model_answer),
                "MySQL package ready for static review.",
                confidence=0.74,
            )
        if language == "mongodb":
            return _finalize_from_syntax_result(
                finalized,
                check_mongodb_syntax(model_answer),
                "MongoDB package ready for static review.",
                confidence=0.74,
            )

    if not all_tests:
        finalized["package_summary"] = "No generated test sets available yet."
        return finalized

    if language == "python":
        function_name = _extract_first_function_name(model_answer)
        if not function_name:
            finalized["package_status"] = "draft"
            finalized["package_summary"] = "Could not validate the registered model answer because no Python function was found."
            finalized["package_confidence"] = 0.15
            finalized["exam_ready"] = False
            return finalized

        cases = [_parse_hidden_test_input(item.get("input")) for item in all_tests]
        expected_outputs = [_parse_expected_output(item.get("expected_output")) for item in all_tests]
        run_result = _run_code_with_timeout(model_answer, function_name, cases)
        if not run_result.get("ok"):
            finalized["package_status"] = "draft"
            finalized["package_summary"] = f"Model answer validation failed: {run_result.get('error', 'execution error')}."
            finalized["package_confidence"] = 0.15
            finalized["exam_ready"] = False
            return finalized

        outputs = run_result.get("outputs", [])
        passed = 0
        for expected, actual in zip(expected_outputs, outputs):
            if actual.get("ok") and actual.get("result") == expected:
                passed += 1
        return _finalize_from_validation_result(finalized, len(all_tests), passed, "Python package ready.")

    if language == "java":
        result = evaluate_java_hidden_tests(model_answer, all_tests)
        if result is None:
            finalized["package_summary"] = "Generated Java package content. Validation will activate automatically on systems with a JDK."
            finalized["package_confidence"] = 0.4
            finalized["review_required"] = True
            finalized["exam_ready"] = False
            return finalized
        passed = len(all_tests) if result.get("result_type") == "full_pass" else int(result.get("passed_cases", 0) or 0)
        return _finalize_from_validation_result(finalized, len(all_tests), passed, "Java package ready.")

    if language == "javascript":
        result = evaluate_javascript_hidden_tests(model_answer, all_tests)
        if result is None:
            syntax_result = check_javascript_syntax(model_answer)
            return _finalize_from_syntax_result(
                finalized,
                syntax_result,
                "JavaScript package ready for static review.",
                confidence=0.68,
            )
        passed = len(all_tests) if result.get("result_type") == "full_pass" else int(result.get("passed_cases", 0) or 0)
        return _finalize_from_validation_result(finalized, len(all_tests), passed, "JavaScript package ready.")

    finalized["package_summary"] = "Generated package content. Automated validation is currently strongest for Python and Java."
    finalized["package_confidence"] = 0.45 if accepted else 0.3
    finalized["review_required"] = True
    finalized["exam_ready"] = False
    return finalized

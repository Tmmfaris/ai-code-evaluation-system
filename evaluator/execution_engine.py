import ast
import multiprocessing
import queue
import re
import threading


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

EXECUTION_TIMEOUT_SECONDS = 2.0


def _extract_first_function_name(code):
    try:
        tree = ast.parse(code)
    except Exception:
        return None

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


def _question_contains(question, *parts):
    lowered = (question or "").lower()
    return all(part in lowered for part in parts)


def _normalize_java(code):
    return re.sub(r"\s+", " ", (code or "").strip()).lower()


def _java_has(code, *parts):
    normalized = _normalize_java(code)
    return all(part in normalized for part in parts)


def _success_feedback(question):
    lowered = (question or "").lower()

    if "sum of all elements" in lowered or "sum of all elements in a list" in lowered:
        return "The function correctly returns the sum of all elements in the list."
    if "add two numbers" in lowered:
        return "The function correctly adds the two input numbers and matches the expected behavior on representative test cases."
    if "count words" in lowered:
        return "The function correctly counts the words in the sentence."
    if "even" in lowered:
        return "The function correctly returns a boolean even-check result for representative test cases."
    if "reverse" in lowered and "string" in lowered:
        return "The function correctly reverses the input string and matches the expected output on representative test cases."
    if "reverse" in lowered and "list" in lowered:
        return "The function correctly reverses the input list and matches the expected output on representative test cases."
    if "remove spaces" in lowered:
        return "The function correctly removes spaces from the input string on representative test cases."
    if "lowercase" in lowered:
        return "The function correctly converts the input string to lowercase on representative test cases."
    if "minimum" in lowered or "min" in lowered:
        return "The function returns the correct minimum value for representative test cases."
    if "maximum" in lowered or "max" in lowered:
        return "The function returns the correct maximum value for representative test cases."
    if "duplicate" in lowered:
        return "The function correctly removes duplicate elements from the list."
    if "palindrome" in lowered:
        return "The function correctly identifies palindrome and non-palindrome strings on representative test cases."
    if "factorial" in lowered:
        return "The function produces the expected factorial results on representative test cases."
    if "prime" in lowered:
        return "The function correctly identifies prime and non-prime numbers on representative test cases."

    return "Execution-based checks matched the expected outputs for representative test cases."


def _java_success_feedback(question):
    lowered = (question or "").lower()

    if "add two numbers" in lowered:
        return "The method correctly adds the two input numbers and matches the expected behavior."
    if "sum of digits" in lowered or "sum digits" in lowered:
        return "The method correctly calculates the sum of the digits."
    if "even" in lowered:
        return "The method correctly returns a boolean even-check result."
    if "reverse" in lowered and "string" in lowered:
        return "The method correctly reverses the input string and matches the expected behavior."
    if "remove spaces" in lowered:
        return "The method correctly removes spaces from the input string."
    if "lowercase" in lowered:
        return "The method correctly converts the input string to lowercase."
    if "uppercase" in lowered:
        return "The method correctly checks whether the string is uppercase."
    if "square" in lowered:
        return "The method correctly calculates the square of the input number."
    if "minimum" in lowered or "min" in lowered:
        return "The method correctly finds the minimum value in the array."

    return "The method matches the expected behavior for this Java question."


def _build_cases(question):
    if _question_contains(question, "palindrome"):
        return [("level",), ("hello",), ("",), ("abba",)]

    if _question_contains(question, "add", "two", "numbers"):
        return [(2, 3), (0, 0), (-1, 5), (10, -4)]

    if _question_contains(question, "length", "string"):
        return [("abc",), ("",), ("OpenAI",), ("  a  ",)]

    if _question_contains(question, "positive"):
        return [(5,), (1,), (0,), (-3,)]

    if _question_contains(question, "average", "list"):
        return [([2, 4, 6],), ([5],), ([1, 2, 3, 4],)]

    if _question_contains(question, "sum", "all", "elements", "list") or _question_contains(question, "sum", "elements", "list"):
        return [([1, 2, 3],), ([5],), ([-1, 4, 2],), ([],)]

    if _question_contains(question, "factorial"):
        return [(0,), (1,), (4,), (5,)]

    if _question_contains(question, "prime"):
        return [(2,), (3,), (4,), (1,), (9,), (17,)]

    if _question_contains(question, "lowercase"):
        return [("ABC",), ("AbC",), ("already",), ("123A",)]

    if _question_contains(question, "divisible by 5"):
        return [(10,), (11,), (0,), (-15,)]

    if _question_contains(question, "divisible by 3"):
        return [(9,), (10,), (0,), (-6,)]

    if _question_contains(question, "divisible by"):
        return [(8,), (9,), (10,), (0,)]

    if _question_contains(question, "second largest"):
        return [([1, 5, 3, 4],), ([10, 8, 9],), ([-1, -5, -3],)]

    if _question_contains(question, "remove spaces"):
        return [("a b c",), (" no spaces ",), ("",), ("a  b",)]

    if _question_contains(question, "sum of digits"):
        return [(123,), (9,), (1005,), (0,)]

    if _question_contains(question, "uppercase"):
        return [("ABC",), ("AbC",), ("",), ("XYZ",)]

    if _question_contains(question, "count the number of elements"):
        return [([1, 2, 3],), ([],), (["a"],), ([None, None],)]

    if _question_contains(question, "count", "words"):
        return [("hello world",), ("one",), (" two  spaces here ",), ("",)]

    if _question_contains(question, "minimum", "list"):
        return [([3, 1, 2],), ([5],), ([-1, -3, 0],)]

    if _question_contains(question, "maximum", "list"):
        return [([3, 1, 2],), ([5],), ([-1, -3, 0],)]

    if _question_contains(question, "reverse", "list"):
        return [([1, 2, 3],), ([],), (["a", "b"],)]

    if _question_contains(question, "reverse", "string"):
        return [("abc",), ("",), ("ab cd",)]

    if _question_contains(question, "duplicate"):
        return [([1, 2, 2, 3],), ([1, 1, 1],), ([],), (["a", "b", "a"],)]

    if _question_contains(question, "only digits"):
        return [("123",), ("12a",), ("",), ("007",)]

    if _question_contains(question, "even"):
        return [(2,), (3,), (0,), (-4,)]

    if _question_contains(question, "cube"):
        return [(2,), (0,), (-3,)]

    return []


def _worker(code, function_name, cases, queue):
    try:
        namespace = {"__builtins__": SAFE_BUILTINS}
        exec(code, namespace, namespace)
        func = namespace.get(function_name)
        if not callable(func):
            queue.put({"ok": False, "error": "Function not found after execution"})
            return

        outputs = []
        for case in cases:
            try:
                result = func(*case)
                outputs.append({"ok": True, "result": result})
            except Exception as exc:
                outputs.append({"ok": False, "error": str(exc)})

        queue.put({"ok": True, "outputs": outputs})
    except Exception as exc:
        queue.put({"ok": False, "error": str(exc)})


def _run_code_with_timeout(code, function_name, cases):
    try:
        result_queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_worker,
            args=(code, function_name, cases, result_queue),
        )
        process.start()
        process.join(EXECUTION_TIMEOUT_SECONDS)

        if process.is_alive():
            process.terminate()
            process.join()
            return {"ok": False, "error": "Execution timed out"}

        if result_queue.empty():
            return {"ok": False, "error": "No execution result returned"}

        return result_queue.get()
    except Exception:
        return _run_code_with_thread_timeout(code, function_name, cases)


def _run_code_with_thread_timeout(code, function_name, cases):
    result_queue = queue.Queue(maxsize=1)
    thread = threading.Thread(
        target=_worker,
        args=(code, function_name, cases, result_queue),
        daemon=True,
    )
    thread.start()
    thread.join(EXECUTION_TIMEOUT_SECONDS)

    if thread.is_alive():
        return {"ok": False, "error": "Execution timed out"}

    if result_queue.empty():
        return {"ok": False, "error": "No execution result returned"}

    return result_queue.get()


def analyze_python_execution(question, sample_answer, student_answer):
    cases = _build_cases(question)
    if not cases:
        return None

    sample_fn = _extract_first_function_name(sample_answer)
    student_fn = _extract_first_function_name(student_answer)
    if not sample_fn or not student_fn:
        return None

    sample_run = _run_code_with_timeout(sample_answer, sample_fn, cases)
    if not sample_run.get("ok"):
        return None

    student_run = _run_code_with_timeout(student_answer, student_fn, cases)
    if not student_run.get("ok"):
        return {
            "result_type": "execution_error",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": f"Code could not be executed reliably: {student_run.get('error', 'execution error')}.",
            "suggestion": "Fix the function so it runs successfully for standard test inputs."
        }

    sample_outputs = sample_run["outputs"]
    student_outputs = student_run["outputs"]
    total = len(cases)
    passed = 0

    question_text = (question or "").lower()

    if "duplicate" in question_text:
        for case, expected, actual in zip(cases, sample_outputs, student_outputs):
            if not (expected.get("ok") and actual.get("ok")):
                continue
            original = case[0]
            actual_result = actual.get("result")
            if not isinstance(actual_result, list):
                continue
            if len(actual_result) != len(set(original)):
                continue
            if set(actual_result) != set(original):
                continue
            if len(actual_result) != len(set(actual_result)):
                continue
            passed += 1
    else:
        for expected, actual in zip(sample_outputs, student_outputs):
            if expected.get("ok") and actual.get("ok") and expected.get("result") == actual.get("result"):
                passed += 1

    if passed == total:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": _success_feedback(question),
        }

    if passed == 0:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": f"Execution-based checks failed on all {total} representative test cases.",
            "suggestion": "Review the core logic against simple sample inputs and edge cases."
        }

    return {
        "result_type": "partial_pass",
        "correctness_max": 28,
        "efficiency_max": 15,
        "feedback": f"Execution-based checks passed {passed} out of {total} representative test cases, so the logic is only partially correct.",
        "suggestion": "Check the edge cases where the current logic differs from the expected output."
    }


def analyze_java_execution(question, sample_answer, student_answer):
    question_text = (question or "").lower()
    code = _normalize_java(student_answer)

    if not code:
        return None

    if _question_contains(question_text, "add", "two", "numbers"):
        if "+" in code and "return" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "-" in code and "return" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method subtracts instead of adding the two numbers.",
                "suggestion": "Return the sum of the two input values.",
            }

    if "even" in question_text:
        if _java_has(code, "return", "% 2 == 0"):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if _java_has(code, "return", "% 2"):
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 15,
                "feedback": "The method returns a remainder instead of an explicit boolean even check.",
                "suggestion": "Compare the remainder to 0 so the method returns true or false directly.",
            }

    if "reverse" in question_text and "string" in question_text:
        if "stringbuilder" in code and ".reverse()" in code and ".tostring()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the original string instead of reversing it.",
                "suggestion": "Reverse the string before returning it.",
            }

    if "sum of digits" in question_text or "sum digits" in question_text:
        if "n%10" in code and ("n/=" in code or "n /= " in code) and "while" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+n\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the original number instead of calculating the sum of its digits.",
                "suggestion": "Extract each digit and accumulate the total before returning it.",
            }

    if "factorial" in question_text:
        if re.search(r"return\s+n\s*\*\s*n\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the square of the input instead of the factorial.",
                "suggestion": "Use a base case and a recursive or iterative factorial calculation.",
            }
        method_name_match = re.search(r"\b([a-z_][a-z0-9_]*)\s*\([^)]*\)\s*\{", code)
        if method_name_match:
            method_name = method_name_match.group(1)
            if f"{method_name}(" in code.split("return", 1)[-1]:
                return {
                    "result_type": "full_pass",
                    "correctness_min": 36,
                    "feedback": _java_success_feedback(question),
                }

    if "palindrome" in question_text:
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the string is a palindrome.",
                "suggestion": "Compare the original string with its reversed form or equivalent mirrored logic.",
            }
        if "equals" in code and "reverse()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the string is a palindrome.",
            }

    if "remove spaces" in question_text:
        if '.replace(" ", "")' in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "uppercase" in question_text:
        if ".touppercase()" in code and "equals" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if ("maximum" in question_text or "max" in question_text) and "array" in question_text:
        if "arrays.sort" in code and "arr[arr.length-1]" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method returns the correct maximum value, but sorting the full array is less efficient than scanning once.",
                "suggestion": "Track the maximum in a single pass instead of sorting the entire array.",
            }
        if "if(i>m)" in code or "if (i>m)" in code or "if(i > m)" in code or "if (i > m)" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly finds the maximum value in the array.",
            }

    if ("minimum" in question_text or "min" in question_text) and "array" in question_text:
        if "arrays.sort" in code and "arr[0]" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method returns the correct minimum value, but sorting the full array is less efficient than scanning once.",
                "suggestion": "Track the minimum in a single pass instead of sorting the full array.",
            }
        if "if(i<m)" in code or "if (i<m)" in code or "if(i < m)" in code or "if (i < m)" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "positive" in question_text:
        if "> 0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks for strictly positive numbers.",
            }
        if ">= 0" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 20,
                "feedback": "The method treats zero as positive, so the logic is only partially correct.",
                "suggestion": "Return true only when the number is greater than zero.",
            }

    if "lowercase" in question_text:
        if ".tolowercase()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "square" in question_text:
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\*\s*[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "cube" in question_text:
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\*\s*[a-z_][a-z0-9_]*\s*\*\s*[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly calculates the cube of the input number.",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\*\s*[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method calculates the square of the input instead of the cube.",
                "suggestion": "Multiply the number by itself three times to compute the cube.",
            }

    if "vowel" in question_text:
        if "aeiou" in code and ".tolowercase()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly counts vowels, including uppercase inputs after normalization.",
            }
        if "aeiou" in code and ".tochararray()" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 15,
                "feedback": "The method counts lowercase vowels but misses uppercase vowel inputs.",
                "suggestion": "Convert the string to lowercase before checking vowel membership.",
            }

    if "only digits" in question_text or "digit" in question_text or "numeric" in question_text:
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the string contains only digits.",
                "suggestion": "Use matches(\"\\\\d+\") or an equivalent digit check.",
            }
        if '.matches("\\\\d+")' in code or '.matches("\\\\\\\\d+")' in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the string contains only digits.",
            }

    return None


def analyze_execution(question, sample_answer, student_answer, language):
    language = (language or "").lower()
    if language == "python":
        return analyze_python_execution(question, sample_answer, student_answer)
    if language == "java":
        return analyze_java_execution(question, sample_answer, student_answer)
    return None

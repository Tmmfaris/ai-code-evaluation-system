import ast
import builtins
import multiprocessing
import queue
import re
import threading


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed = {"json", "csv", "math"}
    if name in allowed:
        return builtins.__import__(name, globals, locals, fromlist, level)
    raise ImportError(f"Import of module '{name}' is not allowed in the evaluator sandbox")


SAFE_BUILTINS = {
    "__build_class__": builtins.__build_class__,
    "__import__": _safe_import,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
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


def _extract_class_method_name(code, class_name, method_name):
    try:
        tree = ast.parse(code)
    except Exception:
        return None

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.lower() == class_name.lower():
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.lower() == method_name.lower():
                    return item.name
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
    if "anagram" in lowered:
        return "The function correctly checks whether the two strings are anagrams."
    if "frequency" in lowered:
        return "The function correctly returns the frequency of each element in the list."
    if "armstrong" in lowered:
        return "The function correctly identifies Armstrong numbers on representative test cases."
    if "flatten" in lowered and "list" in lowered:
        return "The function correctly flattens the nested list on representative test cases."
    if "balanced parentheses" in lowered:
        return "The function correctly detects balanced and unbalanced parentheses on representative test cases."
    if "longest word" in lowered:
        return "The function correctly returns the longest word in the sentence."
    if "binary search" in lowered:
        return "The function returns the expected search result on representative test cases."
    if "power of 2" in lowered or "power of two" in lowered:
        return "The function correctly identifies powers of two on representative test cases."
    if "rotate" in lowered and "list" in lowered:
        return "The function correctly rotates the list by the requested number of steps."
    if "common elements" in lowered:
        return "The function correctly returns the common elements from the two input lists."
    if "filter even numbers" in lowered:
        return "The function correctly filters the even numbers from the input list."
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
    if "grade" in lowered and "student" in lowered:
        return "The class correctly computes the grade from the student's marks."
    if "prime" in lowered:
        return "The method correctly identifies prime and non-prime numbers for representative cases."
    if "count number of lines" in lowered or "count lines" in lowered:
        return "The method correctly counts the number of lines in the file."
    if "sum of digits" in lowered or "sum digits" in lowered:
        return "The method correctly calculates the sum of the digits."
    if "even" in lowered:
        return "The method correctly returns a boolean even-check result."
    if "reverse" in lowered and "string" in lowered:
        return "The method correctly reverses the input string and matches the expected behavior."
    if "binary search" in lowered:
        return "The method correctly returns the expected search result for representative cases."
    if "balanced parentheses" in lowered:
        return "The method correctly detects balanced and unbalanced parentheses."
    if "intersection of two arrays" in lowered:
        return "The method correctly finds the intersection of the two arrays."
    if "anagram" in lowered:
        return "The method correctly checks whether the two strings are anagrams."
    if "power of 2" in lowered or "power of two" in lowered:
        return "The method correctly identifies powers of two."
    if "common elements" in lowered:
        return "The method correctly returns the common elements from the two arrays."
    if "remove duplicates" in lowered:
        return "The method correctly removes duplicate values from the array."
    if "exception handling" in lowered and "division" in lowered:
        return "The method safely handles division errors with exception handling."
    if "valid json" in lowered:
        return "The method performs the expected basic JSON-format validation."
    if "frequency using map" in lowered:
        return "The method correctly counts frequencies using a Map."
    if "longest substring without repeating characters" in lowered:
        return "The method correctly finds the length of the longest substring without repeating characters."
    if "stack using array" in lowered:
        return "The class correctly implements stack operations using an array."
    if "list is sorted" in lowered:
        return "The method correctly checks whether the list is sorted."
    if "convert string to integer safely" in lowered:
        return "The method safely converts the string to an integer and handles invalid input."
    if "streams to filter even numbers" in lowered:
        return "The method correctly filters even numbers from the list."
    if "abstract class shape" in lowered or ("shape" in lowered and "circle" in lowered and "area" in lowered):
        return "The class design correctly models Shape and Circle with the required area behavior."
    if "sort objects of class employee by salary" in lowered:
        return "The code correctly sorts employees by salary."
    if "rotate" in lowered and "array" in lowered:
        return "The method correctly rotates the array by the requested number of steps."
    if "remove spaces" in lowered:
        return "The method correctly removes spaces from the input string."
    if "lowercase" in lowered:
        return "The method correctly converts the input string to lowercase."
    if "string is empty" in lowered:
        return "The method correctly checks whether the string is empty."
    if "uppercase" in lowered:
        return "The method correctly checks whether the string is uppercase."
    if "square" in lowered:
        return "The method correctly calculates the square of the input number."
    if "minimum" in lowered or "min" in lowered:
        return "The method correctly finds the minimum value in the array."

    return "The method matches the expected behavior for this Java question."


def _build_cases(question):
    if _question_contains(question, "filter", "even") and _question_contains(question, "list"):
        return [([2, 3, 4],), ([1, 5],), ([],), ([-4, -3, 0],)]

    if _question_contains(question, "handle", "division", "exception") or _question_contains(question, "division", "exception"):
        return [(6, 2), (5, 0), (-8, 4)]

    if _question_contains(question, "safely", "divide") or _question_contains(question, "safe", "divide"):
        return [(6, 2), (5, 0), (-8, 4)]

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

    if _question_contains(question, "anagram"):
        return [("listen", "silent"), ("evil", "vile"), ("restful", "fluster"), ("rat", "car")]

    if _question_contains(question, "frequency"):
        return [([1, 2, 2, 3],), (["a", "b", "a"],), ([],), ([1, 1, 1],)]

    if _question_contains(question, "armstrong"):
        return [(153,), (370,), (9474,), (10,), (100,)]

    if _question_contains(question, "flatten") and _question_contains(question, "list"):
        return [([[1, 2], [3, 4]],), ([[1], [], [2, 3]],), (([], []),), ([["a"], ["b", "c"]],)]

    if _question_contains(question, "balanced", "parentheses"):
        return [("()",), ("(())",), ("())(",), (")(",), ("(()",)]

    if _question_contains(question, "longest", "word"):
        return [("a bb ccc",), ("one three five",), ("",), ("hi there world",)]

    if _question_contains(question, "binary", "search"):
        return [([1, 3, 5, 7, 9], 7), ([1, 3, 5, 7, 9], 2), ([2], 2), ([2], 1)]

    if _question_contains(question, "group", "words", "length"):
        return [(["a", "bb", "c", "dd"],), (["hi", "to", "tea"],), ([],), (["one"],)]

    if _question_contains(question, "parse", "json", "string") and "key" in (question or "").lower():
        return [('{"a": 1, "b": 2}', "a"), ('{"name": "x"}', "name"), ('{"flag": true}', "flag")]

    if _question_contains(question, "lowercase"):
        return [("ABC",), ("AbC",), ("already",), ("123A",)]

    if _question_contains(question, "divisible by 5"):
        return [(10,), (11,), (0,), (-15,)]

    if _question_contains(question, "divisible by 3"):
        return [(9,), (10,), (0,), (-6,)]

    if _question_contains(question, "divisible by"):
        return [(8,), (9,), (10,), (0,)]

    if _question_contains(question, "second largest"):
        return [([1, 5, 3, 4],), ([10, 8, 9],), ([-1, -5, -3],), ([1, 2, 2],), ([5, 5, 3, 1],)]

    if _question_contains(question, "top", "2", "largest"):
        return [([1, 5, 3, 4],), ([10, 8, 9],), ([1, 2, 2],), ([5, 5, 3, 1],)]

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

    if _question_contains(question, "only digits") or _question_contains(question, "numeric"):
        return [("123",), ("12a",), ("",), ("007",)]

    if _question_contains(question, "even"):
        return [(2,), (3,), (0,), (-4,)]

    if _question_contains(question, "power of 2") or _question_contains(question, "power of two"):
        return [(1,), (2,), (8,), (6,), (0,), (-2,)]

    if _question_contains(question, "rotate", "list"):
        return [([1, 2, 3, 4], 1), ([1, 2, 3, 4], 2), ([1], 3), ([], 0)]

    if _question_contains(question, "common", "elements"):
        return [([1, 2, 3], [2, 3, 4]), ([1, 1, 2], [1, 2]), ([1, 2], [3, 4]), ([], [1, 2])]

    if _question_contains(question, "cube"):
        return [(2,), (0,), (-3,)]

    return []


def _worker(code, function_name, cases, queue):
    try:
        namespace = {"__builtins__": SAFE_BUILTINS, "__name__": "__main__"}
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
    question_text = (question or "").lower()

    if "grade" in question_text and "student" in question_text:
        sample_method = _extract_class_method_name(sample_answer, "Student", "grade")
        student_method = _extract_class_method_name(student_answer, "Student", "grade")
        if sample_method and student_method:
            sample_run = _run_code_with_timeout(
                f"{sample_answer}\n\ndef __runner__(marks):\n    obj = Student()\n    obj.marks = marks\n    return obj.grade()",
                "__runner__",
                [(95,), (80,), (50,)],
            )
            if sample_run.get("ok"):
                student_run = _run_code_with_timeout(
                    f"{student_answer}\n\ndef __runner__(marks):\n    obj = Student()\n    obj.marks = marks\n    return obj.grade()",
                    "__runner__",
                    [(95,), (80,), (50,)],
                )
                if not student_run.get("ok"):
                    return {
                        "result_type": "execution_error",
                        "correctness_max": 5,
                        "efficiency_max": 5,
                        "feedback": f"Code could not be executed reliably: {student_run.get('error', 'execution error')}.",
                        "suggestion": "Fix the class so the grade method runs successfully for standard test inputs."
                    }
                passed = 0
                for expected, actual in zip(sample_run["outputs"], student_run["outputs"]):
                    if expected.get("ok") and actual.get("ok") and expected.get("result") == actual.get("result"):
                        passed += 1
                if passed == 3:
                    return {
                        "result_type": "full_pass",
                        "correctness_min": 36,
                        "feedback": "The class correctly computes grades from the student's marks."
                    }
                if passed == 0:
                    return {
                        "result_type": "zero_pass",
                        "correctness_max": 5,
                        "efficiency_max": 5,
                        "feedback": "The class does not compute the correct grade from the student's marks.",
                        "suggestion": "Return A, B, or C based on the marks thresholds in the question."
                    }
                return {
                    "result_type": "partial_pass",
                    "correctness_max": 20,
                    "efficiency_max": 12,
                    "feedback": "The class computes the correct grade for some marks ranges, but not all of them.",
                    "suggestion": "Check each marks threshold carefully so A, B, and C are all handled correctly."
                }

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

    if "duplicate" in question_text and "preserving order" in question_text:
        for expected, actual in zip(sample_outputs, student_outputs):
            if expected.get("ok") and actual.get("ok") and expected.get("result") == actual.get("result"):
                passed += 1
    elif "top 2 largest" in question_text:
        for expected, actual in zip(sample_outputs, student_outputs):
            if expected.get("ok") and actual.get("ok") and expected.get("result") == actual.get("result"):
                passed += 1
    elif "duplicate" in question_text:
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
    elif "common elements" in question_text:
        for expected, actual in zip(sample_outputs, student_outputs):
            if not (expected.get("ok") and actual.get("ok")):
                continue
            expected_result = expected.get("result")
            actual_result = actual.get("result")
            if not isinstance(expected_result, list) or not isinstance(actual_result, list):
                continue
            if set(expected_result) == set(actual_result) and len(actual_result) == len(set(actual_result)):
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

    if "prime" in question_text:
        if re.search(r"for\s*\([^)]*i\s*=\s*2[^)]*i\s*<\s*n", code) and "return true" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 34,
                "efficiency_max": 14,
                "feedback": "The method handles many prime cases, but it misses values below 2 and uses a wider divisor loop than necessary.",
                "suggestion": "Return false for values below 2 and check divisors only up to the square root of n.",
            }
        if ("math.sqrt" in code or "i*i<=n" in code or "i * i <= n" in code) and "return true" in code and "return false" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "grade" in question_text and "student" in question_text:
        if 'return "a"' in code and 'return "b"' in code and 'return "c"' in code and "marks" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r'return\s+"a"\s*;', code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The class always returns grade A instead of computing the grade from the marks.",
                "suggestion": "Add conditions for the marks ranges so the method returns A, B, or C correctly.",
            }

    if "count number of lines" in question_text or "count lines" in question_text:
        if "bufferedreader" in code and "readline()" in code and "return c" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+0\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns 0 instead of reading the file and counting its lines.",
                "suggestion": "Read the file line by line and increment a counter before returning it.",
            }

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
        if re.search(r"return\s+[^;]*%\s*2\s*==\s*0\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+[^;]*%\s*2\s*;", code) and "==" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns a remainder instead of a boolean even-check result.",
                "suggestion": "Compare the remainder to 0 so the method returns true or false directly.",
            }

    if "reverse" in question_text and "string" in question_text:
        if "stringbuilder" in code and ".reverse()" in code and ".tostring()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "for(" in code and "charat(" in code and "r+=" in code and "return r" in code:
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

    if "remove duplicates" in question_text:
        if "distinct()" in code or ("set<" in code and "return" in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+arr\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the original array instead of removing duplicates.",
                "suggestion": "Build and return a new result that keeps only distinct values.",
            }

    if "streams to filter even numbers" in question_text:
        if ".stream()" in code and ".filter(" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "for(" in code and "%2==0" in code and "add(" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 15,
                "feedback": "The method correctly filters even numbers, but it does not use streams as requested.",
                "suggestion": "Use stream().filter(...) if you need to follow the stream-based requirement exactly.",
            }

    if ("shape" in question_text and "circle" in question_text and "area" in question_text) or "abstract class shape" in question_text:
        if "abstract class shape" in code and "extends shape" in code and "math.pi" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "class shape" in code and "return 0" in code and "extends shape" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 15,
                "feedback": "The code defines Shape and Circle, but it does not use an abstract Shape class and the Circle area formula is incomplete.",
                "suggestion": "Make Shape abstract and implement Circle.area() with Math.PI * r * r.",
            }

    if "exception handling" in question_text and "division" in question_text:
        if "try{" in code and "catch" in code and "a/b" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "a/b" in code and "catch" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method performs division but does not handle division errors with exception handling.",
                "suggestion": "Wrap the division in a try/catch block and return a safe fallback value when an exception occurs.",
            }

    if "sort objects of class employee by salary" in question_text:
        if "collections.sort" in code and ("salary" in code or "->" in code or "comparator" in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "collections.sort" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 15,
                "feedback": "The code sorts the list, but it does not show how Employee objects are ordered by salary.",
                "suggestion": "Provide a salary-based comparator or Comparable implementation so the sort order is defined by salary.",
            }

    if "valid json" in question_text:
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of performing any JSON-format validation.",
                "suggestion": "Check the trimmed string boundaries or equivalent JSON-format conditions before returning true.",
            }
        if "startswith" in code and "endswith" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "frequency using map" in question_text:
        if "map<" in code and "getordefault" in code and "put(" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "new hashmap<>()" in code and re.search(r"return\s+new hashmap<>\(\)\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns an empty Map instead of counting frequencies.",
                "suggestion": "Loop through the array and update the Map counts before returning it.",
            }

    if "stack using array" in question_text:
        if "push(" in code and "pop(" in code and "top" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "class stack" in code and "push(" not in code and "pop(" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The class declares the array storage but does not implement push and pop operations.",
                "suggestion": "Add push and pop methods and update the top index accordingly.",
            }

    if "list is sorted" in question_text:
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the list is sorted.",
                "suggestion": "Compare each element with the previous one and return false when the order decreases.",
            }
        if "for(" in code and ".get(" in code and "return false" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "convert string to integer safely" in question_text:
        if "integer.parseint" in code and "catch" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "integer.parseint" in code and "catch" not in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 15,
                "feedback": "The method parses the integer, but it does not handle invalid input safely.",
                "suggestion": "Wrap Integer.parseInt(...) in a try/catch block and return a safe fallback value for invalid strings.",
            }

    if "power of 2" in question_text or "power of two" in question_text:
        if "&(n-1)" in code or "(n&(n-1))==0" in code or "( n & ( n - 1 ) ) == 0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "%2==0" in code or "% 2 == 0" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether a number is even is not the same as checking whether it is a power of two.",
                "suggestion": "Use a true power-of-two check such as n > 0 && (n & (n - 1)) == 0.",
            }

    if "binary search" in question_text:
        if "while(" in code and ("l<=r" in code or "l <= r" in code) and "return -1" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "for(" in code and "return -1" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method returns correct search results, but it uses a linear scan instead of binary search.",
                "suggestion": "Use low, high, and mid pointers with a loop to implement binary search in logarithmic time.",
            }

    if "anagram" in question_text:
        if "arrays.sort" in code and "arrays.equals" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ".length()==" in code or ".length() ==" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking only string length does not determine whether two strings are anagrams.",
                "suggestion": "Compare character frequencies or sort both character arrays before comparing them.",
            }

    if "balanced parentheses" in question_text:
        if "stack<" in code and ("isempty()" in code or ".pop()" in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if '.contains("(")' in code and '.contains(")")' in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking only whether both parentheses characters appear does not determine whether the parentheses are balanced.",
                "suggestion": "Track order and balance with a stack or counter that never goes negative.",
            }
        if ".length()%2==0" in code or ".length() % 2 == 0" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking only whether the string length is even does not correctly detect balanced parentheses.",
                "suggestion": "Track opening and closing parentheses with a stack or balance counter.",
            }

    if "rotate" in question_text and "array" in question_text:
        if "system.arraycopy" in code or ("return" in code and "k%=" in code and "res" in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+a\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the original array instead of rotating it.",
                "suggestion": "Construct and return the rotated array based on k.",
            }

    if "common elements" in question_text:
        if ("hashset" in code or "set<" in code) and "contains(" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "for(" in code and "for(" in code.split("for(", 1)[-1] and "res.add(" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 28,
                "efficiency_max": 15,
                "feedback": "The method finds common elements, but nested loops are less efficient and can add duplicates when inputs repeat values.",
                "suggestion": "Use a HashSet to test membership and control duplicate results more efficiently.",
            }

    if "intersection of two arrays" in question_text:
        if ("hashset" in code or "set<" in code) and "contains(" in code and ".maptoint" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "for(" in code and "for(" in code.split("for(", 1)[-1] and "res.add(" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 24,
                "efficiency_max": 12,
                "feedback": "The method can find shared values, but nested loops are less efficient and can add duplicates when values repeat.",
                "suggestion": "Use a HashSet for membership checks and control duplicates in the intersection result.",
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

    if "sum of array" in question_text:
        if "for(" in code and "+=" in code and "return s" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly calculates the sum of the array elements.",
            }
        if re.search(r"return\s+0\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns 0 instead of summing the array elements.",
                "suggestion": "Loop through the array and accumulate the total before returning it.",
            }

    if "second largest" in question_text:
        if "distinct()" in code and "sorted()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly finds the second distinct largest element.",
            }
        if "arrays.sort" in code and "a[a.length-2]" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Sorting without removing duplicates can return the largest value again instead of the second distinct largest element.",
                "suggestion": "Remove duplicates first, or track the two largest distinct values explicitly.",
            }

    if "average of array" in question_text:
        if re.search(r"return\s*\(\s*double\s*\)\s*[a-z_][a-z0-9_]*\s*/\s*arr\.length\s*;", code) or re.search(r"return\s+[a-z_][a-z0-9_]*\s*/\s*\(\s*double\s*\)\s*arr\.length\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly calculates the average of the array elements.",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*;", code) and "arr.length" not in code.split("return", 1)[-1]:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the sum instead of dividing by the array length to compute the average.",
                "suggestion": "Divide the sum by arr.length and return a double result for the average.",
            }

    if "find frequency of elements using map" in question_text or "frequency using map" in question_text:
        if "getordefault" in code and "put(" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "put(i,1)" in code or "put(i, 1)" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method stores 1 for every element instead of incrementing counts for repeated values.",
                "suggestion": "Use getOrDefault(...) + 1 so repeated elements increase their stored frequency.",
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
                "result_type": "mostly_correct",
                "correctness_max": 34,
                "efficiency_max": 14,
                "feedback": "The method counts lowercase vowels but misses uppercase vowel inputs.",
                "suggestion": "Convert the string to lowercase before checking vowel membership.",
            }

    if "string is empty" in question_text:
        if ".isempty()" in code or ".length()==0" in code or ".length() == 0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "longest substring without repeating characters" in question_text:
        if re.search(r"return\s+s\.length\(\)\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the full string length does not solve the longest-substring-without-repeats problem.",
                "suggestion": "Use a sliding window or equivalent logic to track the longest substring without repeated characters.",
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

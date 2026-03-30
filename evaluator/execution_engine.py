import ast
import multiprocessing
import queue
import threading


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
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


def _build_cases(question):
    if _question_contains(question, "palindrome"):
        return [("level",), ("hello",), ("",), ("abba",)]

    if _question_contains(question, "length", "string"):
        return [("abc",), ("",), ("OpenAI",), ("  a  ",)]

    if _question_contains(question, "positive"):
        return [(5,), (1,), (0,), (-3,)]

    if _question_contains(question, "average", "list"):
        return [([2, 4, 6],), ([5],), ([1, 2, 3, 4],)]

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

    if _question_contains(question, "minimum", "list"):
        return [([3, 1, 2],), ([5],), ([-1, -3, 0],)]

    if _question_contains(question, "maximum", "list"):
        return [([3, 1, 2],), ([5],), ([-1, -3, 0],)]

    if _question_contains(question, "reverse", "list"):
        return [([1, 2, 3],), ([],), (["a", "b"],)]

    if _question_contains(question, "reverse", "string"):
        return [("abc",), ("",), ("ab cd",)]

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
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": f"Code could not be executed reliably: {student_run.get('error', 'execution error')}.",
            "suggestion": "Fix the function so it runs successfully for standard test inputs."
        }

    sample_outputs = sample_run["outputs"]
    student_outputs = student_run["outputs"]
    total = len(cases)
    passed = 0

    for expected, actual in zip(sample_outputs, student_outputs):
        if expected.get("ok") and actual.get("ok") and expected.get("result") == actual.get("result"):
            passed += 1

    if passed == total:
        return {
            "correctness_min": 36,
            "feedback": "Execution-based checks matched the expected outputs for representative test cases.",
        }

    if passed == 0:
        return {
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": f"Execution-based checks failed on all {total} representative test cases.",
            "suggestion": "Review the core logic against simple sample inputs and edge cases."
        }

    return {
        "correctness_max": 28,
        "efficiency_max": 15,
        "feedback": f"Execution-based checks passed {passed} out of {total} representative test cases, so the logic is only partially correct.",
        "suggestion": "Check the edge cases where the current logic differs from the expected output."
    }

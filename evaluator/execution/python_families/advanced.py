# evaluator/execution/python_families/advanced.py
"""
Deterministic evaluation for advanced Python patterns:
generators, decorators, closures, context managers, comprehensions,
*args/**kwargs, lambda, f-strings, and functional patterns.
"""
import ast
import re


def _has_yield(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(isinstance(n, ast.Yield) or isinstance(n, ast.YieldFrom) for n in ast.walk(tree))
    except Exception:
        return "yield" in (student_answer or "")


def _has_decorator(student_answer, name=None):
    code = student_answer or ""
    if name:
        return f"@{name}" in code
    return "@" in code and "def " in code


def _has_lambda(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(isinstance(n, ast.Lambda) for n in ast.walk(tree))
    except Exception:
        return "lambda" in (student_answer or "")


def _has_comprehension(student_answer, kind="list"):
    try:
        tree = ast.parse(student_answer or "")
        type_map = {
            "list": ast.ListComp,
            "dict": ast.DictComp,
            "set": ast.SetComp,
            "generator": ast.GeneratorExp,
        }
        target_type = type_map.get(kind, ast.ListComp)
        return any(isinstance(n, target_type) for n in ast.walk(tree))
    except Exception:
        if kind == "list":
            return bool(re.search(r"\[.+\bfor\b", student_answer or ""))
        if kind == "dict":
            return bool(re.search(r"\{.+:.+\bfor\b", student_answer or ""))
        return False


def _has_star_args(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.args.vararg or node.args.kwarg:
                    return True
        return False
    except Exception:
        return "*args" in (student_answer or "") or "**kwargs" in (student_answer or "")


def _has_nonlocal(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(isinstance(n, ast.Nonlocal) for n in ast.walk(tree))
    except Exception:
        return "nonlocal" in (student_answer or "")


def _has_context_manager(student_answer):
    code = student_answer or ""
    return "__enter__" in code or "__exit__" in code or "contextmanager" in code


def _has_with_statement(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(isinstance(n, ast.With) for n in ast.walk(tree))
    except Exception:
        return "with " in (student_answer or "")


def _has_functools_wraps(student_answer):
    return "functools.wraps" in (student_answer or "") or "wraps(" in (student_answer or "")


def _has_fstring(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(isinstance(n, ast.JoinedStr) for n in ast.walk(tree))
    except Exception:
        return 'f"' in (student_answer or "") or "f'" in (student_answer or "")


def _has_walrus(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(isinstance(n, ast.NamedExpr) for n in ast.walk(tree))
    except Exception:
        return ":=" in (student_answer or "")


def evaluate_advanced_family(question, question_text, families, normalized_student, student_answer):
    """Evaluate advanced Python feature questions."""
    q = question_text

    # ── Generator / yield ────────────────────────────────────────────────────
    if any(kw in q for kw in ("generator", "yield", "infinite sequence", "lazy sequence", "lazy evaluation")):
        if not _has_yield(student_answer):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The function does not use `yield`, so it is a regular function, not a generator.",
                "suggestion": "Replace `return` with `yield` to turn the function into a generator.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly uses `yield` to implement a generator.",
        }

    # ── Decorator ────────────────────────────────────────────────────────────
    if any(kw in q for kw in ("decorator", "wrap function", "wraps", "@functools")):
        has_dec = _has_decorator(student_answer)
        has_wraps = _has_functools_wraps(student_answer)
        if not has_dec:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The answer does not implement a decorator (a function that wraps another function).",
                "suggestion": "Define an outer function that takes `func` as argument, define a `wrapper(*args, **kwargs)` inside it, and return `wrapper`.",
            }
        if "preserve" in q and not has_wraps:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 28,
                "feedback": "The decorator works but does not use `@functools.wraps(func)` to preserve the original function's metadata.",
                "suggestion": "Add `import functools` and decorate the wrapper function with `@functools.wraps(func)`.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The decorator is correctly implemented and wraps the target function.",
        }

    # ── Closure / nonlocal ───────────────────────────────────────────────────
    if any(kw in q for kw in ("closure", "nonlocal", "enclosing scope", "inner function")):
        if "closure" in q or "nonlocal" in q:
            if not _has_nonlocal(student_answer) and "closure" not in q:
                pass  # closures don't always need nonlocal
            # Check there's at least a nested function
            try:
                tree = ast.parse(student_answer or "")
                nested = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        for child in ast.walk(node):
                            if child is not node and isinstance(child, ast.FunctionDef):
                                nested = True
                if nested:
                    return {
                        "result_type": "full_pass",
                        "correctness_min": 36,
                        "feedback": "The function correctly implements a closure using a nested function.",
                    }
            except Exception:
                pass

    # ── Context Manager ──────────────────────────────────────────────────────
    if any(kw in q for kw in ("context manager", "__enter__", "__exit__", "with statement")):
        if not _has_context_manager(student_answer):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The class does not implement `__enter__` and `__exit__` methods needed for a context manager.",
                "suggestion": "Define `__enter__(self)` and `__exit__(self, exc_type, exc_val, exc_tb)` in the class.",
            }

    # ── List Comprehension ───────────────────────────────────────────────────
    if any(kw in q for kw in ("list comprehension", "using list comprehension", "in one line using comprehension")):
        if not _has_comprehension(student_answer, "list"):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The answer does not use a list comprehension even though the question requires one.",
                "suggestion": "Use the form `[expr for item in iterable if condition]` to write a list comprehension.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The answer correctly uses a list comprehension to produce the expected result.",
        }

    # ── Dict Comprehension ───────────────────────────────────────────────────
    if any(kw in q for kw in ("dict comprehension", "dictionary comprehension")):
        if not _has_comprehension(student_answer, "dict"):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The answer does not use a dictionary comprehension.",
                "suggestion": "Use the form `{key: value for item in iterable}` to write a dict comprehension.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The answer correctly uses a dictionary comprehension.",
        }

    # ── Set Comprehension ─────────────────────────────────────────────────────
    if "set comprehension" in q:
        if not _has_comprehension(student_answer, "set"):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The answer does not use a set comprehension.",
                "suggestion": "Use `{expr for item in iterable}` (with curly braces, no colon) for a set comprehension.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The answer correctly uses a set comprehension.",
        }

    # ── Lambda ───────────────────────────────────────────────────────────────
    if any(kw in q for kw in ("lambda", "anonymous function")):
        if not _has_lambda(student_answer):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The answer does not use a `lambda` expression even though the question requires one.",
                "suggestion": "Use `lambda x: expression` to define an anonymous function.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The answer correctly uses a `lambda` function.",
        }

    # ── *args / **kwargs ─────────────────────────────────────────────────────
    if any(kw in q for kw in ("*args", "**kwargs", "variable arguments", "variable number", "arbitrary arguments")):
        if not _has_star_args(student_answer):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The function does not use `*args` or `**kwargs` to accept variable-length arguments.",
                "suggestion": "Use `def func(*args)` or `def func(**kwargs)` to accept a variable number of arguments.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly uses `*args`/`**kwargs` to handle variable arguments.",
        }

    # ── f-string ─────────────────────────────────────────────────────────────
    # Avoid false positives like "of string" which contains the substring "f string".
    if re.search(r"(?i)(?<![a-z0-9])f[- ]string(?![a-z0-9])|formatted string literal", q):
        if not _has_fstring(student_answer):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The answer does not use an f-string even though the question asks for one.",
                "suggestion": "Use f\"Hello {name}\" syntax to embed variables directly in the string.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The answer correctly uses an f-string for string formatting.",
        }

    # ── Walrus Operator ──────────────────────────────────────────────────────
    if "walrus" in q or ":=" in q:
        if not _has_walrus(student_answer):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The answer does not use the walrus operator `:=`.",
                "suggestion": "Use `:=` to assign and test a value in a single expression, e.g. `while chunk := f.read(1024):`.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The answer correctly uses the walrus operator `:=`.",
        }

    # ── with statement (file/resource handling) ───────────────────────────────
    if any(kw in q for kw in ("with statement", "open file", "read file", "write file", "file handling")) and \
            "context manager" not in q:
        if not _has_with_statement(student_answer):
            if any(kw in q for kw in ("open file", "read file", "write file")):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 8,
                    "feedback": "The answer opens the file without using a `with` statement, so the file may not be closed properly.",
                    "suggestion": "Use `with open(filename) as f:` to ensure the file is automatically closed after use.",
                }
        else:
            if any(kw in q for kw in ("open file", "read file", "write file", "read a file")):
                return {
                    "result_type": "full_pass",
                    "correctness_min": 36,
                    "feedback": "The answer correctly uses a `with` statement for safe file handling.",
                }

    return None

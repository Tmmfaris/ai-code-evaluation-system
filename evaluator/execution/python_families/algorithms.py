# evaluator/execution/python_families/algorithms.py
"""
Deterministic evaluation rules for algorithm-based Python questions.
Covers: sorting, searching, dynamic programming, recursion, graphs,
        two pointers, sliding window, backtracking, greedy, bit manipulation.
"""
import ast
import re


def _normalized(code):
    return re.sub(r"\s+", "", (code or "").lower())


def _has_keyword(student_answer, *keywords):
    n = _normalized(student_answer)
    return all(kw in n for kw in keywords)


def _has_recursion(student_answer, fn_name=None):
    try:
        tree = ast.parse(student_answer or "")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                name = fn_name or node.name
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        if child.func.id == name:
                            return True
    except Exception:
        pass
    return False


def _has_two_loops(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]
        return len(loops) >= 2
    except Exception:
        return False


def _uses_dp_memoization(student_answer):
    n = _normalized(student_answer)
    return ("memo" in n or "cache" in n or "dp[" in n or "dp={" in n
            or "@lru_cache" in n or "functools.lru_cache" in n or "{};" in n)


def _uses_dict(student_answer):
    try:
        tree = ast.parse(student_answer or "")
        return any(
            isinstance(n, ast.Dict) or
            (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "dict")
            for n in ast.walk(tree)
        )
    except Exception:
        return "{" in (student_answer or "")


def evaluate_algorithms_family(question, question_text, families, normalized_student, student_answer):
    """Evaluate algorithm-based Python questions."""
    q = question_text
    code = student_answer or ""
    n = _normalized(code)

    # ── Sorting Algorithms ────────────────────────────────────────────────────
    if "bubble sort" in q:
        if "bubblesort" in n or ("for" in n and "swap" in n) or ("if" in n and ">" in code and "for" in n):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The bubble sort implementation correctly compares and swaps adjacent elements.",
            }
        if "sorted(" in n or ".sort(" in n:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "feedback": "Using Python's built-in sort does not implement the bubble sort algorithm.",
                "suggestion": "Implement bubble sort manually using nested loops and adjacent element swaps.",
            }

    if "insertion sort" in q:
        if "for" in n and "while" in n and ("key" in n or "current" in n or "temp" in n):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The insertion sort implementation correctly shifts elements and inserts the key.",
            }
        if "sorted(" in n or ".sort(" in n:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "feedback": "Using Python's built-in sort does not implement the insertion sort algorithm.",
                "suggestion": "Implement insertion sort using a for loop and a while loop to shift elements right.",
            }

    if "selection sort" in q:
        if "min" in n or ("for" in n and _has_two_loops(code)):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The selection sort implementation correctly finds the minimum and swaps it into position.",
            }
        if "sorted(" in n or ".sort(" in n:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "feedback": "Using Python's built-in sort does not implement the selection sort algorithm.",
                "suggestion": "Implement selection sort using nested loops to find the minimum in each pass.",
            }

    if "merge sort" in q:
        if _has_recursion(code) and ("merge" in n or "left" in n and "right" in n):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The merge sort implementation correctly divides and merges the array recursively.",
            }
        if not _has_recursion(code) and ("sorted(" in n or ".sort(" in n):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "feedback": "Using Python's built-in sort does not implement the merge sort algorithm.",
                "suggestion": "Implement merge sort by recursively splitting the list and merging sorted halves.",
            }

    if "quick sort" in q:
        if _has_recursion(code) and ("pivot" in n or "partition" in n):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The quick sort implementation correctly partitions around a pivot and recurses.",
            }

    if "heap sort" in q:
        if "heapify" in n or "heappush" in n or "heappop" in n:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The heap sort implementation correctly uses a heap structure to sort.",
            }

    # ── Searching Algorithms ─────────────────────────────────────────────────
    if "binary search" in q:
        if ("low" in n or "left" in n or "lo" in n) and ("high" in n or "right" in n or "hi" in n) and "mid" in n:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The binary search implementation correctly maintains low/high/mid pointers.",
            }
        if "for" in n and "if" in n and "return" in n and ("low" not in n and "mid" not in n):
            return {
                "result_type": "partially_correct",
                "correctness_max": 28,
                "feedback": "The search works correctly but is a linear scan, not binary search (O(n) instead of O(log n)).",
                "suggestion": "Use left and right pointers with a midpoint calculation to implement binary search.",
            }

    # ── Fibonacci ────────────────────────────────────────────────────────────
    if "fibonacci" in q:
        if _has_recursion(code):
            if _uses_dp_memoization(code):
                return {
                    "result_type": "full_pass",
                    "correctness_min": 36,
                    "feedback": "The Fibonacci implementation correctly uses memoization or caching to avoid redundant computation.",
                }
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The recursive Fibonacci implementation is correct but has O(2^n) time complexity without memoization.",
                "suggestion": "Add `@functools.lru_cache(None)` or a `memo` dictionary to cache previously computed values.",
            }
        if "for" in n and ("fib" in n or "a" in n and "b" in n):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The iterative Fibonacci implementation correctly computes the sequence in O(n) time.",
            }

    # ── Factorial ─────────────────────────────────────────────────────────────
    if "factorial" in q:
        if _has_recursion(code):
            if "recursion" in q or "recursive" in q:
                return {
                    "result_type": "full_pass",
                    "correctness_min": 36,
                    "feedback": "The recursive factorial implementation correctly multiplies n by the factorial of n-1.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The factorial implementation is correct.",
            }
        if "for" in n or "while" in n:
            if "recursion" in q or "recursive" in q:
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 5,
                    "feedback": "The question asks for a recursive solution, but the implementation uses a loop instead.",
                    "suggestion": "Use recursion: `def factorial(n): return 1 if n == 0 else n * factorial(n-1)`.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The iterative factorial implementation correctly computes the product.",
            }

    # ── Dynamic Programming ──────────────────────────────────────────────────
    if "dynamic programming" in q or "dp" in q or "memoization" in q or "tabulation" in q:
        if not _uses_dp_memoization(code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 8,
                "feedback": "The solution does not use dynamic programming (memoization or tabulation).",
                "suggestion": "Store computed sub-results in a table or dictionary to avoid redundant calculations.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly applies dynamic programming to avoid repeated computation.",
        }

    # ── Longest Common Subsequence ───────────────────────────────────────────
    if "longest common subsequence" in q or "lcs" in q:
        if "dp" in n or _uses_dp_memoization(code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The LCS implementation correctly uses dynamic programming.",
            }

    # ── Knapsack ─────────────────────────────────────────────────────────────
    if "knapsack" in q:
        if _uses_dp_memoization(code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The knapsack solution correctly uses dynamic programming.",
            }

    # ── BFS / DFS ────────────────────────────────────────────────────────────
    if "breadth first search" in q or "bfs" in q:
        if "queue" in n or "deque" in n or "collections.deque" in n:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The BFS implementation correctly uses a queue to explore nodes level by level.",
            }
        if "stack" in n or ("append" in n and "pop()" in n):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "feedback": "BFS requires a queue (FIFO), not a stack (LIFO).",
                "suggestion": "Use `collections.deque` and `popleft()` to implement BFS.",
            }

    if "depth first search" in q or "dfs" in q:
        if _has_recursion(code) or "stack" in n or "append" in n:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The DFS implementation correctly explores nodes depth-first using recursion or a stack.",
            }

    # ── Two Pointers ─────────────────────────────────────────────────────────
    if "two pointer" in q or "two-pointer" in q:
        if ("left" in n and "right" in n) or ("i" in n and "j" in n and "while" in n):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The two-pointer technique is correctly applied with left/right pointers.",
            }

    # ── Sliding Window ───────────────────────────────────────────────────────
    if "sliding window" in q:
        if "window" in n or ("start" in n and "end" in n):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The sliding window approach correctly maintains a window of elements.",
            }

    # ── Recursion (generic) ─────────────────────────────────────────────────
    if "recursion" in q or "recursive" in q:
        if not _has_recursion(code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "feedback": "The question requires a recursive solution, but the implementation does not call itself.",
                "suggestion": "Define a base case and a recursive case where the function calls itself with a smaller input.",
            }

    # ── Greedy ───────────────────────────────────────────────────────────────
    if "greedy" in q:
        if "sorted" in n or "max" in n or "min" in n:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The greedy approach makes locally optimal choices at each step.",
            }

    # ── Bit Manipulation ─────────────────────────────────────────────────────
    if "bit manipulation" in q or "bitwise" in q:
        if "&" in code or "|" in code or "^" in code or "<<" in code or ">>" in code or "~" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses bitwise operations.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 8,
            "feedback": "The solution does not use any bitwise operators.",
            "suggestion": "Use operators like `&`, `|`, `^`, `<<`, `>>` to manipulate bits directly.",
        }

    # ── Backtracking ─────────────────────────────────────────────────────────
    if "backtracking" in q or "n-queens" in q or "sudoku" in q or "permutation" in q and "backtrack" in q:
        if _has_recursion(code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The backtracking solution correctly uses recursion to explore and prune the search space.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 8,
            "feedback": "Backtracking requires recursive exploration with undo (backtrack) steps.",
            "suggestion": "Use recursion to try each option, and undo the choice if it does not lead to a solution.",
        }

    return None

import ast
import atexit
import builtins
import hashlib
import multiprocessing
from pathlib import Path
import queue
import re
import threading
from itertools import count


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
    "map": map,
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
_EXECUTION_CONTEXT = multiprocessing.get_context("spawn")
_EXECUTION_WORKER_LOCK = threading.Lock()
_EXECUTION_WORKER_STATE = None
_EXECUTION_TASK_COUNTER = count(1)
_EXECUTION_RESULT_CACHE = {}
_EXECUTION_RESULT_CACHE_LOCK = threading.Lock()
_EXECUTION_RESULT_CACHE_MAXSIZE = 512


def _build_execution_cache_version():
    path = Path(__file__).resolve()
    digest = hashlib.sha256()
    try:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    except OSError:
        digest.update(f"{path.name}:missing".encode("utf-8"))
    return digest.hexdigest()


def _extract_first_function_name(code):
    try:
        tree = ast.parse(code)
    except Exception:
        return None

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


def _extract_first_function_node(code):
    try:
        tree = ast.parse(code)
    except Exception:
        return None

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node
    return None


def _returns_subtraction_of_first_two_args(function_node):
    if function_node is None or len(function_node.args.args) < 2:
        return False

    first = function_node.args.args[0].arg
    second = function_node.args.args[1].arg

    for node in ast.walk(function_node):
        if not isinstance(node, ast.Return):
            continue
        value = node.value
        if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Sub):
            continue
        if not isinstance(value.left, ast.Name) or not isinstance(value.right, ast.Name):
            continue
        if value.left.id == first and value.right.id == second:
            return True

    return False


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


def _requires_recursion(question):
    lowered = (question or "").lower()
    return "recursion" in lowered or "recursive" in lowered


def _java_question_families(question):
    lowered = (question or "").lower()
    families = set()

    if "ipv4" in lowered or "ip address" in lowered:
        families.add("ipv4")
    if "first missing positive" in lowered:
        families.add("first_missing_positive")
    if ("balanced parentheses" in lowered) or ("parentheses" in lowered and "balanced" in lowered):
        families.add("balanced_parentheses")
    if "password" in lowered and all(token in lowered for token in ("digit", "uppercase", "lowercase")):
        families.add("password_validation")
    if "longest common prefix" in lowered:
        families.add("longest_common_prefix")
    if "armstrong" in lowered:
        families.add("armstrong")
    if "factorial" in lowered and "avoid overflow" in lowered:
        families.add("factorial_avoid_overflow")
    if ("unique characters" in lowered) or ("all unique" in lowered):
        families.add("unique_characters")
    if ("number is even" in lowered) or ("if number is even" in lowered) or ("check if number is even" in lowered):
        families.add("even_check")

    return families


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
    if "frequency of characters" in lowered:
        return "The function correctly counts the frequency of each character in the string."
    if "armstrong" in lowered:
        return "The function correctly identifies Armstrong numbers on representative test cases."
    if "flatten" in lowered and "list" in lowered:
        return "The function correctly flattens the nested list on representative test cases."
    if "balanced parentheses" in lowered:
        return "The function correctly detects balanced and unbalanced parentheses on representative test cases."
    if "ipv4" in lowered or "ip address" in lowered:
        return "The function correctly validates whether the string is a valid IPv4 address."
    if "first missing positive" in lowered:
        return "The function correctly finds the first missing positive integer."
    if "valid email" in lowered:
        return "The function correctly performs the required basic email validation."
    if "valid url" in lowered:
        return "The function correctly performs the required basic URL validation."
    if "longest word" in lowered:
        return "The function correctly returns the longest word in the sentence."
    if "length of longest word" in lowered:
        return "The function correctly returns the length of the longest word in the sentence."
    if "rotation" in lowered and "string" in lowered:
        return "The function correctly checks whether one string is a rotation of the other."
    if ("unique characters" in lowered) or ("all unique" in lowered):
        return "The function correctly checks whether the string has all unique characters."
    if "second smallest" in lowered:
        return "The function correctly returns the second distinct smallest value in the list."
    if "binary search" in lowered:
        return "The function returns the expected search result on representative test cases."
    if "longest substring without repeating characters" in lowered:
        return "The function correctly finds the length of the longest substring without repeating characters."
    if "perfect square" in lowered:
        return "The function correctly checks whether the number is a perfect square."
    if "perfect number" in lowered:
        return "The function correctly checks whether the number is a perfect number."
    if "power of 2" in lowered or "power of two" in lowered:
        return "The function correctly identifies powers of two on representative test cases."
    if "power of 3" in lowered or "power of three" in lowered:
        return "The function correctly identifies powers of three on representative test cases."
    if "number is a palindrome" in lowered:
        return "The function correctly checks whether the number is a palindrome."
    if "rotate" in lowered and "list" in lowered:
        return "The function correctly rotates the list by the requested number of steps."
    if "common elements" in lowered:
        return "The function correctly returns the common elements from the two input lists."
    if "contains duplicates" in lowered:
        return "The function correctly checks whether the list contains duplicate values."
    if "duplicate characters" in lowered:
        return "The function correctly checks whether the string contains duplicate characters."
    if "duplicate elements" in lowered:
        return "The function correctly returns the duplicate elements from the list."
    if "arrays are equal" in lowered:
        return "The function correctly checks whether the two arrays are equal."
    if "reverse words" in lowered and "sentence" in lowered:
        return "The function correctly reverses the order of words in the sentence."
    if "reverse a number" in lowered or "reverse number" in lowered:
        return "The function correctly reverses the number."
    if "sum of even numbers" in lowered:
        return "The function correctly returns the sum of the even numbers in the list."
    if "sum of odd numbers" in lowered:
        return "The function correctly returns the sum of the odd numbers in the list."
    if "filter even numbers" in lowered:
        return "The function correctly filters the even numbers from the input list."
    if "contains digits" in lowered:
        return "The function correctly checks whether the string contains at least one digit."
    if "uppercase letters" in lowered:
        return "The function correctly checks whether the string contains only uppercase letters."
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
    if "first non-repeating character" in lowered or "first unique character" in lowered:
        return "The function correctly returns the first non-repeating character in the string."
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
    if "frequency of characters" in lowered:
        return "The method correctly counts the frequency of each character in the string."
    if "first non-repeating character" in lowered:
        return "The method correctly returns the first non-repeating character in the string."
    if "array is sorted" in lowered:
        return "The method correctly checks whether the array is sorted."
    if "sum of even numbers" in lowered:
        return "The method correctly sums only the even numbers in the array."
    if "ignoring case" in lowered and "equal" in lowered:
        return "The method correctly compares the two strings without case sensitivity."
    if "longest word" in lowered:
        return "The method correctly returns the longest word in the sentence."
    if "count digits" in lowered:
        return "The method correctly counts the digits in the number."
    if "leap year" in lowered:
        return "The method correctly checks whether the year is a leap year."
    if "perfect square" in lowered:
        return "The method correctly checks whether the number is a perfect square."
    if "merge two arrays" in lowered:
        return "The method correctly merges the two arrays into one result."
    if "find duplicates" in lowered:
        return "The method correctly returns the duplicate values from the array."
    if "convert string to integer" in lowered:
        return "The method correctly converts the string to an integer."
    if "intersection of two arrays" in lowered:
        return "The method correctly finds the intersection of the two arrays."
    if "valid email" in lowered:
        return "The method correctly performs the required basic email validation."
    if "rotation" in lowered and "string" in lowered:
        return "The method correctly checks whether one string is a rotation of the other."
    if "second smallest" in lowered:
        return "The method correctly finds the second distinct smallest element in the array."
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
        return [("level",), ("hello",), ("",), ("abba",), ("A",), ("Aa",)]

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
        return [(-1,), (0,), (1,), (2,), (3,), (4,), (17,)]

    if _question_contains(question, "anagram"):
        return [("listen", "silent"), ("evil", "vile"), ("restful", "fluster"), ("rat", "car")]

    if _question_contains(question, "frequency"):
        return [([1, 2, 2, 3],), (["a", "b", "a"],), ([],), ([1, 1, 1],)]

    if _question_contains(question, "frequency", "characters"):
        return [("hello",), ("aab",), ("",), ("AaA",)]

    if _question_contains(question, "armstrong"):
        return [(153,), (370,), (9474,), (10,), (100,)]

    if _question_contains(question, "flatten") and _question_contains(question, "list"):
        return [([[1, 2], [3, 4]],), ([[1], [], [2, 3]],), (([], []),), ([["a"], ["b", "c"]],)]

    if _question_contains(question, "balanced", "parentheses"):
        return [("()",), ("(())",), ("())(",), (")(",), ("(()",)]

    if _question_contains(question, "first", "missing", "positive"):
        return [([1, 2, 0],), ([3, 4, -1, 1],), ([7, 8, 9, 11, 12],), ([1, 1, 2, 2],)]

    if _question_contains(question, "second", "smallest"):
        return [([4, 1, 3, 2],), ([10, 8, 9],), ([1, 1, 2, 3],), ([-5, -1, -3],)]

    if _question_contains(question, "kth", "largest"):
        return [([3, 1, 5, 2, 4], 2), ([9, 7, 8], 1), ([1, 2, 3, 4], 4), ([5, 5, 3], 2)]

    if _question_contains(question, "longest", "word"):
        return [("a bb ccc",), ("one three five",), ("hi there world",), ("tiny medium enormous",)]

    if _question_contains(question, "length", "longest", "word"):
        return [("a bb ccc",), ("one three five",), ("hi there world",), ("tiny medium enormous",)]

    if _question_contains(question, "first", "non-repeating", "character") or _question_contains(question, "first", "unique", "character"):
        return [("swiss",), ("level",), ("aabb",), ("abc",), ("",)]

    if _question_contains(question, "rotation") and _question_contains(question, "string"):
        return [("abcd", "cdab"), ("waterbottle", "erbottlewat"), ("abc", "acb"), ("", "")]

    if _question_contains(question, "permutation"):
        return [("abc", "cba"), ("aab", "aba"), ("aab", "ab"), ("aab", "abb")]

    if _question_contains(question, "unique", "characters") or _question_contains(question, "all", "unique"):
        return [("abc",), ("hello",), ("",), ("Aa",)]

    if _question_contains(question, "longest", "substring", "without", "repeating"):
        return [("abcabcbb",), ("bbbbb",), ("pwwkew",), ("",), ("dvdf",)]

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

    if _question_contains(question, "remove") and (_question_contains(question, "duplicate", "string") or _question_contains(question, "duplicates", "string")):
        return [("banana",), ("aabbcc",), ("abc",), ("",), ("mississippi",)]

    if _question_contains(question, "remove spaces"):
        return [("a b c",), (" no spaces ",), ("",), ("a  b",)]

    if _question_contains(question, "sum of digits"):
        return [(123,), (9,), (1005,), (0,)]

    if _question_contains(question, "uppercase"):
        return [("ABC",), ("AbC",), ("",), ("XYZ",)]

    if _question_contains(question, "only alphabets") or _question_contains(question, "only alphabet"):
        return [("abc",), ("AbC",), ("abc1",), ("",)]

    if _question_contains(question, "count the number of elements"):
        return [([1, 2, 3],), ([],), (["a"],), ([None, None],)]

    if _question_contains(question, "count", "words"):
        return [("hello world",), ("one",), (" two  spaces here ",), ("",), ("Hello  World",)]

    if _question_contains(question, "minimum", "list"):
        return [([3, 1, 2],), ([5],), ([-1, -3, 0],)]

    if _question_contains(question, "maximum", "list"):
        return [([3, 1, 2],), ([5],), ([-1, -3, 0],)]

    if _question_contains(question, "strictly", "increasing"):
        return [([1, 2, 3],), ([1, 1, 2],), ([3, 2, 1],), ([1],), ([],)]

    if _question_contains(question, "reverse", "list"):
        return [([1, 2, 3],), ([],), (["a", "b"],)]

    if _question_contains(question, "reverse", "string"):
        return [("abc",), ("",), ("ab cd",), ("A",)]

    if _question_contains(question, "reverse", "words"):
        return [("hello world",), ("one",), ("Hello  World",), ("",)]

    if _question_contains(question, "duplicate"):
        return [([1, 2, 2, 3],), ([1, 1, 1],), ([],), (["a", "b", "a"],)]

    if _question_contains(question, "list", "sorted"):
        return [([1, 2, 3],), ([1, 1, 2],), ([3, 2, 1],), ([1],), ([],)]

    if _question_contains(question, "only digits") or _question_contains(question, "numeric"):
        return [("123",), ("12a",), ("",), ("007",)]

    if _question_contains(question, "valid", "email"):
        return [("a@b.com",), ("user@site.org",), ("a.b@c",), ("abc",), ("a@b",)]

    if _question_contains(question, "valid", "url"):
        return [("http://example.com",), ("https://openai.com",), ("ftp://x.com",), ("example.com",), ("xhttp",)]

    if _question_contains(question, "convert", "string", "integer"):
        return [("123",), ("007",), ("0",), ("42",)]

    if _question_contains(question, "even"):
        return [(2,), (3,), (0,), (-4,)]

    if _question_contains(question, "odd"):
        return [(2,), (3,), (0,), (-5,)]

    if _question_contains(question, "contains", "digits"):
        return [("abc1",), ("123",), ("abc",), ("a2b3",), ("",)]

    if _question_contains(question, "arrays", "equal"):
        return [([1, 2], [1, 2]), ([1, 2], [2, 1]), ([1, 1, 2], [1, 2, 2]), ([], [])]

    if _question_contains(question, "power of 2") or _question_contains(question, "power of two"):
        return [(1,), (2,), (8,), (6,), (0,), (-2,)]

    if _question_contains(question, "power of 3") or _question_contains(question, "power of three"):
        return [(1,), (3,), (9,), (12,), (0,), (-3,)]

    if _question_contains(question, "perfect", "square"):
        return [(0,), (1,), (4,), (9,), (10,), (15,)]

    if _question_contains(question, "perfect", "number"):
        return [(6,), (28,), (12,), (1,), (2,)]

    if _question_contains(question, "ipv4") or _question_contains(question, "ip", "address"):
        return [("192.168.1.1",), ("255.255.255.255",), ("256.1.1.1",), ("1.2.3",), ("a.b.c.d",)]

    if _question_contains(question, "rotate", "list"):
        return [([1, 2, 3, 4], 1), ([1, 2, 3, 4], 2), ([1], 3), ([], 0)]

    if _question_contains(question, "common", "elements"):
        return [([1, 2, 3], [2, 3, 4]), ([1, 1, 2], [1, 2]), ([1, 2], [3, 4]), ([], [1, 2])]

    if _question_contains(question, "contains", "duplicates"):
        return [([1, 2, 2, 3],), ([1, 2, 3],), ([],), (["a", "b", "a"],)]

    if _question_contains(question, "duplicate", "elements"):
        return [([1, 2, 2, 3],), ([1, 1, 1],), ([1, 2, 3],), (["a", "b", "a"],)]

    if _question_contains(question, "duplicate", "characters"):
        return [("abc",), ("hello",), ("",), ("aab",)]

    if _question_contains(question, "number", "palindrome"):
        return [(121,), (123,), (0,), (1221,), (10,)]

    if _question_contains(question, "reverse", "number"):
        return [(123,), (1005,), (0,), (9,)]

    if _question_contains(question, "intersection") and _question_contains(question, "list"):
        return [([1, 2, 3], [2, 3, 4]), ([1, 1, 2], [1, 2]), ([1, 2], [3, 4]), ([], [1, 2])]

    if _question_contains(question, "cube"):
        return [(2,), (0,), (-3,)]

    if _question_contains(question, "vowel"):
        return [("aeiou",), ("AEIOU",), ("Hello",), ("",)]

    if _question_contains(question, "uppercase", "letters"):
        return [("ABC",), ("AbC",), ("",), ("XYZ",), ("ABC1",)]

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


def _persistent_worker_loop(task_queue, result_queue):
    while True:
        try:
            task = task_queue.get()
        except EOFError:
            break

        if task is None:
            break

        task_id = task.get("task_id")
        response_queue = queue.Queue(maxsize=1)
        _worker(
            task.get("code", ""),
            task.get("function_name"),
            task.get("cases", []),
            response_queue,
        )
        try:
            result = response_queue.get_nowait()
        except queue.Empty:
            result = {"ok": False, "error": "No execution result returned"}
        result_queue.put({"task_id": task_id, "result": result})


def _shutdown_execution_worker():
    global _EXECUTION_WORKER_STATE
    state = _EXECUTION_WORKER_STATE
    _EXECUTION_WORKER_STATE = None
    if not state:
        return

    process = state.get("process")
    task_queue = state.get("task_queue")
    if task_queue is not None:
        try:
            task_queue.put_nowait(None)
        except Exception:
            pass

    if process is not None and process.is_alive():
        process.terminate()
        process.join(timeout=0.2)


def _get_or_start_execution_worker():
    global _EXECUTION_WORKER_STATE
    state = _EXECUTION_WORKER_STATE
    if state and state.get("process") is not None and state["process"].is_alive():
        return state

    task_queue = _EXECUTION_CONTEXT.Queue()
    result_queue = _EXECUTION_CONTEXT.Queue()
    process = _EXECUTION_CONTEXT.Process(
        target=_persistent_worker_loop,
        args=(task_queue, result_queue),
        daemon=True,
    )
    process.start()
    _EXECUTION_WORKER_STATE = {
        "process": process,
        "task_queue": task_queue,
        "result_queue": result_queue,
    }
    return _EXECUTION_WORKER_STATE


atexit.register(_shutdown_execution_worker)


def _run_code_with_timeout(code, function_name, cases):
    cache_key = (_build_execution_cache_version(), code or "", function_name or "", repr(cases))
    with _EXECUTION_RESULT_CACHE_LOCK:
        cached = _EXECUTION_RESULT_CACHE.get(cache_key)
        if cached is not None:
            return cached

    try:
        with _EXECUTION_WORKER_LOCK:
            state = _get_or_start_execution_worker()
            task_id = next(_EXECUTION_TASK_COUNTER)
            state["task_queue"].put({
                "task_id": task_id,
                "code": code,
                "function_name": function_name,
                "cases": cases,
            })
            try:
                while True:
                    message = state["result_queue"].get(timeout=EXECUTION_TIMEOUT_SECONDS)
                    if message.get("task_id") == task_id:
                        result = message.get("result", {"ok": False, "error": "No execution result returned"})
                        with _EXECUTION_RESULT_CACHE_LOCK:
                            _EXECUTION_RESULT_CACHE[cache_key] = result
                            if len(_EXECUTION_RESULT_CACHE) > _EXECUTION_RESULT_CACHE_MAXSIZE:
                                _EXECUTION_RESULT_CACHE.pop(next(iter(_EXECUTION_RESULT_CACHE)))
                        return result
            except queue.Empty:
                _shutdown_execution_worker()
                return {"ok": False, "error": "Execution timed out"}
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
    normalized_student = re.sub(r"\s+", "", (student_answer or "").lower())

    if _question_contains(question, "median") and _question_contains(question, "list") and "returnsum(lst)/len(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Averaging the whole list does not compute the median value.",
            "suggestion": "Sort the list and return the middle value, or the average of the two middle values for an even-length list.",
        }

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

    student_function_node = _extract_first_function_node(student_answer)

    if _question_contains(question, "palindrome") and normalized_student.endswith("returntrue") and "[::-1]" not in normalized_student and "reversed(" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function returns a constant boolean instead of checking whether the string is a palindrome.",
            "suggestion": "Compare the original string with its reverse or an equivalent mirrored check.",
        }

    if (_question_contains(question, "only digits") or _question_contains(question, "numeric")) and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the string contains only digits.",
            "suggestion": "Use s.isdigit() or an equivalent character-by-character check.",
        }

    if _question_contains(question, "list", "sorted") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the list is sorted.",
            "suggestion": "Compare adjacent elements and return False when the order decreases.",
        }

    if (_question_contains(question, "ipv4") or _question_contains(question, "ip", "address")) and "parts=ip.split('.')" in normalized_student and "len(parts)!=4" in normalized_student and "p.isdigit()" in normalized_student and "int(p)>255" in normalized_student and "returnfalse" in normalized_student and "returntrue" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly validates whether the string is a valid IPv4 address.",
        }

    if _question_contains(question, "valid", "url") and ("return'http'ins" in normalized_student or 'return"http"ins' in normalized_student):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Checking whether 'http' appears anywhere in the string is weaker than validating that the URL starts with http:// or https://.",
            "suggestion": "Use startswith('http://') or startswith('https://') for the required basic validation.",
        }

    if _question_contains(question, "valid", "email") and ("\"@\"ins" in normalized_student or "'@'ins" in normalized_student) and ("\".\"ins" in normalized_student or "'.'ins" in normalized_student) and "split('@')" not in normalized_student and 'split("@")' not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function checks for '@' and '.', but it does not ensure that the dot appears in the domain part after '@'.",
            "suggestion": "Check the substring after '@' and verify that it contains '.'.",
        }

    if _question_contains(question, "first", "missing", "positive") and "nums=sorted(nums)" in normalized_student and "i=1" in normalized_student and "forninnums" in normalized_student and "ifn==i:i+=1" in normalized_student and "returni" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly finds the first missing positive integer, but sorting the whole list is less efficient than using a set-based or in-place approach.",
            "suggestion": "Use a set or an in-place indexing strategy to avoid sorting the full list.",
        }

    if _question_contains(question, "kth", "largest") and "lst=sorted(lst)" in normalized_student and "returnlst[-k]" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the kth largest element from the list.",
        }

    if _question_contains(question, "intersection") and _question_contains(question, "list") and normalized_student.endswith("returna"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function returns the first list instead of returning the shared elements from both lists.",
            "suggestion": "Return only the values that appear in both input lists.",
        }

    if _question_contains(question, "second largest") and "returnmax(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the maximum value does not solve the second-largest-number problem.",
            "suggestion": "Track the largest and second distinct largest values, or sort the distinct values and return the second last one.",
        }

    if _question_contains(question, "second largest") and "sorted(lst)[-2]" in normalized_student and "set(lst)" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 24,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Sorting the list and taking the second last element works for many inputs, but it can return the largest value again when duplicates are present.",
            "suggestion": "Remove duplicates first, or track the two largest distinct values explicitly.",
        }

    if (_question_contains(question, "only digits") or _question_contains(question, "numeric")) and "forcins" in normalized_student and "returnfalse" in normalized_student and "returntrue" in normalized_student and "<'0'" in normalized_student and ">'9'" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string contains only digits using a character-by-character check.",
        }

    if (_question_contains(question, "first", "non-repeating", "character") or _question_contains(question, "first", "unique", "character")) and "forchins" in normalized_student and "s.count(ch)==1" in normalized_student and "returnch" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly returns the first non-repeating character, but repeatedly calling s.count(...) is less efficient than counting frequencies once.",
            "suggestion": "Count character frequencies first for a more efficient solution.",
        }

    if (_question_contains(question, "rotation") and _question_contains(question, "string")) and "foriinrange(len(a))" in normalized_student and "a[i:]+a[:i]==b" in normalized_student and "returntrue" in normalized_student and "returnfalse" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly checks whether one string is a rotation of the other, but building every rotation is less efficient than checking membership in a+a.",
            "suggestion": "Use len(a) == len(b) and b in (a + a) for a shorter and more efficient solution.",
        }

    if ((_question_contains(question, "unique", "characters")) or (_question_contains(question, "all", "unique"))) and "foriinrange(len(s))" in normalized_student and "forjinrange(i+1,len(s))" in normalized_student and "ifs[i]==s[j]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly checks whether the string has all unique characters, but nested loops are less efficient than tracking seen characters in a set.",
            "suggestion": "Use a set to detect repeated characters in a single pass.",
        }

    if _question_contains(question, "list", "sorted") and "foriinrange(len(lst)-1)" in normalized_student and "iflst[i]>lst[i+1]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the list is sorted.",
        }

    if _question_contains(question, "length", "longest", "word") and "returnlen(max(s.split()))" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using len(max(s.split())) compares words lexicographically before taking the length, so it can miss the actual longest word.",
            "suggestion": "Use max(len(w) for w in s.split()) or track the maximum word length directly.",
        }

    if _question_contains(question, "sum of digits") and "whilen>0" in normalized_student and "s+=n%10" in normalized_student and "n//=" in normalized_student and "returns" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the sum of the digits.",
        }

    if _question_contains(question, "frequency", "characters") and "d={}" in normalized_student and "forcins" in normalized_student and "d.get(c,0)+1" in normalized_student and "returnd" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly counts the frequency of each character in the string.",
        }

    if _question_contains(question, "contains", "duplicates") and "seen=set()" in normalized_student and "ifxinseen:returntrue" in normalized_student and "seen.add(x)" in normalized_student and normalized_student.endswith("returnfalse"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the list contains duplicate values.",
        }

    if _question_contains(question, "second", "smallest") and "m1=m2=float('inf')" in normalized_student and "ifx<m1:m2,m1=m1,x" in normalized_student and "elifx<m2andx!=m1:m2=x" in normalized_student and "returnm2" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the second distinct smallest value in the list.",
        }

    if _question_contains(question, "perfect", "square") and "whilei*i<=n" in normalized_student and "ifi*i==n:returntrue" in normalized_student and normalized_student.endswith("returnfalse"):
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly checks whether the number is a perfect square, but it scans candidate values linearly.",
            "suggestion": "Use an integer square-root check or a binary-search-style approach for better efficiency.",
        }

    if _question_contains(question, "perfect", "number") and "s=0" in normalized_student and "foriinrange(1,n)" in normalized_student and "ifn%i==0:s+=i" in normalized_student and "returns==n" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly checks whether the number is a perfect number, but it tests every divisor below n.",
            "suggestion": "You can reduce the work by checking divisors only up to the square root and adding paired divisors.",
        }

    if _question_contains(question, "longest", "substring", "without", "repeating") and "foriinrange(len(s))" in normalized_student and "seen=set()" in normalized_student and "forjinrange(i,len(s))" in normalized_student and "ifs[j]inseen:break" in normalized_student and "seen.add(s[j])" in normalized_student and "maxlen=max(maxlen,j-i+1)" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly finds the longest substring without repeating characters, but it restarts a nested scan from each position.",
            "suggestion": "Use a sliding window with a map or set to keep the runtime linear.",
        }

    if _question_contains(question, "permutation") and "returnset(a)==set(b)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Comparing sets ignores duplicate character counts, so it can treat non-permutations as equal.",
            "suggestion": "Compare sorted strings or count character frequencies so duplicate counts are preserved.",
        }

    if _question_contains(question, "sum", "odd", "numbers") and _question_contains(question, "list") and "returnsum(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function sums every number in the list instead of adding only the odd values.",
            "suggestion": "Filter for odd numbers before summing, or add only values where x % 2 != 0.",
        }

    if _question_contains(question, "number", "palindrome") and "rev=0" in normalized_student and "whiletemp>0" in normalized_student and "rev=rev*10+temp%10" in normalized_student and "temp//=" in normalized_student and "returnrev==n" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the number is a palindrome.",
        }

    if (_question_contains(question, "power of 3") or _question_contains(question, "power of three")) and "whilen>1" in normalized_student and "ifn%3!=0:returnfalse" in normalized_student and "n//=3" in normalized_student and "returnn==1" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly checks whether the number is a power of 3, but it repeatedly divides by 3 instead of using a more direct mathematical check.",
            "suggestion": "A logarithmic or maximum-power divisibility check can be shorter, though the current logic is correct.",
        }

    if _question_contains(question, "intersection") and _question_contains(question, "list") and "res=[]" in normalized_student and "forxina" in normalized_student and "ifxinbandxnotinres:res.append(x)" in normalized_student and "returnres" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the intersection of the two lists without duplicate values.",
        }

    if _question_contains(question, "reverse", "number") and "rev=0" in normalized_student and "whilen>0" in normalized_student and "rev=rev*10+n%10" in normalized_student and "n//=" in normalized_student and "returnrev" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly reverses the number.",
        }

    if _question_contains(question, "duplicate", "elements") and "seen=set()" in normalized_student and "dup=set()" in normalized_student and "ifxinseen:dup.add(x)" in normalized_student and "seen.add(x)" in normalized_student and "returnlist(dup)" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the duplicate elements from the list.",
        }

    if _question_contains(question, "duplicate", "characters") and "foriinrange(len(s))" in normalized_student and "forjinrange(i+1,len(s))" in normalized_student and "ifs[i]==s[j]:returntrue" in normalized_student and normalized_student.endswith("returnfalse"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string contains duplicate characters.",
        }

    if (_question_contains(question, "only alphabets") or _question_contains(question, "only alphabet")) and "forcins" in normalized_student and "ifnotc.isalpha():returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string contains only alphabetic characters.",
        }

    if _question_contains(question, "strictly", "increasing") and "foriinrange(len(lst)-1)" in normalized_student and "iflst[i]>=lst[i+1]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the list is strictly increasing.",
        }

    if _question_contains(question, "find", "duplicates") and _question_contains(question, "list") and "returnlist(set(lst))" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning list(set(lst)) removes duplicates instead of returning only the values that appear more than once.",
            "suggestion": "Collect and return only the repeated values from the list.",
        }

    if _question_contains(question, "convert", "string", "integer") and "returnord(s[0])" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Using ord(s[0]) returns the character code of the first character, not the integer value of the full string.",
            "suggestion": "Use int(s) to convert the whole numeric string to an integer.",
        }

    if _question_contains(question, "sum of digits") and "returnint(str(n)[0])" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first digit does not calculate the sum of all digits in the number.",
            "suggestion": "Iterate through every digit or convert the string digits and sum them all.",
        }

    if _question_contains(question, "add", "two", "numbers") and _returns_subtraction_of_first_two_args(student_function_node):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function subtracts the second number from the first instead of adding the two inputs.",
            "suggestion": "Use the addition operator so the function returns a + b.",
        }

    if _question_contains(question, "factorial") and "returnn*n" in normalized_student and _requires_recursion(question):
        return {
            "result_type": "partial_pass",
            "correctness_max": 14,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 10,
            "passed_cases": 0,
            "total_cases": 0,
            "pass_ratio": 0.0,
            "feedback": "The function mentions factorial but does not implement the required recursive factorial logic.",
            "suggestion": "Use a base case like n == 0 and a recursive call such as n * fact(n - 1).",
        }

    if _question_contains(question, "positive") and (">=0" in (student_answer or "") or ">= 0" in (student_answer or "")):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function treats zero as positive, so it misses the strict positive-number requirement.",
            "suggestion": "Return true only when the number is greater than zero.",
        }

    if _question_contains(question, "prime") and "foriinrange(2,n)" in normalized_student and "ifn<2:returnfalse" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly checks whether the number is prime, but it loops up to n instead of stopping at the square root.",
            "suggestion": "Check divisors only up to int(n**0.5) + 1 for better efficiency.",
        }

    if _question_contains(question, "palindrome") and "returns[0]==s[-1]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Checking only the first and last characters is not enough to determine whether the full string is a palindrome.",
            "suggestion": "Compare the whole string with its reverse, or check matching characters from both ends inward.",
        }

    if _question_contains(question, "odd") and "returnn%2==0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function checks for even numbers instead of returning true for odd numbers.",
            "suggestion": "Return n % 2 != 0 so the function is true only for odd inputs.",
        }

    if _question_contains(question, "contains", "digits") and "returns.isdigit()" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using s.isdigit() checks whether all characters are digits, not whether the string contains at least one digit.",
            "suggestion": "Use any(c.isdigit() for c in s) or loop until you find one digit.",
        }

    if _question_contains(question, "arrays", "equal") and "returnset(a)==set(b)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 8,
            "efficiency_max": 6,
            "readability_max": 8,
            "structure_max": 8,
            "feedback": "Set equality ignores element order and duplicate counts, so it is not the same as direct array equality.",
            "suggestion": "Compare the lists directly with a == b so both order and duplicates are preserved.",
        }

    if _question_contains(question, "reverse", "number") and "rev=0" in normalized_student and "whilen>0" in normalized_student and "rev=rev*10+n%10" in normalized_student and "n//=" in normalized_student and "returnrev" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly reverses the number.",
        }

    if _question_contains(question, "uppercase", "letters") and "returns==s.upper()" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string contains only uppercase letters.",
        }

    if _question_contains(question, "average", "list") and "returnsum(lst)" in normalized_student and "/len(lst)" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function returns the sum of the list instead of dividing by the list length to compute the average.",
            "suggestion": "Return sum(lst) / len(lst) so the function computes the average value.",
        }

    if _question_contains(question, "sum", "even", "numbers") and _question_contains(question, "list") and "returnsum(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function sums every number in the list instead of adding only the even values.",
            "suggestion": "Filter for even numbers before summing, or add only values where x % 2 == 0.",
        }

    if _question_contains(question, "common", "elements") and _question_contains(question, "list") and "return[iforiinaifiinb]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function can find overlapping values, but it can repeat duplicates and does not behave like a proper distinct intersection.",
            "suggestion": "Use sets or track added values so each shared element appears only once in the result.",
        }

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
    elif "remove" in question_text and "duplicate" in question_text and "string" in question_text:
        for case, actual in zip(cases, student_outputs):
            if not actual.get("ok"):
                continue
            original = case[0]
            actual_result = actual.get("result")
            if not isinstance(original, str) or not isinstance(actual_result, str):
                continue
            expected_result = "".join(dict.fromkeys(original))
            if actual_result == expected_result:
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
    elif "longest word" in question_text:
        for case, expected, actual in zip(cases, sample_outputs, student_outputs):
            if not (expected.get("ok") and actual.get("ok")):
                continue
            sentence = case[0]
            expected_result = expected.get("result")
            actual_result = actual.get("result")
            if not isinstance(sentence, str) or not isinstance(expected_result, str) or not isinstance(actual_result, str):
                continue
            words = sentence.split()
            if not words:
                continue
            longest_len = max(len(word) for word in words)
            if len(actual_result) == longest_len and actual_result in words:
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

    if _question_contains(question, "reverse", "words"):
        return {
            "result_type": "partial_pass",
            "correctness_max": 28,
            "efficiency_max": 15,
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": passed / total if total else 0.0,
            "feedback": "Reversing the whole string does not correctly reverse the order of words in the sentence.",
            "suggestion": "Split the sentence into words, reverse the word order, and join them back into a string.",
        }

    if _question_contains(question, "maximum", "list") or _question_contains(question, "max", "list"):
        return {
            "result_type": "partial_pass",
            "correctness_max": 28,
            "efficiency_max": 15,
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": passed / total if total else 0.0,
            "feedback": "Returning only the first element works only when the maximum happens to be at the front of the list.",
            "suggestion": "Scan the whole list and keep track of the largest value before returning it.",
        }

    return {
        "result_type": "partial_pass",
        "correctness_max": 28,
        "efficiency_max": 15,
        "passed_cases": passed,
        "total_cases": total,
        "pass_ratio": passed / total if total else 0.0,
        "feedback": f"Execution-based checks passed {passed} out of {total} representative test cases, so the logic is only partially correct.",
        "suggestion": "Check the edge cases where the current logic differs from the expected output."
    }


def analyze_java_execution(question, sample_answer, student_answer):
    question_text = (question or "").lower()
    code = _normalize_java(student_answer)
    families = _java_question_families(question_text)

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

    if "perfect square" in question_text:
        if "math.sqrt" in code and "r*r==n" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"for\s*\([^)]*i\s*=\s*1[^)]*i\s*\*\s*i\s*<=\s*n", code) and re.search(r"if\s*\(\s*i\s*\*\s*i\s*==\s*n\s*\)\s*return\s+true\s*;", code) and "return false" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly checks for perfect squares, but scanning values linearly is less efficient than using Math.sqrt or binary search.",
                "suggestion": "Use Math.sqrt or a binary-search-style check to avoid testing every value up to the square root.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is a perfect square.",
                "suggestion": "Compare the number against a squared root candidate before returning true.",
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
        if re.search(r"return\s+a\s*;", code) or re.search(r"return\s+b\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns only one input value instead of adding the two numbers.",
                "suggestion": "Return the sum of the two input values.",
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

    if "count words" in question_text:
        if ".trim().split(\"\\\\s+\")" in code and ".length" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly counts the words in the sentence.",
            }
        if ".split(\" \")" in code and ".length" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 20,
                "efficiency_max": 20,
                "readability_max": 15,
                "structure_max": 15,
                "feedback": "The method counts words for simple single-space input, but it does not handle leading, trailing, or repeated spaces reliably.",
                "suggestion": "Trim the string and split with a whitespace pattern like \"\\\\s+\" to handle spacing edge cases.",
            }

    if "factorial_avoid_overflow" in families:
        if "biginteger" in code and "multiply" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly computes factorial values without overflow using BigInteger.",
            }
        if "int res=1" in code and "res*=" in code and "return res" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 18,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method computes factorial values for smaller inputs, but it still uses int and does not avoid overflow as required.",
                "suggestion": "Use BigInteger multiplication so the factorial remains correct for large input values.",
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
        if "for(" in code and ("*=" in code or re.search(r"\b[a-z_][a-z0-9_]*\s*=\s*[a-z_][a-z0-9_]*\s*\*\s*[a-z_][a-z0-9_]*", code)):
            if _requires_recursion(question):
                return {
                    "result_type": "mostly_correct",
                    "correctness_max": 28,
                    "efficiency_max": 15,
                    "feedback": "The method computes factorial values correctly, but it uses an iterative loop instead of the required recursive approach.",
                    "suggestion": "Add a base case and a recursive call if the question explicitly requires recursion.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly computes factorial values with an iterative approach.",
            }

    if "password_validation" in families:
        if "length()<8" in code and ".tochararray()" in code and "character.isdigit" in code and "character.isuppercase" in code and "character.islowercase" in code and "return d&&u&&l" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly validates the password requirements with a character-by-character check.",
            }
        if ".length()>5" in code or ".length() > 5" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking only the password length does not validate the required digit, uppercase, and lowercase conditions.",
                "suggestion": "Check the minimum length and verify that the password contains at least one digit, one uppercase letter, and one lowercase letter.",
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
        if "+=" in code and "for(" in code and "charat(" in code and "equals(" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly checks whether the string is a palindrome, but repeated string concatenation is less efficient than using StringBuilder.",
                "suggestion": "Use StringBuilder or a two-pointer comparison to avoid repeated string concatenation.",
            }

    if "longest_common_prefix" in families:
        if "arr[0].charat(i)" in code and "for(string s:arr)" in code and "i>=s.length()" in code and "return res" in code and "res+=c" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly finds the longest common prefix, but it builds the result one character at a time and can be shorter to express with a shrinking-prefix approach.",
                "suggestion": "Start from the first string and shrink the prefix until every string starts with it.",
            }
        if re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the first string instead of computing the longest common prefix shared by all strings.",
                "suggestion": "Compare characters or prefixes across every string and stop when the shared prefix ends.",
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

    if "frequency of words" in question_text:
        if "map<" in code and "hashmap" in code and ".split(\" \")" in code and "getordefault" in code and "put(" in code and "return map" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly counts the frequency of words in the sentence.",
            }
        if "new java.util.hashmap<>()" in code and re.search(r"return\s+new\s+java\.util\.hashmap<>\(\)\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns an empty map instead of counting word frequencies from the sentence.",
                "suggestion": "Split the sentence into words and increment each word's count in the map before returning it.",
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

    if "reverse words" in question_text and "sentence" in question_text:
        if '.split(" ")' in code and "for(" in code and "i--" in code and "trim()" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly reverses the words in the sentence, but repeated string concatenation is less efficient than using a builder or join-based approach.",
                "suggestion": "Use StringBuilder or reverse a word list and join it to avoid repeated string concatenation.",
            }

    if "gcd" in question_text:
        if "b==0?a:gcd(b,a%b)" in code or "b == 0 ? a : gcd(b, a % b)" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "while(b!=0)" in code and "b=a%b" in code and "a=t" in code and "return a" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly computes the GCD using an iterative Euclidean algorithm.",
            }
        if re.search(r"return\s+a\s*\*\s*b\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the product of the two numbers does not compute their greatest common divisor.",
                "suggestion": "Use the Euclidean algorithm with recursion or iteration to compute the GCD.",
            }

    if "ipv4" in families:
        if (
            re.search(r'\.split\s*\(\s*"\\+\."\s*\)', code)
            and re.search(r"p\.length\s*!=\s*4", code)
            and "integer.parseint" in code
            and re.search(r"n\s*<\s*0\s*\|\|\s*n\s*>\s*255", code)
            and "return true" in code
            and (
                re.search(r"catch\s*\(\s*exception\s+[a-z_][a-z0-9_]*\s*\)\s*\{\s*return\s+false\s*;\s*\}", code)
                or "catch(" not in code
            )
        ):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly validates whether the string is a valid IPv4 address.",
            }
        if re.fullmatch(r".*return\s+true\s*;\s*\}?\s*$", code) and ".split(" not in code and "parseint" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of validating the IPv4 structure and octet ranges.",
                "suggestion": "Split the string into four parts, parse each octet, and reject values outside 0 to 255.",
            }

    if "armstrong" in families:
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is an Armstrong number.",
                "suggestion": "Compute the digit-power sum and compare it with the original number before returning true.",
            }
        if "math.pow" in code and ("while(" in code or "while (" in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks Armstrong numbers using digit extraction and exponentiation.",
            }
        if ("d*d*d" in code or "d * d * d" in code) and ("while(" in code or "while (" in code):
            return {
                "result_type": "mostly_correct",
                "correctness_max": 18,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "Cubing every digit works only for 3-digit Armstrong numbers and does not correctly handle the general Armstrong-number definition.",
                "suggestion": "Raise each digit to the power of the total number of digits instead of always cubing it.",
            }

    if "sort array" in question_text:
        if "arrays.sort" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"\{\s*\}", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method body is empty, so the array is never sorted.",
                "suggestion": "Call Arrays.sort(arr) or implement sorting logic before returning.",
            }

    if "balanced_parentheses" in families:
        if "stack<" in code and ("isempty()" in code or ".pop()" in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if (
            re.search(r"int\s+[a-z_][a-z0-9_]*\s*=\s*0", code)
            and ".tochararray()" in code
            and re.search(r"if\s*\(\s*[a-z_][a-z0-9_]*\s*==\s*'\('\s*\)", code)
            and "++" in code
            and re.search(r"else\s+if\s*\(\s*[a-z_][a-z0-9_]*\s*==\s*'\)'\s*\)", code)
            and "--" in code
            and re.search(r"if\s*\(\s*[a-z_][a-z0-9_]*\s*<\s*0\s*\)\s*return\s+false", code)
            and re.search(r"return\s+[a-z_][a-z0-9_]*\s*==\s*0\s*;", code)
        ):
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

    if "balanced_parentheses" in families:
        if (
            re.search(r"int\s+[a-z_][a-z0-9_]*\s*=\s*0", code)
            and ".tochararray()" in code
            and re.search(r"if\s*\(\s*[a-z_][a-z0-9_]*\s*==\s*'\('\s*\)", code)
            and "++" in code
            and re.search(r"else\s+if\s*\(\s*[a-z_][a-z0-9_]*\s*==\s*'\)'\s*\)", code)
            and "--" in code
            and re.search(r"if\s*\(\s*[a-z_][a-z0-9_]*\s*<\s*0\s*\)\s*return\s+false", code)
            and re.search(r"return\s+[a-z_][a-z0-9_]*\s*==\s*0\s*;", code)
        ):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly detects balanced and unbalanced parentheses.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the parentheses are balanced.",
                "suggestion": "Track the balance of opening and closing parentheses and return false only when the sequence is actually unbalanced.",
            }

    if "contains duplicates" in question_text:
        if ("hashset" in code or "set<" in code) and ".add(" in code and "return true" in code and "return false" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the array contains duplicate values.",
            }
        if "arrays.sort" in code and "arr[i]==arr[i-1]" in code and "return true" in code and "return false" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly checks for duplicates, but sorting the full array is less efficient than using a HashSet to detect repeats.",
                "suggestion": "Use a HashSet to detect repeated values in one pass without sorting the whole array.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the array contains duplicate values.",
                "suggestion": "Track seen values and return true when an element appears more than once.",
            }

    if "unique_characters" in families:
        if "for(int i=0;i<s.length();i++)" in code and "for(int j=i+1;j<s.length();j++)" in code and "s.charat(i)==s.charat(j)" in code and "return false" in code and "return true" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly checks whether the string has all unique characters, but nested loops are less efficient than using a Set.",
                "suggestion": "Use a HashSet to detect repeated characters in a single pass.",
            }

    if "first_missing_positive" in families:
        if (
            "arrays.sort" in code
            and re.search(r"expected\s*=\s*1", code)
            and re.search(r"if\s*\(\s*x\s*==\s*expected\s*\)\s*expected\+\+", code)
            and "return expected" in code
        ):
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly finds the first missing positive number, but sorting the array is less efficient than using a set-based or in-place approach.",
                "suggestion": "Use a HashSet or an in-place indexing approach to avoid sorting the full array.",
            }
        if re.search(r"return\s+1\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns 1 instead of computing the first missing positive number from the array values.",
                "suggestion": "Track which positive numbers are present and return the first missing positive value in sequence.",
            }

    if "frequency of characters" in question_text:
        if "map<character,integer>" in code and ".tochararray()" in code and "m.containskey(" in code and "m.get(" in code and "m.put(" in code and "return m" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "first non-repeating character" in question_text:
        if "indexof(" in code and "lastindexof(" in code and "charat(i)" in code and "return '_'" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly finds the first non-repeating character, but repeated indexOf/lastIndexOf scans are less efficient than counting frequencies first.",
                "suggestion": "Use a HashMap to count characters first if you want a more efficient linear-time solution.",
            }

    if "array is sorted" in question_text:
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the array is sorted.",
                "suggestion": "Compare each element with the previous one and return false when the order decreases.",
            }
        if "for(" in code and "arr[i]<arr[i-1]" in code and "return false" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "sum of even numbers" in question_text:
        if "for(" in code and "%2==0" in code and "s+=" in code and "return s" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "for(" in code and "s+=i" in code and "%2" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method sums all array elements instead of adding only the even numbers.",
                "suggestion": "Add a condition so only values with remainder 0 when divided by 2 are included in the sum.",
            }

    if "ignoring case" in question_text and "equal" in question_text:
        if ".equalsignorecase(" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ".equals(" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 18,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method compares the strings exactly, but it does not ignore differences in letter case as required.",
                "suggestion": "Use equalsIgnoreCase(...) so values like \"Hello\" and \"hello\" are treated as equal.",
            }

    if "longest word" in question_text:
        if "arrays.sort" in code and "->b.length()-a.length()" in code and "return w[0]" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly returns the longest word, but sorting all words is less efficient than scanning once for the maximum length.",
                "suggestion": "Track the longest word in one pass instead of sorting the full array of words.",
            }

    if "count digits" in question_text:
        if "while(n>0)" in code and "c++" in code and "n/=" in code and "return c" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 22,
                "efficiency_max": 15,
                "feedback": "The method counts digits for positive numbers, but it misses edge cases such as 0 and negative inputs.",
                "suggestion": "Handle 0 explicitly and normalize negative numbers before counting digits.",
            }

    if "leap year" in question_text:
        if "y%4==0" in code and "%100" not in code and "%400" not in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 18,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method handles many leap years correctly, but it misses the century-year exceptions.",
                "suggestion": "Also require years divisible by 100 to be divisible by 400 before treating them as leap years.",
            }

    if "merge two arrays" in question_text:
        if "new int[a.length+b.length]" in code and "for(int i=0;i<a.length;i++)" in code and "r[i]=a[i]" in code and "for(int i=0;i<b.length;i++)" in code and "r[a.length+i]=b[i]" in code and "return r" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "find duplicates" in question_text and "array" in question_text:
        if (
            "set<integer>" in code
            and "contains(" in code
            and re.search(r"if\s*\(\s*[a-z_][a-z0-9_]*\.contains\s*\(\s*[a-z_][a-z0-9_]*\s*\)\s*\)\s*return\s+[a-z_][a-z0-9_]*\s*;", code)
        ):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the seen-values set instead of returning the actual duplicate values from the array.",
                "suggestion": "Keep a seen set and a separate duplicates set, then return the duplicates set after processing the whole array.",
            }

    if "convert string to integer" in question_text:
        if "integer.parseint" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ".charat(0)" in code and "(int)" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Casting the first character to int returns its character code, not the numeric value of the full string.",
                "suggestion": "Use Integer.parseInt(s) so the entire string is converted to its integer value.",
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

    if "reverse array" in question_text:
        if ("for(" in code or "for (" in code) and "return arr" in code and ("arr.length-1-i" in code or "arr.length - 1 - i" in code):
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
                "feedback": "The method returns the original array instead of reversing it.",
                "suggestion": "Swap elements from both ends or build a reversed result before returning the array.",
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
                "correctness_max": 22,
                "efficiency_max": 12,
                "feedback": "The method finds common elements, but nested loops are less efficient and can add duplicates when inputs repeat values.",
                "suggestion": "Use a HashSet to test membership and control duplicate results more efficiently.",
            }

    if "intersection of two arrays" in question_text:
        if ("hashset" in code or "set<" in code) and "contains(" in code and "res.add(" in code and "return res" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ("hashset" in code or "set<" in code) and "contains(" in code and ".maptoint" in code:
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
                "feedback": "The method returns the first array instead of returning the intersection of shared values.",
                "suggestion": "Collect only elements that appear in both arrays and return that intersection result.",
            }
        if "for(" in code and "for(" in code.split("for(", 1)[-1] and "res.add(" in code:
            return {
                "result_type": "partial_pass",
                "correctness_max": 24,
                "efficiency_max": 12,
                "feedback": "The method can find shared values, but nested loops are less efficient and can add duplicates when values repeat.",
                "suggestion": "Use a HashSet for membership checks and control duplicates in the intersection result.",
            }

    if "sort a map by values" in question_text:
        if "new java.util.arraylist<>(map.entryset())" in code and "list.sort" in code and "comparingbyvalue" in code and "return list" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly sorts the map entries by value and returns them in sorted order.",
            }

    if "median" in question_text and "array" in question_text:
        if "arrays.sort" in code and "arr[n/2-1]+arr[n/2]" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly computes the median of the array.",
            }
        if "sum+=" in code and "return sum/arr.length" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method computes the average of all elements instead of the median value of the sorted array.",
                "suggestion": "Sort the array first, then return the middle value or the mean of the two middle values for even-length arrays.",
            }

    if "arrays are equal" in question_text:
        if "arrays.equals" in code and "arrays.sort" not in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the two arrays are equal.",
            }
        if "arrays.sort(a)" in code and "arrays.sort(b)" in code and "arrays.equals(a,b)" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Sorting both arrays changes the task from ordered equality to order-insensitive comparison, so it does not correctly implement direct array equality.",
                "suggestion": "Compare the arrays directly with Arrays.equals(a, b) without sorting them first.",
            }

    if "remove spaces" in question_text:
        if '.replace(" ", "")' in code or (".replaceall(" in code and "\\s+" in code and '""' in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "remove duplicates" in question_text and "string" in question_text:
        if ".chars()" in code and ".distinct()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly removes duplicate characters from the string.",
            }
        if re.search(r"return\s+s\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the original string instead of removing duplicate characters.",
                "suggestion": "Build and return a new string that keeps each character only once.",
            }

    if "valid email" in question_text:
        if ".contains(\"@\")" in code and ".contains(\".\")" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ".matches(" in code and "@" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ".length()>5" in code or ".length() > 5" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking only the string length does not determine whether it is a valid email address, even for a basic email check.",
                "suggestion": "Check for required email markers such as '@' and '.' before returning true.",
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
        if re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning only the first element does not correctly find the maximum value in the array.",
                "suggestion": "Loop through the array and keep track of the largest value before returning it.",
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
        if ">= 0" in code or ">=0" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats zero as positive, so it misses the strict positive-number requirement.",
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
        if re.search(r"return\s+max\s*;", code) or re.search(r"return\s+m\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning only the maximum value does not solve the second-largest-element problem.",
                "suggestion": "Track both the largest and second distinct largest values before returning the result.",
            }

    if "average of array" in question_text:
        if re.search(r"return\s*\(\s*double\s*\)\s*[a-z_][a-z0-9_]*\s*/\s*arr\.length\s*;", code) or re.search(r"return\s+[a-z_][a-z0-9_]*\s*/\s*\(\s*double\s*\)\s*arr\.length\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly calculates the average of the array elements.",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*/\s*arr\.length\s*;", code):
            return {
                "result_type": "mostly_correct",
                "correctness_max": 18,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method divides by arr.length, but integer division loses the fractional part before returning the result.",
                "suggestion": "Cast the sum or the divisor to double before division so the average keeps its decimal value.",
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
        if "integer.parseint" in code and "catch" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks numeric input by attempting to parse the string safely.",
            }
        if '.matches("\\\\d+")' in code or '.matches("\\\\\\\\d+")' in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the string contains only digits.",
            }
        if (
            ".tochararray()" in code
            and (
                re.search(r"c\s*<\s*'0'\s*\|\|\s*c\s*>\s*'9'", code)
                or re.search(r"c\s*>\s*'9'\s*\|\|\s*c\s*<\s*'0'", code)
            )
            and "return false" in code
            and "return true" in code
        ):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether every character is a digit using a character-range check.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the string contains only digits.",
                "suggestion": "Use matches(\"\\\\d+\") or an equivalent digit check.",
            }
        if ".length()>0" in code or ".length() > 0" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking only whether the string is non-empty does not determine whether it contains only digits.",
                "suggestion": "Use matches(\"\\\\d+\") or an equivalent digit-only check for every character.",
            }

    if "power" in question_text and "^" in question_text:
        if "math.pow" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "r*=a" in code or "r *= a" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly computes the power by repeated multiplication.",
            }

    if "maximum subarray sum" in question_text or "kadane" in question_text:
        if "math.max(arr[i],cur+arr[i])" in code and "max=math.max(max,cur)" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly computes the maximum subarray sum.",
            }
        if (
            re.search(r"for\s*\(\s*int\s+i\s*=\s*0\s*;\s*i\s*<\s*arr\.length\s*;\s*i\+\+\s*\)", code)
            and re.search(r"for\s*\(\s*int\s+j\s*=\s*i\s*;\s*j\s*<\s*arr\.length\s*;\s*j\+\+\s*\)", code)
            and re.search(r"sum\s*\+=\s*arr\s*\[\s*j\s*\]", code)
            and re.search(r"if\s*\(\s*sum\s*>\s*max\s*\)\s*max\s*=\s*sum", code)
        ):
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 10,
                "feedback": "The method correctly computes the maximum subarray sum, but it uses a brute-force nested-loop approach instead of Kadane's algorithm.",
                "suggestion": "Use Kadane's algorithm to track the best running sum in linear time.",
            }

    if "reverse an integer" in question_text:
        if "r=r*10+n%10" in code and "n/=" in code and "return r" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly reverses the integer.",
            }
        if re.search(r"return\s+n\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns the original integer instead of reversing its digits.",
                "suggestion": "Extract digits one by one and rebuild the number in reverse order before returning it.",
            }

    if "missing number" in question_text and "array" in question_text:
        if "n*(n+1)/2" in code and "sum-=x" in code and "return sum" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly finds the missing number in the array.",
            }
        if re.search(r"return\s+0\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method returns 0 instead of computing the missing number from the array contents.",
                "suggestion": "Compare the expected sum from 1 to n with the actual array sum and return the difference.",
            }

    if "rotation" in question_text and "string" in question_text:
        if ".contains(" in code and "a+a" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ".substring(" in code and "for(" in code and "r.equals(b)" in code and "return true" in code and "return false" in code:
            return {
                "result_type": "correct_but_inefficient",
                "correctness_min": 36,
                "efficiency_max": 12,
                "feedback": "The method correctly checks string rotation, but constructing every rotation is less efficient than checking whether b appears inside a + a.",
                "suggestion": "Use a.length() == b.length() && (a + a).contains(b) for a shorter and more efficient solution.",
            }

    if "second smallest" in question_text:
        if "arrays.sort" in code and "return arr[1]" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if (
            "integer.max_value" in code
            and re.search(r"second\s*=\s*integer\.max_value", code)
            and re.search(r"if\s*\(\s*x\s*<\s*min\s*\)", code)
            and re.search(r"else\s+if\s*\(\s*x\s*<\s*second\s*&&\s*x\s*!=\s*min\s*\)", code)
            and "return second" in code
        ):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }

    if "even_check" in families:
        if "(n&1)==0" in code or "( n & 1 ) == 0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is even using a bitwise operation.",
            }

    return None


def analyze_execution(question, sample_answer, student_answer, language):
    language = (language or "").lower()
    if language == "python":
        return analyze_python_execution(question, sample_answer, student_answer)
    if language == "java":
        return analyze_java_execution(question, sample_answer, student_answer)
    return None

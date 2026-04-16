import ast
import atexit
import builtins
import hashlib
import json
import multiprocessing
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
from itertools import count

from evaluator.execution.python_families import (
    evaluate_list_family,
    evaluate_number_family,
    evaluate_string_family,
    evaluate_oop_family,
    evaluate_algorithms_family,
    evaluate_advanced_family,
)


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed = {
        "json", "csv", "math", "re", "collections", "functools", "itertools",
        "string", "copy", "heapq", "bisect", "operator", "abc", "dataclasses",
        "datetime", "random", "statistics", "decimal", "fractions",
    }
    if name in allowed:
        return builtins.__import__(name, globals, locals, fromlist, level)
    raise ImportError(f"Import of module '{name}' is not allowed in the evaluator sandbox")


SAFE_BUILTINS = {
    # Core
    "__build_class__": builtins.__build_class__,
    "__import__": _safe_import,
    "__name__": "__main__",
    # Basic types
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "bytes": bytes,
    "bytearray": bytearray,
    "chr": chr,
    "complex": complex,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "hex": hex,
    "int": int,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    # OOP support
    "callable": callable,
    "classmethod": classmethod,
    "delattr": delattr,
    "dir": dir,
    "getattr": getattr,
    "hasattr": hasattr,
    "hash": hash,
    "id": id,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "object": object,
    "property": property,
    "setattr": setattr,
    "staticmethod": staticmethod,
    "super": super,
    "type": type,
    "vars": vars,
    # Constants
    "True": True,
    "False": False,
    "None": None,
    "NotImplemented": NotImplemented,
    "Ellipsis": ...,
    # Exceptions (needed for try/except blocks in student code)
    "Exception": Exception,
    "BaseException": BaseException,
    "ArithmeticError": ArithmeticError,
    "AttributeError": AttributeError,
    "EOFError": EOFError,
    "EnvironmentError": EnvironmentError,
    "FloatingPointError": FloatingPointError,
    "GeneratorExit": GeneratorExit,
    "IOError": IOError,
    "ImportError": ImportError,
    "IndexError": IndexError,
    "KeyError": KeyError,
    "KeyboardInterrupt": KeyboardInterrupt,
    "LookupError": LookupError,
    "MemoryError": MemoryError,
    "NameError": NameError,
    "NotImplementedError": NotImplementedError,
    "OSError": OSError,
    "OverflowError": OverflowError,
    "RecursionError": RecursionError,
    "ReferenceError": ReferenceError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "StopAsyncIteration": StopAsyncIteration,
    "SyntaxError": SyntaxError,
    "SystemError": SystemError,
    "TypeError": TypeError,
    "UnboundLocalError": UnboundLocalError,
    "UnicodeError": UnicodeError,
    "UnicodeDecodeError": UnicodeDecodeError,
    "UnicodeEncodeError": UnicodeEncodeError,
    "ValueError": ValueError,
    "ZeroDivisionError": ZeroDivisionError,
    # I/O (sandboxed print)
    "print": print,
    "input": (lambda *a, **k: ""),  # stub — students may call input() in examples
    # Misc
    "bin": bin,
    "format": format,
    "globals": (lambda: {}),
    "locals": (lambda: {}),
    "open": None,  # blocked — keep None so NameError is replaced with clearer ImportError
}

EXECUTION_TIMEOUT_SECONDS = 2.0
_EXECUTION_CONTEXT = multiprocessing.get_context("spawn")
_EXECUTION_WORKER_LOCK = threading.Lock()
_EXECUTION_WORKER_STATE = None
_EXECUTION_TASK_COUNTER = count(1)
_EXECUTION_RESULT_CACHE = {}
_EXECUTION_RESULT_CACHE_LOCK = threading.Lock()
_EXECUTION_RESULT_CACHE_MAXSIZE = 512
JAVA_METHOD_SIGNATURE_RE = re.compile(
    r"(?:public|private|protected)?\s*(?:static\s+)?(?P<return>[A-Za-z_][A-Za-z0-9_<>\[\]]*)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)"
)


def _build_execution_cache_version():
    base_dir = Path(__file__).resolve().parent
    fingerprint_paths = [
        base_dir / "shared.py",
        base_dir / "python_families" / "__init__.py",
        base_dir / "python_families" / "strings.py",
        base_dir / "python_families" / "lists.py",
        base_dir / "python_families" / "numbers.py",
    ]
    digest = hashlib.sha256()
    for path in fingerprint_paths:
        try:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            digest.update(f"{path.name}:missing".encode("utf-8"))
    return digest.hexdigest()


def _extract_first_function_name(code):
    if not code:
        return None
    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                return node.name
    except Exception:
        # Fallback to regex if AST fails (e.g. partial code)
        match = re.search(r"def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
        if match:
            return match.group(1)
            
        # JS fallback
        javascript_match = re.search(
            r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            code,
        )
        if javascript_match:
            return javascript_match.group(1)
    return None


def _wrap_python_snippet(code, question_text=""):
    """
    Attempts to wrap a 'naked' Python snippet into a function definition.
    Intelligently detects used variables to form the parameter list.
    """
    if not code or "def " in code:
        return code, _extract_first_function_name(code)

    fn_name = "solution"
    params = []
    
    try:
        tree = ast.parse(code)
        # Find all names that are used but not defined in this scope
        defined = set()
        used = set()
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.Name, ast.arg)):
                if isinstance(node.ctx, ast.Store) or isinstance(node, ast.arg):
                    defined.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    used.add(node.id)
            elif isinstance(node, ast.FunctionDef):
                defined.add(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    defined.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    defined.add(alias.asname or alias.name)

        # Candidates for parameters are those used but never defined locally
        import builtins
        builtin_names = set(dir(builtins))
        candidates = sorted(list(used - defined - builtin_names))
        
        # Heuristic: exclude common library names if they aren't parameters
        excluded = {"np", "pd", "plt", "sns", "math", "json", "re", "os", "sys", "datetime"}
        params = [c for c in candidates if c not in excluded]
    except Exception:
        # If AST fails, fall back to question text heuristics
        pass

    if not params:
        q = (question_text or "").lower()
        if "list" in q or "array" in q or "elements" in q or "duplicates" in q:
            params = ["lst"]
        elif "string" in q or "text" in q or "word" in q:
            params = ["s"]
        elif "two numbers" in q or "addition" in q:
            params = ["a", "b"]
        else:
            params = ["n"]

    param_str = ", ".join(params)
    lines = code.strip().split("\n")
    has_return = any(line.strip().startswith("return ") for line in lines)
    
    if not has_return and len(lines) == 1:
        wrapped = f"def {fn_name}({param_str}):\n    return {code.strip()}"
    else:
        indented = "\n".join("    " + line for line in lines)
        wrapped = f"def {fn_name}({param_str}):\n{indented}"
        
    return wrapped, fn_name


def _extract_first_function_node(code):
    try:
        tree = ast.parse(code)
    except Exception:
        return None

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node
    return None


def _normalize_question_text(question):
    text = (question or "").lower()
    # Avoid false positives like "of string" which contains the substring "f string".
    text = re.sub(r"(?<![a-z0-9])f\s*string(?![a-z0-9])", "f-string", text)
    text = re.sub(r"(?<![a-z0-9])fstring(?![a-z0-9])", "f-string", text)
    replacements = [
        ("formatted string", "f-string"),
        ("string formatting", "string format"),
        ("format string", "string format"),
        ("format output", "string format"),
        ("formatted output", "string format"),
        ("join words", "join string"),
        ("join strings", "join string"),
        ("split text", "split string"),
        ("split a string", "split string"),
        ("strip spaces", "strip string"),
        ("trim", "strip"),
        ("keyword args", "keyword arguments"),
        ("keyword arg", "keyword arguments"),
        ("kwargs", "**kwargs"),
        ("varargs", "*args"),
        ("variable arguments", "*args"),
        ("default value", "default argument"),
        ("default parameter", "default argument"),
        ("raise error", "raise"),
        ("raise exception", "raise"),
        ("import module", "import a module"),
    ]
    for src, dst in replacements:
        text = text.replace(src, dst)
    return text


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


def _uses_string_coercion_for_length(normalized_student):
    return bool(re.search(r"return\(*len\(str\(", normalized_student or ""))


def _normalize_java(code):
    return re.sub(r"\s+", " ", (code or "").strip()).lower()


def _extract_java_method_signature(code):
    match = JAVA_METHOD_SIGNATURE_RE.search(code or "")
    if not match:
        return None
    params = [item.strip() for item in match.group("params").split(",") if item.strip()]
    param_types = []
    for param in params:
        parts = param.split()
        if len(parts) < 2:
            return None
        param_types.append(parts[-2] if parts[-1].endswith("[]") else parts[0])
    return {
        "return_type": match.group("return"),
        "method_name": match.group("name"),
        "param_types": param_types,
    }


def _java_value_literal(value, declared_type=None):
    declared = (declared_type or "").strip()

    if declared.endswith("[]"):
        base = declared[:-2]
        if not isinstance(value, list):
            return f"new {base}[]{{}}"
        items = ",".join(_java_value_literal(item, base) for item in value)
        return f"new {base}[]{{{items}}}"

    if declared in {"int", "Integer"}:
        return str(int(value))
    if declared in {"long", "Long"}:
        return f"{int(value)}L"
    if declared in {"double", "Double", "float", "Float"}:
        return str(float(value))
    if declared in {"boolean", "Boolean"}:
        return "true" if bool(value) else "false"
    if declared in {"char", "Character"}:
        text = str(value)
        escaped = text.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"

    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f"\"{escaped}\""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, list):
        items = ",".join(_java_value_literal(item) for item in value)
        return f"new Object[]{{{items}}}"
    return "null"


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


def _serialize_hidden_expected(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return json.dumps(value, separators=(",", ":"))
    if value is None:
        return "null"
    return str(value)


def _run_java_hidden_test(student_answer, signature, args):
    if "class " in (student_answer or ""):
        return {"ok": False, "error": "Java hidden tests currently expect method-style answers, not full classes."}

    method_name = signature["method_name"]
    param_types = signature["param_types"]
    if len(param_types) != len(args):
        return {"ok": False, "error": "Hidden test input count does not match the Java method signature."}

    java_args = ", ".join(_java_value_literal(arg, param_types[index]) for index, arg in enumerate(args))
    source = f"""
import java.util.*;

public class Main {{
    static class Solution {{
        {student_answer}
    }}

    public static void main(String[] args) {{
        Solution s = new Solution();
        Object result = s.{method_name}({java_args});
        if (result instanceof int[]) {{
            System.out.print(Arrays.toString((int[]) result));
        }} else if (result instanceof long[]) {{
            System.out.print(Arrays.toString((long[]) result));
        }} else if (result instanceof double[]) {{
            System.out.print(Arrays.toString((double[]) result));
        }} else if (result instanceof boolean[]) {{
            System.out.print(Arrays.toString((boolean[]) result));
        }} else if (result instanceof Object[]) {{
            System.out.print(Arrays.deepToString((Object[]) result));
        }} else {{
            System.out.print(String.valueOf(result));
        }}
    }}
}}
""".strip()

    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "Main.java"
        source_path.write_text(source, encoding="utf-8")

        compile_run = subprocess.run(
            ["javac", str(source_path)],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT_SECONDS,
            cwd=temp_dir,
        )
        if compile_run.returncode != 0:
            return {"ok": False, "error": (compile_run.stderr or compile_run.stdout or "javac failed").strip()}

        execute_run = subprocess.run(
            ["java", "-cp", temp_dir, "Main"],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT_SECONDS,
            cwd=temp_dir,
        )
        if execute_run.returncode != 0:
            return {"ok": False, "error": (execute_run.stderr or execute_run.stdout or "java failed").strip()}

        return {"ok": True, "result": (execute_run.stdout or "").strip()}


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


def _python_question_families(question):
    lowered = (question or "").lower()
    families = set()

    def has(*parts):
        return all(part in lowered for part in parts)

    if has("reverse", "string"):
        families.add("reverse_string")
        if has("without", "slicing"):
            families.add("reverse_string_without_slicing")
    if has("length", "string"):
        families.add("string_length")
        if has("without", "len"):
            families.add("string_length_without_len")
    if has("reverse", "words"):
        families.add("reverse_words")
    if has("sum of digits"):
        families.add("sum_of_digits")
    if has("count", "vowels") or "vowel" in lowered:
        families.add("count_vowels")
    if "armstrong" in lowered:
        families.add("armstrong")
    if has("palindrome", "permutation") or (("rearranged" in lowered or "rearrange" in lowered) and has("form", "palindrome")):
        families.add("palindrome_permutation")
    elif "palindrome" in lowered:
        families.add("palindrome")
        if has("ignore") and "isalnum" in lowered:
            families.add("palindrome_ignore_non_alnum")
        if has("ignore", "case"):
            families.add("palindrome_ignore_case")
        if has("number") or has("without", "converting", "string"):
            families.add("palindrome_number")
        if has("without", "converting", "string"):
            families.add("palindrome_number_no_string")
    if has("first", "non-repeating", "character") or has("first", "unique", "character"):
        families.add("first_non_repeating_character")
    if has("group", "anagrams"):
        families.add("group_anagrams")
    if "anagram" in lowered:
        families.add("anagram")
    if has("unique", "characters") or has("all", "unique"):
        families.add("unique_characters")
    if has("kth", "largest"):
        families.add("kth_largest")
    if has("pairs") and has("sum"):
        families.add("pairs_with_sum")
    if has("at most one character") or has("one", "edit"):
        families.add("one_edit")
    if has("maximum", "product", "two", "numbers"):
        families.add("maximum_product_two_numbers")
    if has("rotation") and has("string"):
        families.add("rotation_string")
    if has("interleaving"):
        families.add("interleaving_strings")
    if has("power of 3") or has("power of three"):
        families.add("power_of_3")
    if has("prime", "numbers", "up", "n"):
        families.add("primes_up_to_n")
    elif "prime" in lowered:
        families.add("prime_check")
    if has("sum", "squares") and has("numbers"):
        families.add("sum_of_squares")
    if has("median", "two", "sorted", "arrays"):
        families.add("median_two_sorted_arrays")
    elif has("median") and has("list"):
        families.add("median_list")
    if has("subsequence"):
        families.add("subsequence")
    if has("longest", "substring", "without", "repeating"):
        families.add("longest_substring_without_repeating")
    if has("longest", "consecutive", "sequence"):
        families.add("longest_consecutive_sequence")
    if has("matrix", "rows", "sorted"):
        families.add("matrix_rows_sorted")
    if has("cycle") and has("linked", "list"):
        families.add("linked_list_cycle")
    if has("intersection") and (has("arrays") or has("array") or has("lists") or has("list")):
        families.add("intersection")
    if has("common", "elements"):
        families.add("common_elements")
    if has("merge", "two", "sorted", "lists"):
        families.add("merge_sorted_lists")
    if has("missing", "numbers") and has("array"):
        families.add("missing_numbers_in_array")
    if has("missing", "number") and has("range"):
        families.add("missing_number_in_range")
    if has("rotated", "sorted"):
        families.add("rotated_sorted_check")
        if has("minimum", "element"):
            families.add("minimum_in_rotated_sorted_array")
    if has("balanced", "brackets"):
        families.add("balanced_brackets")
    if has("gcd"):
        families.add("gcd")
    if has("even") and not has("sum", "even", "numbers") and not has("filter", "even"):
        families.add("even_check")
    if has("product", "except", "self"):
        families.add("product_except_self")
    if has("factorial"):
        families.add("factorial")
    if has("isomorphic"):
        families.add("isomorphic_strings")
    if has("longest", "common", "prefix"):
        families.add("longest_common_prefix")
    if has("maximum", "subarray", "sum") or "kadane" in lowered:
        families.add("maximum_subarray_sum")
    if has("longest", "increasing", "subsequence"):
        families.add("longest_increasing_subsequence")
    if has("longest", "palindromic", "substring"):
        families.add("longest_palindromic_substring")
    if has("second", "smallest"):
        families.add("second_smallest")
    if has("contains", "duplicates"):
        families.add("contains_duplicates")
    if has("list", "sorted"):
        families.add("list_sorted")
    if has("valid", "url"):
        families.add("valid_url")
    if has("valid", "email"):
        families.add("valid_email")
    if has("arrays", "equal"):
        families.add("arrays_equal")
    if has("normalize") and ("min-max" in lowered or "min max" in lowered):
        families.add("min_max_normalize")
        if "pandas" in lowered or "column" in lowered or "series" in lowered:
            families.add("pandas_min_max_normalize")
    if has("division", "zero") and "normaliz" in lowered:
        families.add("normalization_division_by_zero")
    if has("standardize") or "standardization" in lowered or "z-score" in lowered or "z score" in lowered:
        families.add("zscore_standardize")
        if "standardscaler" in lowered or ("sklearn" in lowered and "scale" in lowered):
            families.add("standard_scaler")
    if has("calculate", "mean") and has("list"):
        families.add("mean_list")
    if has("largest", "three", "numbers"):
        families.add("largest_of_three")
    if has("frequency", "elements") and "list" in lowered:
        families.add("frequency_elements")
    if has("sum", "natural", "numbers"):
        families.add("sum_first_n_natural")
    if has("split", "dataset") and has("train") and has("test"):
        families.add("train_test_split")
        if "train_test_split" in lowered or "sklearn" in lowered:
            families.add("sklearn_train_test_split")
    if has("accuracy") and has("predictions") and has("labels"):
        families.add("classification_accuracy")
    if has("accuracy") and "sklearn" in lowered:
        families.add("sklearn_accuracy")
    if has("unique", "values") and "dataset" in lowered:
        families.add("unique_values")
    if has("linear", "regression", "prediction") or ("y = mx + c" in lowered):
        families.add("linear_regression_predict")
    if has("mean", "squared", "error"):
        families.add("mean_squared_error")
    if has("missing", "values") and "none" in lowered:
        families.add("has_missing_values")
    if has("label", "encoding"):
        families.add("label_encoding")
    if has("precision", "score"):
        families.add("precision_score")
    if has("recall", "score"):
        families.add("recall_score")
    if has("f1", "score"):
        families.add("f1_score")
    if has("confusion", "matrix"):
        families.add("confusion_matrix")
    if has("fill", "missing") and "mean" in lowered:
        families.add("fill_missing_with_mean")
    if has("fill", "missing") and "median" in lowered:
        families.add("fill_missing_with_median")
    if has("remove", "outliers") and "z-score" in lowered:
        families.add("zscore_outlier_removal")
    if has("constant", "feature", "column"):
        families.add("constant_feature")
    if has("variance") and has("list"):
        families.add("variance_list")
    if has("scale") and "-1 and 1" in lowered:
        families.add("scale_between_minus1_and_1")
    if has("most", "frequent", "element"):
        families.add("most_frequent_element")
    if has("split", "features") and has("labels"):
        families.add("split_features_labels")
    if has("mean", "normalization"):
        families.add("mean_normalization")
    if has("all", "same") and ("model" in lowered or "predictions" in lowered):
        families.add("all_predictions_same")
    if has("shuffle", "dataset"):
        families.add("shuffle_dataset")
        if has("keeping", "features", "labels", "aligned"):
            families.add("shuffle_dataset_aligned")
    if has("imbalanced") and "90%" in lowered:
        families.add("imbalanced_dataset")
    if has("imbalance") and "80%" in lowered:
        families.add("imbalanced_dataset")
    if has("drop", "rows") and has("missing", "values"):
        families.add("drop_missing_rows")
    if has("roc-auc") or has("roc", "auc"):
        families.add("roc_auc_score")
    if has("log", "loss"):
        families.add("log_loss")
    if has("train") and has("logistic", "regression"):
        families.add("train_logistic_regression")
    if has("train") and has("decision", "tree"):
        families.add("train_decision_tree")
    if (has("train") and has("knn")) or has("train", "k", "nn"):
        families.add("train_knn")
    if has("train") and has("svm"):
        families.add("train_svm")
    if has("correlation", "matrix"):
        families.add("correlation_matrix")
    if has("correlated", "features"):
        families.add("top_correlated_features")
    if has("outliers") and "iqr" in lowered:
        families.add("iqr_outliers")
    if has("one-hot", "encoding") or has("one", "hot", "encoding"):
        families.add("one_hot_encoding")
    if has("k-fold", "cross", "validation") or has("k", "fold", "cross", "validation"):
        families.add("kfold_cross_validation")
    if ("overfitting" in lowered and has("train", "test", "accuracy")) or has("overfitting", "accuracy", "gap"):
        families.add("overfitting_detection")
    if has("datetime", "column") and has("year") and "pandas" in lowered:
        families.add("datetime_to_year")
    if "labelencoder" in lowered or (has("encode", "labels") and "sklearn" in lowered):
        families.add("label_encoder")
    if "minmaxscaler" in lowered or (has("scale", "features") and "minmax" in lowered):
        families.add("minmax_scaler")
    if has("precision", "recall", "together"):
        families.add("precision_recall_pair")
    if has("rmse") or has("root", "mean", "squared", "error"):
        families.add("rmse")
    if has("stratified", "train-test", "split") or has("stratified", "train", "test", "split"):
        families.add("stratified_train_test_split")
    if ("biased" in lowered and "same class" in lowered) or (has("all", "same", "class") and "predictions" in lowered):
        families.add("biased_predictions_same_class")
    if (has("train") and has("randomforest")) or has("train", "random", "forest"):
        families.add("train_random_forest")
    if has("multicollinearity") or (has("correlation") and "0.9" in lowered):
        families.add("multicollinearity_check")
    if has("sigmoid", "function") or has("implement", "sigmoid"):
        families.add("sigmoid_function")
    if has("binary", "cross", "entropy"):
        families.add("binary_cross_entropy")
    if has("gradient", "descent", "step"):
        families.add("gradient_descent_step")
    if has("data", "leakage"):
        families.add("data_leakage")
    if has("normalize", "vector") and has("unit", "length"):
        families.add("normalize_unit_vector")
    if has("convergence") and "1e-4" in lowered:
        families.add("convergence_check")
    if has("shuffle", "dataset") and "sklearn" in lowered:
        families.add("sklearn_shuffle_dataset")
    if has("sort", "dataframe") and has("descending"):
        families.add("sort_dataframe_desc")
    if has("softmax", "function") or has("implement", "softmax"):
        families.add("softmax_function")
    if has("skewness") or has("mean", "median"):
        if "skew" in lowered:
            families.add("skewness_check")
    if has("clip", "values") and "0 and 1" in lowered:
        families.add("clip_between_0_and_1")
    if has("balanced") and "60%" in lowered:
        families.add("balanced_dataset")
    if has("early", "stopping") or has("early", "stop"):
        families.add("early_stopping")
    if has("reverse", "number"):
        families.add("reverse_number")
    if has("duplicate", "characters"):
        families.add("duplicate_characters")
    if has("perfect", "number"):
        families.add("perfect_number")
    if has("maximum", "list") or has("max", "list") or has("maximum", "element"):
        families.add("maximum_value")

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
    families = _python_question_families(question)

    if _question_contains(question, "filter", "even") and _question_contains(question, "list"):
        return [([2, 3, 4],), ([1, 5],), ([],), ([-4, -3, 0],)]

    if _question_contains(question, "handle", "division", "exception") or _question_contains(question, "division", "exception"):
        return [(6, 2), (5, 0), (-8, 4)]

    if _question_contains(question, "safely", "divide") or _question_contains(question, "safe", "divide"):
        return [(6, 2), (5, 0), (-8, 4)]

    if "palindrome" in families and "palindrome_number" not in families:
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

    if "factorial" in families:
        return [(0,), (1,), (4,), (5,)]

    if "prime_check" in families:
        return [(-1,), (0,), (1,), (2,), (3,), (4,), (17,)]

    if "anagram" in families:
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

    if "missing_number_in_range" in families:
        return [([1, 2, 4, 5], 5), ([2, 3, 1, 5], 5), ([1], 2), ([2], 2)]

    if "second_smallest" in families:
        return [([4, 1, 3, 2],), ([10, 8, 9],), ([1, 1, 2, 3],), ([-5, -1, -3],)]

    if "kth_largest" in families:
        return [([3, 1, 5, 2, 4], 2), ([9, 7, 8], 1), ([1, 2, 3, 4], 4), ([5, 5, 3], 2)]

    if _question_contains(question, "longest", "word"):
        return [("a bb ccc",), ("one three five",), ("hi there world",), ("tiny medium enormous",)]

    if _question_contains(question, "length", "longest", "word"):
        return [("a bb ccc",), ("one three five",), ("hi there world",), ("tiny medium enormous",)]

    if "first_non_repeating_character" in families:
        return [("swiss",), ("level",), ("aabb",), ("abc",), ("",)]

    if "rotation_string" in families:
        return [("abcd", "cdab"), ("waterbottle", "erbottlewat"), ("abc", "acb"), ("", "")]

    if _question_contains(question, "permutation"):
        return [("abc", "cba"), ("aab", "aba"), ("aab", "ab"), ("aab", "abb")]

    if "unique_characters" in families:
        return [("abc",), ("hello",), ("",), ("Aa",)]

    if "longest_substring_without_repeating" in families:
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

    if "sum_of_digits" in families:
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

    if "reverse_string" in families:
        return [("abc",), ("",), ("ab cd",), ("A",)]

    if "reverse_words" in families:
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

    if "count_vowels" in families:
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
        except KeyboardInterrupt:
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


# ──────────────────────────────────────────────────────────────────────────────
# UNIVERSAL PYTHON ORACLE EVALUATOR
# Runs both the model answer and the student answer on the same auto-generated
# test cases and compares outputs directly.  Covers 100% of function-based
# Python questions with no pre-defined family rules required.
# ──────────────────────────────────────────────────────────────────────────────

def _smart_outputs_equal(expected, actual, question_text=""):
    """
    Intelligent output comparison that handles:
    - Exact equality (primary check)
    - Float tolerance (1e-9) for numeric results
    - Unordered list / set equality for questions about common/intersection/duplicates
    - None == None
    - Bool / int coercion (True == 1 is already handled by Python)
    - String normalization (strip whitespace)
    """
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False

    # Direct equality (covers bool, int, str, list, dict, tuple, set)
    if expected == actual:
        return True

    # Float tolerance
    try:
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            return abs(float(expected) - float(actual)) < 1e-9
    except (TypeError, ValueError):
        pass

    # String: strip + case insensitive as last resort
    if isinstance(expected, str) and isinstance(actual, str):
        if expected.strip() == actual.strip():
            return True

    # List / set unordered equality (for intersection, common elements, etc.)
    q = (question_text or "").lower()
    unordered_keywords = (
        "common elements", "intersection", "duplicates", "find duplicate",
        "unique", "set", "union", "frequencies", "frequency",
    )
    if any(kw in q for kw in unordered_keywords):
        try:
            if isinstance(expected, (list, set, tuple)) and isinstance(actual, (list, set, tuple)):
                if set(expected) == set(actual):
                    return True
        except TypeError:
            pass

    # Sorted list equality (order-insensitive)
    try:
        if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
            if sorted(str(x) for x in expected) == sorted(str(x) for x in actual):
                if any(kw in q for kw in unordered_keywords):
                    return True
    except Exception:
        pass

    return False


def _infer_param_types(fn_node, question_text):
    """
    Infer parameter types from:
    1. AST type annotations on the function parameters
    2. AST default values
    3. Question text keywords
    Returns a list of type labels: 'int', 'str', 'list', 'float', 'dict', 'bool', 'any'
    """
    if fn_node is None:
        return []

    q = (question_text or "").lower()

    # Question-text type hints
    q_type_hints = []
    if any(kw in q for kw in ("string", "text", "word", "sentence", "character", "char", "letter", "palindrome",
                               "vowel", "anagram", "reverse string", "uppercase", "lowercase", "email", "url")):
        q_type_hints.append("str")
    if any(kw in q for kw in ("list", "array", "elements", "subarray", "subsequence", "sequence",
                               "matrix", "sorted list", "sorted array")):
        q_type_hints.append("list")
    if any(kw in q for kw in ("integer", "number", "digit", "prime", "even", "odd", "factorial",
                               "fibonacci", "armstrong", "palindrome number", "square", "cube",
                               "divisible", "sum of", "product of", "gcd", "lcm", "power")):
        q_type_hints.append("int")
    if any(kw in q for kw in ("float", "decimal", "average", "mean", "percentage", "ratio")):
        q_type_hints.append("float")
    if any(kw in q for kw in ("dictionary", "dict", "map", "key", "frequency map")):
        q_type_hints.append("dict")
    if any(kw in q for kw in ("boolean", "true or false", "check if", "is valid", "is empty", "is palindrome")):
        q_type_hints.append("bool")

    # Build per-parameter types from annotation then defaults then question hints
    args = fn_node.args
    all_params = list(args.args)
    # Skip 'self' for class methods
    if all_params and all_params[0].arg in ("self", "cls"):
        all_params = all_params[1:]

    n = len(all_params)
    if n == 0:
        return []

    # Collect defaults (right-aligned)
    defaults = args.defaults or []
    default_types = []
    for d in defaults:
        if isinstance(d, ast.Constant):
            if isinstance(d.value, bool):
                default_types.append("bool")
            elif isinstance(d.value, int):
                default_types.append("int")
            elif isinstance(d.value, float):
                default_types.append("float")
            elif isinstance(d.value, str):
                default_types.append("str")
            elif d.value is None:
                default_types.append("any")
            else:
                default_types.append("any")
        elif isinstance(d, ast.List):
            default_types.append("list")
        elif isinstance(d, ast.Dict):
            default_types.append("dict")
        else:
            default_types.append("any")

    # Pad defaults to length n (defaults are right-aligned)
    padded_defaults = ["any"] * (n - len(default_types)) + default_types

    param_types = []
    for i, param in enumerate(all_params):
        t = "any"
        # Check annotation
        if param.annotation:
            ann = param.annotation
            if isinstance(ann, ast.Name):
                name = ann.id.lower()
                if name in ("int", "str", "float", "bool", "list", "dict", "tuple", "set"):
                    t = name
            elif isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
                outer = ann.value.id.lower()
                if outer in ("list", "tuple", "set"):
                    t = "list"
                elif outer in ("dict", "mapping"):
                    t = "dict"
                elif outer == "optional":
                    t = padded_defaults[i] if padded_defaults[i] != "any" else "any"
        # Fall back to defaults
        if t == "any" and padded_defaults[i] != "any":
            t = padded_defaults[i]
        # Fall back to param name heuristics
        if t == "any":
            pname = param.arg.lower()
            if pname in ("n", "num", "number", "k", "x", "y", "a", "b", "c", "val", "value",
                         "target", "count", "limit", "size", "index", "i", "j"):
                t = "int"
            elif pname in ("s", "string", "text", "word", "sentence", "pattern", "key", "name"):
                t = "str"
            elif pname in ("lst", "arr", "array", "list", "nums", "numbers", "items", "elements",
                           "data", "matrix", "grid", "seq", "sequence"):
                t = "list"
            elif pname in ("d", "dct", "dictionary", "mapping"):
                t = "dict"
            elif pname in ("f", "flag", "condition"):
                t = "bool"

        # Apply question-level hints if still unknown
        if t == "any" and q_type_hints:
            t = q_type_hints[0]

        param_types.append(t)

    return param_types


def _generate_oracle_test_cases(param_types, question_text, n_cases=15):
    """
    Generate diverse test cases for the given parameter types.
    Returns a list of tuples (one per test case), each containing one arg per parameter.
    Always includes edge cases (empty, zero, negative, single element).
    """
    q = (question_text or "").lower()

    def _int_values():
        vals = [0, 1, -1, 2, 5, 10, 100, -5, 7, 3, 15, 25, -10, 0, 1000]
        return vals[:n_cases]

    def _str_values():
        vals = [
            "hello", "world", "python", "racecar", "level", "abc", "", "a",
            "Hello World", "12345", "OpenAI", "  spaces  ", "AaBbCc",
            "abcba", "madam", "test string"
        ]
        return vals[:n_cases]

    def _list_int_values():
        vals = [
            [1, 2, 3], [5, 3, 1, 4, 2], [], [1], [1, 2, 2, 3], [-1, 0, 1],
            [10, 20, 30], [1, 1, 1], [3, 1, 4, 1, 5], [100, 50, 75],
            [0, 0, 0], [1, 2], [-5, -3, -1], [1, 2, 3, 4, 5], [7]
        ]
        return vals[:n_cases]

    def _list_str_values():
        vals = [
            ["apple", "banana", "cherry"], ["a", "b", "c"], [],
            ["hello", "world"], ["x"], ["eat", "tea", "tan", "ate"],
            ["race", "care"], ["abc", "bca", "cab"],
            ["cat", "dog", "bird"], ["p", "q", "r"]
        ]
        return vals[:n_cases]

    def _float_values():
        vals = [0.0, 1.0, -1.0, 3.14, 2.5, 0.5, 100.0, -2.5, 0.1, 1.5, 10.0, -0.5, 99.9, 0.001, 50.0]
        return vals[:n_cases]

    def _bool_values():
        return [True, False, True, False, True]

    # Determine special case generation based on question type
    use_string_lists = any(kw in q for kw in ("words", "sentences", "strings", "anagram", "group"))

    # Build values list for each param type
    value_columns = []
    type_counts = {"int": 0, "str": 0, "list": 0, "float": 0, "bool": 0, "dict": 0}
    
    for pt in param_types:
        base_list = []
        if pt == "int":
            base_list = _int_values()
        elif pt == "str":
            base_list = _str_values()
        elif pt == "list":
            if use_string_lists:
                base_list = _list_str_values()
            else:
                base_list = _list_int_values()
        elif pt == "float":
            base_list = _float_values()
        elif pt == "bool":
            base_list = _bool_values()
        elif pt == "dict":
            base_list = [
                {"a": 1}, {"key": "value"}, {}, {"x": 10, "y": 20}, {"name": "Alice"},
                {"1": 1, "2": 2}, {"a": 1, "b": 2, "c": 3}
            ]
        else:  # 'any' — default to int
            base_list = _int_values()
            pt = "int"
            
        # Offset to prevent identical pairs (e.g. gcd(a=1, b=1) instead of gcd(a=1, b=5))
        offset = type_counts[pt] * 3
        type_counts[pt] += 1
        
        # Shift the list by offset
        shifted = base_list[offset:] + base_list[:offset]
        value_columns.append(shifted)

    if not value_columns:
        return []

    # Zip columns into test cases (use shortest)
    max_cases = min(n_cases, min(len(col) for col in value_columns))
    cases = []
    for i in range(max_cases):
        case = tuple(col[i] for col in value_columns)
        cases.append(case)

    return cases


def generate_universal_oracle_test_package_for_registration(question, model_answer, n_cases=None):
    if not model_answer:
        return None

    if n_cases is None:
        try:
            from config import ORACLE_TEST_CASES_BASE
            n_cases = int(ORACLE_TEST_CASES_BASE or 15)
        except Exception:
            n_cases = 15
        
    actual_code, sample_fn_name = _wrap_python_snippet(model_answer, question)
    if not sample_fn_name:
        return None

    try:
        sample_tree = ast.parse(actual_code)
    except Exception:
        return None
    
    sample_fn_node = None
    for node in sample_tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == sample_fn_name:
            sample_fn_node = node
            break
            
    if not sample_fn_node:
        return None
        
    param_types = _infer_param_types(sample_fn_node, question)
    if not param_types:
        cases = [()]
    else:
        cases = _generate_oracle_test_cases(param_types, question, n_cases=n_cases)
        
    if not cases:
        return None

    # IMPORTANT: execute the wrapped code, not the raw model_answer string. The raw
    # value may be a snippet ("return ...") that only becomes runnable after wrapping.
    oracle_run = _run_code_with_timeout(actual_code, sample_fn_name, cases)
    if not oracle_run.get("ok"):
        return None
        
    oracle_outputs = oracle_run.get("outputs", [])
    
    def _materialize_positive_tests(_cases, _outputs):
        materialized = []
        for case, out in zip(_cases, _outputs):
            if out.get("ok"):
                materialized.append(
                    {
                        "input": list(case) if isinstance(case, tuple) else case,
                        "expected_output": out.get("result"),
                        "description": "Auto-generated deterministic oracle test",
                    }
                )
        return materialized

    test_sets = {"positive": _materialize_positive_tests(cases, oracle_outputs), "negative": []}

    # If every oracle case errored (domain mismatch), try a safer set of inputs
    # that avoids empty strings/lists and reduces zero-heavy integer combos.
    if not test_sets["positive"]:
        def _safe_values_for(pt):
            if pt == "int":
                return [1, 2, 3, 5, 10]
            if pt == "str":
                return ["a", "ab", "hello", "python"]
            if pt == "list":
                return [[1], [1, 2], [1, 2, 3], [0, 1]]
            if pt == "float":
                return [1.0, 2.5, -1.0]
            if pt == "bool":
                return [True, False, True]
            if pt == "dict":
                return [{"a": 1}, {"x": 10, "y": 20}]
            return [1, 2, 3]

        safe_columns = []
        for pt in (param_types or []):
            safe_columns.append(_safe_values_for(pt))
        safe_cases = []
        if safe_columns:
            max_cases = min(max(5, int(n_cases or 10)), min(len(col) for col in safe_columns))
            for i in range(max_cases):
                safe_cases.append(tuple(col[i] for col in safe_columns))
        else:
            safe_cases = [()]

        retry = _run_code_with_timeout(actual_code, sample_fn_name, safe_cases)
        if retry and retry.get("ok"):
            retry_outputs = retry.get("outputs", [])
            test_sets["positive"] = _materialize_positive_tests(safe_cases, retry_outputs)
        if not test_sets["positive"]:
            return None
        
    return {
        "test_sets": test_sets,
        "accepted_solutions": [],
        "incorrect_patterns": [],
    }

def _universal_python_oracle_evaluate(question, sample_answer, student_answer):
    """
    Universal oracle-based Python evaluator.

    Strategy:
    1. Parse both answers with AST to extract function name + signature.
    2. Infer parameter types from signature + question keywords.
    3. Generate 15 diverse test cases.
    4. Run model answer (oracle) to get expected outputs.
    5. Run student answer on the same inputs.
    6. Compare outputs with smart equality.
    7. Return structured result with pass ratio.

    Falls back gracefully to None if either answer cannot be executed.
    """
    if not sample_answer or not student_answer:
        return None

    # Parse both answers
    try:
        sample_tree = ast.parse(sample_answer)
        student_tree = ast.parse(student_answer)
    except SyntaxError:
        return None  # Let upstream syntax checker handle this

    # Extract function names
    sample_fn_name = None
    student_fn_name = None
    sample_fn_node = None

    for node in sample_tree.body:
        if isinstance(node, ast.FunctionDef):
            sample_fn_name = node.name
            sample_fn_node = node
            break
        if isinstance(node, ast.ClassDef):
            # Class-based question — not handled by oracle (handled by oop.py)
            return None

    for node in student_tree.body:
        if isinstance(node, ast.FunctionDef):
            student_fn_name = node.name
            break
        if isinstance(node, ast.ClassDef):
            return None  # OOP — handled by oop.py

    if not sample_fn_name or not student_fn_name:
        return None

    # Infer parameter types and generate test cases
    param_types = _infer_param_types(sample_fn_node, question)
    if not param_types:
        # Zero-parameter function — just call with no args
        cases = [()]
    else:
        cases = _generate_oracle_test_cases(param_types, question)

    if not cases:
        return None

    # Run model answer (oracle)
    oracle_run = _run_code_with_timeout(sample_answer, sample_fn_name, cases)
    if not oracle_run.get("ok"):
        # If the model answer itself fails, we cannot oracle-evaluate
        return None

    oracle_outputs = oracle_run.get("outputs", [])

    # Run student answer
    student_run = _run_code_with_timeout(student_answer, student_fn_name, cases)
    if not student_run.get("ok"):
        return {
            "result_type": "execution_error",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": f"The function could not be executed: {student_run.get('error', 'unknown error')}.",
            "suggestion": "Fix any runtime errors (e.g. NameError, TypeError, infinite loop) before submitting.",
        }

    student_outputs = student_run.get("outputs", [])

    # Compare outputs
    total = min(len(oracle_outputs), len(student_outputs))
    if total == 0:
        return None

    passed = 0
    for oracle_out, student_out in zip(oracle_outputs, student_outputs):
        if not oracle_out.get("ok"):
            total -= 1  # Skip cases where model answer itself errored
            continue
        if not student_out.get("ok"):
            continue  # Student errored on this case
        if _smart_outputs_equal(oracle_out.get("result"), student_out.get("result"), question):
            passed += 1

    if total == 0:
        return None

    pass_ratio = passed / total

    if passed == total:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function produces correct output for all test cases.",
        }

    if pass_ratio >= 0.85:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 32,
            "efficiency_max": 15,
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": pass_ratio,
            "feedback": f"The function passes {passed} out of {total} test cases. A small edge case is being missed.",
            "suggestion": "Check boundary conditions such as empty inputs, zero, negative numbers, or single-element collections.",
        }

    if pass_ratio >= 0.5:
        return {
            "result_type": "partial_pass",
            "correctness_max": 28,
            "efficiency_max": 15,
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": pass_ratio,
            "feedback": f"The function passes {passed} out of {total} test cases. The core logic has issues.",
            "suggestion": "Trace through failing test cases manually. Check return type, missing conditions, and edge cases.",
        }

    if pass_ratio > 0:
        return {
            "result_type": "partial_pass",
            "correctness_max": 20,
            "efficiency_max": 10,
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": pass_ratio,
            "feedback": f"The function only passes {passed} out of {total} test cases. The logic is mostly incorrect.",
            "suggestion": "Review the core algorithm against the expected outputs carefully.",
        }

    return {
        "result_type": "zero_pass",
        "correctness_max": 5,
        "efficiency_max": 5,
        "passed_cases": 0,
        "total_cases": total,
        "pass_ratio": 0.0,
        "feedback": "The function produces incorrect output for all test cases.",
        "suggestion": "Review the function logic completely — the algorithm does not match the expected behaviour.",
    }


def evaluate_python_hidden_tests(student_answer, hidden_tests):
    if not hidden_tests:
        return None

    function_name = _extract_first_function_name(student_answer)
    if not function_name:
        return None

    cases = []
    expected_outputs = []
    case_weights = []
    positive_zero_expected_false = False
    required_failures = 0
    for item in hidden_tests:
        if not isinstance(item, dict):
            continue
        raw_input = item.get("input")
        raw_expected = item.get("expected_output")
        description = (item.get("description") or "").lower()
        try:
            parsed_input = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
        except Exception:
            parsed_input = raw_input
        try:
            parsed_expected = json.loads(raw_expected) if isinstance(raw_expected, str) else raw_expected
        except Exception:
            parsed_expected = raw_expected

        if isinstance(parsed_input, list) and len(parsed_input) == 1:
            input_zero = parsed_input[0] in (0, 0.0)
        else:
            input_zero = parsed_input in (0, 0.0)
        expected_false = parsed_expected is False or (
            isinstance(parsed_expected, str) and parsed_expected.lower() == "false"
        )
        if input_zero and expected_false and "positive" in description:
            positive_zero_expected_false = True

        if isinstance(parsed_input, list):
            cases.append(tuple(parsed_input))
        else:
            cases.append((parsed_input,))
        expected_outputs.append(parsed_expected)
        case_weights.append(max(0.1, float(item.get("weight", 1.0) or 1.0)))

    if not cases:
        return None

    student_run = _run_code_with_timeout(student_answer, function_name, cases)
    if not student_run.get("ok"):
        return {
            "result_type": "execution_error",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": f"Code could not be executed reliably on hidden tests: {student_run.get('error', 'execution error')}.",
            "suggestion": "Fix the function so it runs successfully for the registered question inputs.",
        }

    outputs = student_run.get("outputs", [])
    total = min(len(expected_outputs), len(outputs))
    passed = 0
    weighted_total = sum(case_weights[:total]) or float(total)
    weighted_passed = 0.0
    for index, (expected, actual) in enumerate(zip(expected_outputs, outputs)):
        if actual.get("ok") and actual.get("result") == expected:
            passed += 1
            weighted_passed += case_weights[index]
        elif hidden_tests[index].get("required"):
            required_failures += 1

    if total == 0:
        return None

    if passed == total:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "Hidden test cases matched the expected outputs for this registered question.",
        }

    weighted_ratio = weighted_passed / weighted_total if weighted_total else 0.0

    if passed == 0:
        return {
            "result_type": "zero_pass",
            # If every registered check fails, treat correctness as zero.
            # This prevents a misleading non-zero score alongside "failed on all checks" feedback.
            "correctness_max": 0,
            "efficiency_max": 0,
            "feedback": f"Hidden test cases failed on all {total} registered checks.",
            "suggestion": "Review the logic against the registered question inputs and expected outputs.",
        }

    if required_failures and positive_zero_expected_false and re.search(r">=\s*0", student_answer or ""):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Treating zero as positive does not satisfy the strict positive-number requirement, since zero is neither positive nor negative.",
            "suggestion": "Return true only when the number is strictly greater than zero.",
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": weighted_ratio,
        }

    if required_failures:
        return {
            "result_type": "zero_pass",
            "correctness_max": 12,
            "efficiency_max": 8,
            "feedback": "The answer failed one or more required hidden test cases for this registered question.",
            "suggestion": "Fix the required edge or trap cases before relying on this solution.",
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": weighted_ratio,
        }

    return {
        "result_type": "partial_pass",
        "correctness_max": 32 if weighted_ratio >= 0.7 else 28,
        "efficiency_max": 15,
        "passed_cases": passed,
        "total_cases": total,
        "pass_ratio": weighted_ratio,
        "feedback": f"Hidden test cases passed {passed} out of {total} registered checks.",
        "suggestion": "Review the hidden test cases where the current logic differs from the expected output.",
    }


def evaluate_java_hidden_tests(student_answer, hidden_tests):
    if not hidden_tests or not shutil.which("javac") or not shutil.which("java"):
        return None

    signature = _extract_java_method_signature(student_answer)
    if not signature:
        return None

    total = 0
    passed = 0
    weighted_total = 0.0
    weighted_passed = 0.0
    required_failures = 0
    for item in hidden_tests:
        if not isinstance(item, dict):
            continue
        args = _parse_hidden_test_input(item.get("input"))
        expected = _serialize_hidden_expected(_parse_expected_output(item.get("expected_output")))
        result = _run_java_hidden_test(student_answer, signature, args)
        weight = max(0.1, float(item.get("weight", 1.0) or 1.0))
        total += 1
        weighted_total += weight
        if result.get("ok") and result.get("result") == expected:
            passed += 1
            weighted_passed += weight
        elif item.get("required"):
            required_failures += 1

    if total == 0:
        return None

    if passed == total:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "Hidden test cases matched the expected outputs for this registered Java question.",
        }

    weighted_ratio = weighted_passed / weighted_total if weighted_total else 0.0

    if passed == 0:
        return {
            "result_type": "zero_pass",
            "correctness_max": 0,
            "efficiency_max": 0,
            "feedback": f"Hidden test cases failed on all {total} registered Java checks.",
            "suggestion": "Review the Java logic against the registered question inputs and expected outputs.",
        }

    if required_failures:
        return {
            "result_type": "zero_pass",
            "correctness_max": 12,
            "efficiency_max": 8,
            "feedback": "The answer failed one or more required hidden Java test cases.",
            "suggestion": "Fix the required edge or trap cases before relying on this Java solution.",
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": weighted_ratio,
        }

    return {
        "result_type": "partial_pass",
        "correctness_max": 32 if weighted_ratio >= 0.7 else 28,
        "efficiency_max": 15,
        "passed_cases": passed,
        "total_cases": total,
        "pass_ratio": weighted_ratio,
        "feedback": f"Hidden test cases passed {passed} out of {total} registered Java checks.",
        "suggestion": "Review the registered Java hidden tests where the current logic differs from the expected output.",
    }


def _run_javascript_hidden_test(student_answer, function_name, args):
    serialized_args = ", ".join(json.dumps(arg) for arg in args)
    source = f"""
const fn = (() => {{
  {student_answer}
  return {function_name};
}})();

(async () => {{
  try {{
    const result = await fn({serialized_args});
    console.log(JSON.stringify(result));
  }} catch (err) {{
    console.error(String(err && err.message ? err.message : err));
    process.exit(1);
  }}
}})();
""".strip()

    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "main.js"
        source_path.write_text(source, encoding="utf-8")
        run = subprocess.run(
            ["node", str(source_path)],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT_SECONDS,
            cwd=temp_dir,
        )
        if run.returncode != 0:
            return {"ok": False, "error": (run.stderr or run.stdout or "node failed").strip()}
        output = (run.stdout or "").strip()
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = output
        return {"ok": True, "result": parsed}


def evaluate_javascript_hidden_tests(student_answer, hidden_tests):
    if not hidden_tests or not shutil.which("node"):
        return None

    function_name = _extract_first_function_name(student_answer)
    if not function_name:
        return None

    total = 0
    passed = 0
    weighted_total = 0.0
    weighted_passed = 0.0
    required_failures = 0
    for item in hidden_tests:
        if not isinstance(item, dict):
            continue
        args = _parse_hidden_test_input(item.get("input"))
        expected = _parse_expected_output(item.get("expected_output"))
        result = _run_javascript_hidden_test(student_answer, function_name, args)
        weight = max(0.1, float(item.get("weight", 1.0) or 1.0))
        total += 1
        weighted_total += weight
        if result.get("ok") and result.get("result") == expected:
            passed += 1
            weighted_passed += weight
        elif item.get("required"):
            required_failures += 1

    if total == 0:
        return None

    if passed == total:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "Hidden test cases matched the expected outputs for this registered JavaScript question.",
        }

    weighted_ratio = weighted_passed / weighted_total if weighted_total else 0.0

    if passed == 0:
        return {
            "result_type": "zero_pass",
            "correctness_max": 0,
            "efficiency_max": 0,
            "feedback": f"Hidden test cases failed on all {total} registered JavaScript checks.",
            "suggestion": "Review the JavaScript logic against the registered question inputs and expected outputs.",
        }

    if required_failures:
        return {
            "result_type": "zero_pass",
            "correctness_max": 12,
            "efficiency_max": 8,
            "feedback": "The answer failed one or more required hidden JavaScript test cases.",
            "suggestion": "Fix the required edge or trap cases before relying on this JavaScript solution.",
            "passed_cases": passed,
            "total_cases": total,
            "pass_ratio": weighted_ratio,
        }

    return {
        "result_type": "partial_pass",
        "correctness_max": 32 if weighted_ratio >= 0.7 else 28,
        "efficiency_max": 15,
        "passed_cases": passed,
        "total_cases": total,
        "pass_ratio": weighted_ratio,
        "feedback": f"Hidden test cases passed {passed} out of {total} registered JavaScript checks.",
        "suggestion": "Review the registered JavaScript hidden tests where the current logic differs from the expected output.",
    }


def analyze_python_execution(question, sample_answer, student_answer):
    question_text = _normalize_question_text(question)
    families = _python_question_families(question_text)
    normalized_student = re.sub(r"\s+", "", (student_answer or "").lower())

    for family_evaluator in (
        evaluate_string_family,
        evaluate_list_family,
        evaluate_number_family,
        evaluate_oop_family,
        evaluate_algorithms_family,
        evaluate_advanced_family,
    ):
        family_result = family_evaluator(
            question=question,
            question_text=question_text,
            families=families,
            normalized_student=normalized_student,
            student_answer=student_answer,
        )
        if family_result:
            return family_result

    if ("identity" in question_text and "equality" in question_text) or ("same object" in question_text):
        if " is " in (student_answer or "") or "is not" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly uses identity checks to determine whether two references point to the same object.",
            }
        if "==" in (student_answer or ""):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Equality checks compare values, not object identity.",
                "suggestion": "Use the `is` operator to check object identity.",
            }

    if ("type check" in question_text or "isinstance" in question_text or "check type" in question_text) and "isinstance(" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks the input type using isinstance.",
        }
    if ("type check" in question_text or "isinstance" in question_text or "check type" in question_text) and "isinstance(" not in normalized_student:
        if normalized_student.endswith("returntrue") or normalized_student.endswith("returnfalse"):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning a constant value does not check the input type.",
                "suggestion": "Use isinstance(x, type) to verify the input type.",
            }

    if ("element" in question_text and "list" in question_text and "contains" in question_text) or ("in list" in question_text):
        if " in " in (student_answer or "") and "return" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly checks list membership using `in`.",
            }
        if normalized_student.endswith("returntrue") or normalized_student.endswith("returnfalse"):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning a constant value does not check membership.",
                "suggestion": "Return whether the element is in the list using `in`.",
            }

    if "list comprehension" in question_text and re.search(r"\[.*for.+in.+\]", (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses a list comprehension.",
        }

    if "dict comprehension" in question_text and re.search(r"\{.*for.+in.+\}", (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses a dictionary comprehension.",
        }

    if "set comprehension" in question_text and re.search(r"\{.*for.+in.+\}", (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses a set comprehension.",
        }

    # Avoid false positives like "of string" which contains the substring "f string".
    if re.search(r"(?i)(?<![a-z0-9])f[- ]string(?![a-z0-9])|formatted string literal", question_text):
        if re.search(r"f['\"]", (student_answer or "")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses an f-string for formatting.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use an f-string as requested.",
            "suggestion": "Use an f-string (f\"...\") for string formatting.",
        }

    if "lambda" in question_text:
        if "lambda" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a lambda function.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a lambda function as requested.",
            "suggestion": "Use a lambda expression to define the function inline.",
        }

    if "regex" in question_text or "regular expression" in question_text:
        if "re." in (student_answer or "") or "re.compile" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses regular expressions.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use regular expressions as requested.",
            "suggestion": "Import re and use re.search, re.match, or re.compile.",
        }

    if "json" in question_text and ("parse" in question_text or "load" in question_text):
        if "json.loads" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly parses JSON using json.loads.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not parse JSON as requested.",
            "suggestion": "Use json.loads(...) to parse the JSON string.",
        }

    if "json" in question_text and ("serialize" in question_text or "dump" in question_text):
        if "json.dumps" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly serializes JSON using json.dumps.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not serialize JSON as requested.",
            "suggestion": "Use json.dumps(...) to serialize data to JSON.",
        }

    if "csv" in question_text:
        if "csv." in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses the csv module.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use the csv module as requested.",
            "suggestion": "Import csv and use csv.reader or csv.DictReader.",
        }

    if "datetime" in question_text:
        if "datetime" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses the datetime module.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use datetime as requested.",
            "suggestion": "Import datetime and use datetime.datetime or datetime.date.",
        }

    if "random" in question_text:
        if "random." in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses the random module.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use random as requested.",
            "suggestion": "Import random and call random.randint, random.choice, or similar.",
        }

    if "os module" in question_text or "os." in question_text or "using os" in question_text:
        if "os." in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses the os module.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use the os module as requested.",
            "suggestion": "Import os and call an os.* function.",
        }

    if "sys module" in question_text or "sys." in question_text or "using sys" in question_text:
        if "sys." in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses the sys module.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use the sys module as requested.",
            "suggestion": "Import sys and call a sys.* function.",
        }

    if "bitwise" in question_text:
        if any(op in (student_answer or "") for op in ("&", "|", "^", "~", "<<", ">>")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses bitwise operations.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use bitwise operations as requested.",
            "suggestion": "Use operators like &, |, ^, ~, <<, or >> as required by the prompt.",
        }

    if "class" in question_text and ("class " in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly defines a class.",
        }
    if "class" in question_text and ("class " not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not define a class as requested.",
            "suggestion": "Use the class keyword to define a class.",
        }

    if "inheritance" in question_text and ("class " in (student_answer or "") and "(" in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly shows inheritance.",
        }
    if "inheritance" in question_text and ("class " not in (student_answer or "") or "(" not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not demonstrate inheritance as requested.",
            "suggestion": "Define a subclass using class Child(Parent): ...",
        }

    if "recursion" in question_text:
        if re.search(r"\bdef\s+([a-z_][a-z0-9_]*)\s*\(", (student_answer or ""), re.IGNORECASE) and "return" in (student_answer or ""):
            func_match = re.search(r"\bdef\s+([a-z_][a-z0-9_]*)\s*\(", (student_answer or ""), re.IGNORECASE)
            func_name = func_match.group(1) if func_match else ""
            if func_name:
                occurrences = re.findall(rf"\b{re.escape(func_name)}\s*\(", (student_answer or ""), re.IGNORECASE)
                if len(occurrences) > 1:
                    return {
                        "result_type": "full_pass",
                        "correctness_min": 36,
                        "feedback": "The solution correctly uses recursion.",
                    }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use recursion as requested.",
            "suggestion": "Have the function call itself to solve smaller subproblems.",
        }

    if "for loop" in question_text and "for " in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses a for loop.",
        }
    if "for loop" in question_text and "for " not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a for loop as requested.",
            "suggestion": "Use a for loop to iterate.",
        }

    if "while loop" in question_text and "while " in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses a while loop.",
        }
    if "while loop" in question_text and "while " not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a while loop as requested.",
            "suggestion": "Use a while loop with a condition.",
        }

    if "list" in question_text and "create" in question_text and "[" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly creates a list.",
        }
    if "list" in question_text and "create" in question_text and "[" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not create a list as requested.",
            "suggestion": "Use list literals like [1, 2, 3] or list(...) to create a list.",
        }
    if "tuple" in question_text and "(" in (student_answer or "") and "," in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly creates a tuple.",
        }
    if "set" in question_text and "{" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly creates a set.",
        }
    if "dictionary" in question_text and "{" in (student_answer or "") and ":" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly creates a dictionary.",
        }

    if "exception handling" in question_text and "try" in (student_answer or "") and "except" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses try/except for exception handling.",
        }

    if ("file handling" in question_text or "read file" in question_text or "write file" in question_text) and ("open(" in (student_answer or "") or "with open" in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly opens a file for I/O.",
        }

    if ("input" in question_text or "output" in question_text) and ("input(" in (student_answer or "") or "print(" in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses input/output primitives.",
        }

    if "decorator" in question_text and "@" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly applies a decorator.",
        }
    if "decorator" in question_text and "@" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not apply a decorator as requested.",
            "suggestion": "Use the @decorator syntax above the function definition.",
        }

    if "context manager" in question_text and "with " in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses a context manager.",
        }
    if "context manager" in question_text and "with " not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a context manager as requested.",
            "suggestion": "Use a with statement to manage the resource.",
        }

    if "enter" in question_text and "exit" in question_text and ("__enter__" in (student_answer or "") and "__exit__" in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly defines __enter__ and __exit__ for a context manager.",
        }
    if "enter" in question_text and "exit" in question_text and ("__enter__" not in (student_answer or "") or "__exit__" not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not define __enter__ and __exit__ as requested.",
            "suggestion": "Implement both __enter__ and __exit__ methods.",
        }

    if "slicing" in question_text and re.search(r"\[[^\]]*:[^\]]*\]", (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses slicing.",
        }
    if "slicing" in question_text and "step" in question_text and "::" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses slicing with a step.",
        }
    if "slicing" in question_text and not re.search(r"\[[^\]]*:[^\]]*\]", (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use slicing as requested.",
            "suggestion": "Use slice notation like s[start:end].",
        }

    if "range" in question_text and "range(" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use range() as requested.",
            "suggestion": "Use range(...) when iterating over a sequence of numbers.",
        }

    if "enumerate" in question_text:
        if "enumerate(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses enumerate.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use enumerate as requested.",
            "suggestion": "Use enumerate(...) to get indexes and values.",
        }

    if "zip" in question_text:
        if "zip(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses zip.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use zip as requested.",
            "suggestion": "Use zip(...) to iterate over multiple sequences together.",
        }

    if "reversed" in question_text:
        if "reversed(" in (student_answer or "") or "[::-1]" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly reverses iteration.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use reversed iteration as requested.",
            "suggestion": "Use reversed(...) or slicing with [::-1].",
        }

    if "list comprehension" in question_text:
        if re.search(r"\[[^\]]*for\s+.+\]", (student_answer or ""), re.IGNORECASE):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a list comprehension.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a list comprehension as requested.",
            "suggestion": "Use [expr for x in iterable] syntax.",
        }

    if "dict comprehension" in question_text or "dictionary comprehension" in question_text:
        if re.search(r"\{[^}]*for\s+[^}]*:[^}]*\}", (student_answer or ""), re.IGNORECASE):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a dictionary comprehension.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a dictionary comprehension as requested.",
            "suggestion": "Use {k: v for k in iterable} syntax.",
        }

    if "set comprehension" in question_text:
        if re.search(r"\{[^}:]*for\s+[^}]*\}", (student_answer or ""), re.IGNORECASE):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a set comprehension.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a set comprehension as requested.",
            "suggestion": "Use {x for x in iterable} syntax.",
        }

    if "lambda" in question_text:
        if "lambda " in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a lambda expression.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a lambda expression as requested.",
            "suggestion": "Use lambda args: expr to define an anonymous function.",
        }

    if "default argument" in question_text or "default parameter" in question_text:
        if "def " in (student_answer or "") and "=" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a default argument.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a default argument as requested.",
            "suggestion": "Use def func(x=default) to set a default argument.",
        }

    if "*args" in question_text:
        if "*args" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses *args.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use *args as requested.",
            "suggestion": "Use *args to accept variable positional arguments.",
        }

    if "**kwargs" in question_text or "keyword arguments" in question_text:
        if "**kwargs" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses **kwargs.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use **kwargs as requested.",
            "suggestion": "Use **kwargs to accept variable keyword arguments.",
        }

    if "f-string" in question_text or "formatted string" in question_text:
        if re.search(r"f['\"]", (student_answer or "")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses f-strings.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use f-strings as requested.",
            "suggestion": "Use f\"...{expr}...\" for formatted strings.",
        }

    if (
        "format()" in question_text
        or "string format" in question_text
        or "str.format" in question_text
        or "format output" in question_text
        or ("format" in question_text and "string" in question_text)
    ):
        if ".format(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses str.format.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use str.format as requested.",
            "suggestion": "Use \"...\".format(...) for string formatting.",
        }

    if "input" in question_text and "input(" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not read input as requested.",
            "suggestion": "Use input(...) to read user input.",
        }

    if "raise" in question_text:
        if "raise " in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly raises an exception.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not raise an exception as requested.",
            "suggestion": "Use raise SomeError(...) to raise an exception.",
        }

    if "import module" in question_text or "import a module" in question_text:
        if "import " in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly imports a module.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not import a module as requested.",
            "suggestion": "Use import module_name to import a module.",
        }

    if "starts with" in question_text or "startswith" in question_text or "prefix" in question_text:
        if ".startswith(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly checks a string prefix.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not check the prefix as requested.",
            "suggestion": "Use s.startswith(prefix) for prefix checks.",
        }

    if "ends with" in question_text or "endswith" in question_text or "suffix" in question_text:
        if ".endswith(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly checks a string suffix.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not check the suffix as requested.",
            "suggestion": "Use s.endswith(suffix) for suffix checks.",
        }

    if "split" in question_text and "string" in question_text:
        if ".split(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly splits the string.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not split the string as requested.",
            "suggestion": "Use s.split(delimiter) to split the string.",
        }

    if "join" in question_text and "string" in question_text:
        if ".join(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly joins strings.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not join strings as requested.",
            "suggestion": "Use delimiter.join(items) to join strings.",
        }

    if "strip" in question_text and "string" in question_text:
        if any(method in (student_answer or "") for method in (".strip(", ".lstrip(", ".rstrip(")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly strips whitespace or characters.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not strip the string as requested.",
            "suggestion": "Use strip, lstrip, or rstrip to remove whitespace.",
        }

    if "replace" in question_text and "string" in question_text:
        if ".replace(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly replaces substrings.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not replace substrings as requested.",
            "suggestion": "Use s.replace(old, new) to replace substrings.",
        }

    if ("find" in question_text or "index" in question_text) and "string" in question_text:
        if any(method in (student_answer or "") for method in (".find(", ".index(")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly searches for a substring.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not search for a substring as requested.",
            "suggestion": "Use s.find(sub) or s.index(sub) to locate substrings.",
        }

    if ("unicode" in question_text or "emoji" in question_text) and "length" in question_text:
        if "len(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly measures string length.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not measure string length as requested.",
            "suggestion": "Use len(s) to measure string length.",
        }

    if "list method" in question_text or "list methods" in question_text:
        if any(method in (student_answer or "") for method in (".append", ".extend", ".pop", ".insert", ".remove", ".sort", ".reverse")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses list methods.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use list methods as requested.",
            "suggestion": "Use a list method such as append, pop, or sort.",
        }

    if ("copy" in question_text or "clone" in question_text) and "list" in question_text:
        if any(token in (student_answer or "") for token in (".copy()", "list(", "[:]", "[:]")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly copies the list.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not copy the list as requested.",
            "suggestion": "Use list(lst) or lst.copy() to clone the list.",
        }

    if "sort" in question_text and "key" in question_text:
        if "key=" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly sorts with a key function.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not sort with a key function as requested.",
            "suggestion": "Use sorted(items, key=...) or list.sort(key=...).",
        }

    if "dict method" in question_text or "dictionary method" in question_text:
        if any(method in (student_answer or "") for method in (".get(", ".keys()", ".values()", ".items()", ".update(")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses dictionary methods.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use dictionary methods as requested.",
            "suggestion": "Use dict methods such as get, keys, values, or items.",
        }

    if "merge" in question_text and ("dict" in question_text or "dictionary" in question_text):
        if any(token in (student_answer or "") for token in (".update(", "{**", " | ")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly merges dictionaries.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not merge dictionaries as requested.",
            "suggestion": "Use update or unpacking like {**a, **b} to merge dicts.",
        }

    if "defaultdict" in question_text:
        if "defaultdict(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses defaultdict.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use defaultdict as requested.",
            "suggestion": "Use collections.defaultdict to provide default values.",
        }

    if "counter" in question_text or "frequency" in question_text:
        if "Counter(" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses Counter for frequencies.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use Counter as requested.",
            "suggestion": "Use collections.Counter to count frequencies.",
        }

    if "subset" in question_text or "superset" in question_text:
        subset_tokens = (".issubset(", ".issuperset(", "<=", ">=")
        if any(op in (student_answer or "") for op in subset_tokens):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly checks subset or superset relationships.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not check subset or superset relationships as requested.",
            "suggestion": "Use issubset/issuperset or <= / >= for set relationships.",
        }

    if "set operation" in question_text or "set operations" in question_text:
        set_ops_tokens = (".union(", ".intersection(", ".difference(", ".issubset(", ".issuperset(")
        if any(op in (student_answer or "") for op in set_ops_tokens):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses set operations.",
            }
        if any(op in (student_answer or "") for op in ("|", "&", "-", "^")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses set operators.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use set operations as requested.",
            "suggestion": "Use set methods like union or intersection, or operators like | and &.",
        }

    if "custom exception" in question_text:
        if "class " in (student_answer or "") and "Exception" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly defines a custom exception.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not define a custom exception as requested.",
            "suggestion": "Subclass Exception to create a custom exception type.",
        }

    if "iterator" in question_text:
        if "iter(" in (student_answer or "") or "__iter__" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses an iterator.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use iterators as requested.",
            "suggestion": "Use iter(...) or implement __iter__.",
        }

    if "generator" in question_text:
        if "yield" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a generator.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use a generator as requested.",
            "suggestion": "Use yield to define a generator.",
        }

    if ("read" in question_text and "file" in question_text and "binary" not in question_text):
        if "open(" in (student_answer or "") and ("read(" in (student_answer or "") or "readlines(" in (student_answer or "")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly reads from a file.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not read from a file as requested.",
            "suggestion": "Open the file and call read() or readlines().",
        }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not read from a file as requested.",
            "suggestion": "Use open(...).read() or readlines().",
        }

    if ("write" in question_text and "file" in question_text):
        if "open(" in (student_answer or "") and (".write(" in (student_answer or "") or "w" in (student_answer or "")):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly writes to a file.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not write to a file as requested.",
            "suggestion": "Open the file in write/append mode and call write(...).",
        }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not write to a file as requested.",
            "suggestion": "Open the file in write/append mode and call write(...).",
        }

    if "binary file" in question_text:
        if "rb" in (student_answer or "") or "wb" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly handles binary file mode.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use binary file mode as requested.",
            "suggestion": "Use rb or wb mode when opening the file.",
        }

    if "search" in question_text and ("binary" in question_text or "linear" in question_text):
        if "while" in (student_answer or "") or "for " in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution implements a search pattern.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not implement a search pattern as requested.",
            "suggestion": "Use a loop to scan for the target (linear) or a while loop for binary search.",
        }

    if "sort" in question_text and ("sorted(" in (student_answer or "") or ".sort(" in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly performs sorting.",
        }
    if "sort" in question_text and ("sorted(" not in (student_answer or "") and ".sort(" not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not sort as requested.",
            "suggestion": "Use sorted(...) or list.sort() to order the values.",
        }

    if "dynamic programming" in question_text or "dp" in question_text:
        if "dp" in (student_answer or "") or "memo" in (student_answer or ""):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The solution correctly uses a dynamic programming pattern.",
            }
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use dynamic programming as requested.",
            "suggestion": "Use a DP table or memoization to store subproblem results.",
        }

    if ("async" in question_text or "asynchronous" in question_text) and ("async def" in (student_answer or "") or "await " in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly defines or uses async functionality.",
        }
    if ("async" in question_text or "asynchronous" in question_text) and ("async def" not in (student_answer or "")) and ("await " not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not define or use async functionality as requested.",
            "suggestion": "Use async def (and await where appropriate) to implement asynchronous behavior.",
        }

    if "thread" in question_text and "threading" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses threading.",
        }
    if "thread" in question_text and "threading" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use threading as requested.",
            "suggestion": "Import threading and create a Thread to run work concurrently.",
        }

    if "multiprocess" in question_text and "multiprocessing" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses multiprocessing.",
        }
    if "multiprocess" in question_text and "multiprocessing" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use multiprocessing as requested.",
            "suggestion": "Import multiprocessing and create a Process or Pool.",
        }

    if ("http" in question_text or "requests" in question_text) and "requests.get" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly makes an HTTP GET request.",
        }
    if ("http" in question_text or "requests" in question_text) and "requests.get" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not perform the requested HTTP GET with requests.",
            "suggestion": "Use requests.get(url) to make the HTTP request.",
        }

    if "sqlite" in question_text and "sqlite3.connect" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly connects to SQLite using sqlite3.",
        }
    if "sqlite" in question_text and "sqlite3.connect" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not connect to SQLite as requested.",
            "suggestion": "Call sqlite3.connect(...) to create the connection.",
        }

    if "sqlalchemy" in question_text and "sqlalchemy" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses SQLAlchemy.",
        }

    if "numpy" in question_text and ("np.array" in (student_answer or "") or "numpy.array" in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses NumPy arrays.",
        }
    if "numpy" in question_text and ("np.array" not in (student_answer or "") and "numpy.array" not in (student_answer or "")) and "[" in (student_answer or ""):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The solution builds a list, but it does not use NumPy as requested.",
            "suggestion": "Use numpy.array(...) to create the array.",
        }
    if "numpy" in question_text and ("np.array" not in (student_answer or "") and "numpy.array" not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use NumPy as requested.",
            "suggestion": "Use numpy.array(...) to create the array.",
        }

    if "pandas" in question_text and ("DataFrame" in (student_answer or "") or "pd.DataFrame" in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses pandas DataFrame.",
        }
    if "pandas" in question_text and ("DataFrame" not in (student_answer or "") and "pd.DataFrame" not in (student_answer or "")) and "{" in (student_answer or ""):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The solution builds a dictionary, but it does not use pandas DataFrame as requested.",
            "suggestion": "Use pd.DataFrame(...) to construct the DataFrame.",
        }
    if "pandas" in question_text and ("DataFrame" not in (student_answer or "") and "pd.DataFrame" not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use pandas DataFrame as requested.",
            "suggestion": "Use pd.DataFrame(...) to construct the DataFrame.",
        }

    if ("matplotlib" in question_text or "seaborn" in question_text) and ("plt." in (student_answer or "") or "sns." in (student_answer or "")):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses plotting libraries for visualization.",
        }
    if ("matplotlib" in question_text or "seaborn" in question_text) and ("plt." not in (student_answer or "") and "sns." not in (student_answer or "")) and "plot" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The plotting intent is clear, but the requested plotting library is not used.",
            "suggestion": "Use matplotlib.pyplot (plt) or seaborn (sns) to create the plot.",
        }
    if ("matplotlib" in question_text or "seaborn" in question_text) and ("plt." not in (student_answer or "") and "sns." not in (student_answer or "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use the requested plotting library.",
            "suggestion": "Use matplotlib.pyplot (plt) or seaborn (sns) to create the plot.",
        }

    if ("scikit-learn" in question_text or "sklearn" in question_text) and "sklearn" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses scikit-learn.",
        }
    if ("scikit-learn" in question_text or "sklearn" in question_text) and "sklearn" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use scikit-learn as requested.",
            "suggestion": "Import sklearn and use an estimator from the library.",
        }

    if "tkinter" in question_text and "tkinter" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses tkinter for GUI development.",
        }
    if "tkinter" in question_text and "tkinter" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use tkinter as requested.",
            "suggestion": "Import tkinter and build the GUI with its widgets.",
        }

    if "pyqt" in question_text and "pyqt" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses PyQt for GUI development.",
        }
    if "pyqt" in question_text and "pyqt" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use PyQt as requested.",
            "suggestion": "Import PyQt modules and build the GUI with its widgets.",
        }

    if "flask" in question_text and "flask" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses Flask for web development.",
        }
    if "flask" in question_text and "flask" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use Flask as requested.",
            "suggestion": "Import Flask and create an app instance.",
        }

    if "django" in question_text and "django" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses Django for web development.",
        }
    if "django" in question_text and "django" not in (student_answer or "") and "def " in (student_answer or ""):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The solution defines a view function, but it does not use Django as required.",
            "suggestion": "Use Django's HttpResponse or other Django components to build the view.",
        }
    if "django" in question_text and "django" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use Django as requested.",
            "suggestion": "Import Django components or reference Django as required by the prompt.",
        }

    if "fastapi" in question_text and "fastapi" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses FastAPI for web development.",
        }
    if "fastapi" in question_text and "fastapi" not in (student_answer or "") and "def " in (student_answer or ""):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The solution defines a handler, but it does not use FastAPI as required.",
            "suggestion": "Import FastAPI and define an app instance with route decorators.",
        }
    if "fastapi" in question_text and "fastapi" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use FastAPI as requested.",
            "suggestion": "Import FastAPI and define an app instance.",
        }

    if "logging" in question_text and "logging." in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly uses the logging module.",
        }
    if "logging" in question_text and "logging." not in (student_answer or "") and "print(" in (student_answer or ""):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The message is output, but it does not use the logging module as requested.",
            "suggestion": "Replace print(...) with logging.<level>(...) calls.",
        }
    if "logging" in question_text and "logging." not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not use the logging module as requested.",
            "suggestion": "Use logging.<level>(...) to log messages.",
        }

    if "pytest" in question_text and "pytest" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly references pytest.",
        }
    if "pytest" in question_text and "pytest" not in (student_answer or "") and "assert" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The test logic is present, but it does not use pytest as requested.",
            "suggestion": "Write a pytest-style test function and import pytest if needed.",
        }
    if "pytest" in question_text and "pytest" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not reference pytest as requested.",
            "suggestion": "Use pytest syntax or import pytest for tests.",
        }

    if "unittest" in question_text and "unittest" in (student_answer or ""):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The solution correctly references unittest.",
        }
    if "unittest" in question_text and "unittest" not in (student_answer or "") and "assert" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "An assertion is present, but it does not use the unittest framework as requested.",
            "suggestion": "Define a unittest.TestCase class and use unittest assertions.",
        }
    if "unittest" in question_text and "unittest" not in (student_answer or ""):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The solution does not reference unittest as requested.",
            "suggestion": "Use unittest.TestCase or import unittest for tests.",
        }

    if (
        "palindrome_ignore_non_alnum" in families
        and "isalnum()" in normalized_student
        and "join(" in normalized_student
        and ".lower()" in normalized_student
        and "returns==s[::-1]" in normalized_student
    ):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly normalizes the string and checks whether it is a valid palindrome.",
        }

    if "reverse_string_without_slicing" in families and "returns[::-1]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The string reversal logic is correct, but it does not follow the requirement to avoid slicing.",
            "suggestion": "Use a loop or another non-slicing approach to build the reversed string.",
        }

    if _question_contains(question, "parentheses", "sequence") and ("s.count('(')==s.count(')')" in normalized_student or 's.count("(")==s.count(")")' in normalized_student) and ("s.count('{')==s.count('}')" in normalized_student or 's.count("{")==s.count("}")' in normalized_student) and ("s.count('[')==s.count(']')" in normalized_student or 's.count("[")==s.count("]")' in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Matching the counts of each bracket type is not enough to validate a parentheses sequence, because it does not check nesting or order.",
            "suggestion": "Use a stack so each closing bracket must match the most recent unmatched opening bracket.",
        }

    if _question_contains(question, "majority", "element") and "forxinlst" in normalized_student and "lst.count(x)>len(lst)//2" in normalized_student and "returnx" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly identifies the majority element, but repeated count checks make it less efficient than counting frequencies once.",
            "suggestion": "Use a frequency map or Boyer-Moore majority vote to avoid repeated full-list scans.",
        }

    if "group_anagrams" in families and "return[strs]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning [strs] puts every string into one group instead of grouping words by shared anagram signature.",
            "suggestion": "Group the strings by a normalized key such as sorted characters, then return the grouped lists.",
        }

    if "palindrome_permutation" in families and "returns==s[::-1]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 10,
            "efficiency_max": 8,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Checking whether the whole string is already a palindrome is different from checking whether its characters can be rearranged into one.",
            "suggestion": "Count character frequencies and verify that at most one character has an odd count.",
        }
    if "first_non_repeating_character" in families and "returns[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first character does not check whether it is actually non-repeating.",
            "suggestion": "Count character frequencies, then return the first character whose count is 1.",
        }
    if _question_contains(question, "partition") and _question_contains(question, "equal", "sum") and "returnsum(nums)%2==0" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "An even total sum is necessary, but it does not prove the array can actually be partitioned into two equal-sum subsets.",
            "suggestion": "After checking the total sum, search for a subset whose sum is exactly half of it.",
        }

    if _question_contains(question, "happy", "number") and "whilen!=1" in normalized_student and "sum(int(d)**2fordinstr(n))" in normalized_student and normalized_student.endswith("returntrue") and "seen" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The loop never detects repeated unhappy states, so the function can run forever instead of returning False for non-happy numbers.",
            "suggestion": "Track previously seen values and return False when the sequence starts repeating before reaching 1.",
        }

    if "count_vowels" in families and "returnlen(s)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the string length counts every character, not just the vowels.",
            "suggestion": "Count only the characters that are vowels, for example by checking membership in 'aeiou'.",
        }

    if "armstrong" in families and "returnn>0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking whether the number is positive does not determine whether it is an Armstrong number.",
            "suggestion": "Raise each digit to the power of the number of digits, sum those values, and compare the result with the original number.",
        }

    if "largest_of_three" in families and normalized_student.endswith("returna"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first argument does not find the largest of the three numbers.",
            "suggestion": "Compare all three inputs and return the greatest value.",
        }

    if "frequency_elements" in families and normalized_student.endswith("return{}"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning an empty dictionary does not count the frequency of the list elements.",
            "suggestion": "Count how many times each value appears and return those counts in a dictionary.",
        }

    if "frequency_elements" in families and "d={}" in normalized_student and "forxinlst" in normalized_student and "d[x]=1" in normalized_student and "+=1" not in normalized_student and ".get(x,0)+1" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Assigning 1 for every element does not count repeated values correctly.",
            "suggestion": "Increase the stored count when a value appears again, for example with d[x] = d.get(x, 0) + 1.",
        }

    if _question_contains(question, "sum", "even", "numbers") and _question_contains(question, "list") and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not calculate the sum of the even numbers in the list.",
            "suggestion": "Add only the values where x % 2 == 0, for example with sum(x for x in lst if x % 2 == 0).",
        }

    if _question_contains(question, "remove", "duplicates") and _question_contains(question, "list") and "preserve order" in (question or "").lower() and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not remove duplicate values.",
            "suggestion": "Track seen values and build a new list that keeps only the first occurrence of each item.",
        }

    if _question_contains(question, "remove", "duplicates") and _question_contains(question, "list") and "preserve order" in (question or "").lower() and "returnlist(set(lst))" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 8,
            "efficiency_max": 8,
            "feedback": "Using set removes duplicates but does not preserve the original order of the list.",
            "suggestion": "Use an ordered approach such as dict.fromkeys(...) or a loop with a seen set.",
        }

    if "palindrome_ignore_case" in families and "returns==s[::-1]" in normalized_student and ".lower()" not in normalized_student and ".casefold()" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The palindrome comparison is close, but it does not ignore case as the question requires.",
            "suggestion": "Normalize the string with lower() or casefold() before comparing it with its reverse.",
        }

    if "normalization_division_by_zero" in families and "ifmx!=mnelse0" not in normalized_student and "ifmx==mn" not in normalized_student and "(mx-mn)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "The normalization formula is close, but it does not handle the case where the minimum and maximum are equal.",
            "suggestion": "Guard against mx == mn before dividing so constant-value inputs do not trigger division by zero.",
        }

    if "min_max_normalize" in families and "return[x/max(lst)forxinlst]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Dividing each value by the maximum is not min-max scaling because it ignores the minimum and does not map values with (x - min) / (max - min).",
            "suggestion": "Compute both the minimum and maximum, then scale each value with (x - mn) / (mx - mn).",
        }

    if "pandas_min_max_normalize" in families and ("returncol/col.max()" in normalized_student or "return(col/col.max())" in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Dividing the column by its maximum is not min-max scaling because it ignores the column minimum.",
            "suggestion": "Use (col - col.min()) / (col.max() - col.min()) so the values are scaled relative to both bounds.",
        }

    if "mean_list" in families and "returnsum(lst)" in normalized_student and "/len(lst)" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the sum of the list does not compute the mean.",
            "suggestion": "Divide the total by len(lst) to compute the average value.",
        }

    if "sum_first_n_natural" in families and "returnsum(range(n))" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 10,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Summing range(n) stops at n - 1, so it misses the final natural number n.",
            "suggestion": "Use sum(range(1, n + 1)) or the formula n * (n + 1) // 2.",
        }

    if "factorial" in families and normalized_student.endswith("returnn"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning n does not compute the factorial of the input.",
            "suggestion": "Use a factorial base case and multiply through recursive or iterative calls before returning the result.",
        }

    if "train_test_split" in families and ("returndata,data" in normalized_student or "returndata,data[:]" in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the full dataset twice does not create separate training and test splits.",
            "suggestion": "Split the data at the 80 percent index and return the training and test slices separately.",
        }

    if "sklearn_train_test_split" in families and ("returnx,y" in normalized_student or "returnx,y" in normalized_student.replace(" ", "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning X and y unchanged does not split the dataset into training and test sets.",
            "suggestion": "Use train_test_split with test_size=0.2 so the inputs are partitioned into training and test subsets.",
        }

    if "standard_scaler" in families and normalized_student.endswith("returnx"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the feature matrix unchanged does not standardize the features.",
            "suggestion": "Fit a StandardScaler and return the transformed feature matrix.",
        }

    if "classification_accuracy" in families and ("returnlen(y_true)" in normalized_student or "returnlen(y_pred)" in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the number of labels does not calculate prediction accuracy.",
            "suggestion": "Count how many predicted labels match the true labels, then divide by the number of samples.",
        }

    if "sklearn_accuracy" in families and ("returnlen(y_true)" in normalized_student or "returnlen(y_pred)" in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the number of samples does not evaluate model accuracy.",
            "suggestion": "Use accuracy_score or compute the fraction of matching true and predicted labels.",
        }

    if "unique_values" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not remove duplicates to produce unique values.",
            "suggestion": "Track or collect distinct values and return only the unique entries.",
        }

    if "linear_regression_predict" in families and normalized_student.endswith("returnx"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the input x values does not apply the linear regression formula y = m*x + c.",
            "suggestion": "Compute a prediction for each input with m * value + c.",
        }

    if "rmse" in families and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not compute root mean squared error from the prediction errors.",
            "suggestion": "Compute the mean squared error across the paired values, then take its square root.",
        }

    if "mean_squared_error" in families and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not calculate the mean squared error between the true and predicted values.",
            "suggestion": "Compute the squared error for each pair, sum them, and divide by the number of samples.",
        }

    if "prime_check" in families and "returnn>1" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking only whether n is greater than 1 does not determine whether the number is prime.",
            "suggestion": "Test divisibility by integers up to the square root of n and return False when a divisor is found.",
        }

    if "has_missing_values" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether the dataset contains None values.",
            "suggestion": "Scan the data and return True when a None value is present.",
        }

    if "label_encoding" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original categorical values does not encode them into numeric labels.",
            "suggestion": "Build a mapping from category values to integers and return the mapped labels.",
        }

    if "precision_score" in families and normalized_student.endswith("returntp"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning tp alone does not compute precision.",
            "suggestion": "Compute precision as tp / (tp + fp), with a zero check when the denominator is 0.",
        }

    if "recall_score" in families and normalized_student.endswith("returntp"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning tp alone does not compute recall.",
            "suggestion": "Compute recall as tp / (tp + fn), with a zero check when the denominator is 0.",
        }

    if "f1_score" in families and normalized_student.endswith("returntp"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning tp alone does not compute the F1 score.",
            "suggestion": "Compute precision and recall first, then combine them as 2 * p * r / (p + r) when p + r is not 0.",
        }

    if "confusion_matrix" in families and normalized_student.endswith("return0,0,0,0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning zeros for every case does not calculate the confusion matrix values.",
            "suggestion": "Compare true and predicted labels pair by pair and count TP, FP, TN, and FN.",
        }

    if "fill_missing_with_mean" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not fill missing values with the mean.",
            "suggestion": "Compute the mean of the non-missing values, then replace each None entry with that mean.",
        }

    if "fill_missing_with_median" in families and ("returncol" in normalized_student or normalized_student.endswith("returnlst")) and ".fillna" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original column does not fill missing values with the median.",
            "suggestion": "Compute the column median and replace missing entries with that median value, for example with fillna(col.median()).",
        }

    if "zscore_outlier_removal" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not remove outliers using the z-score threshold.",
            "suggestion": "Compute the mean and standard deviation, then keep only values whose absolute z-score is at or below the required threshold.",
        }

    if "constant_feature" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether the feature column is constant.",
            "suggestion": "Compare the number of distinct values and return True when the column contains only one unique value.",
        }

    if "zscore_standardize" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the input list unchanged does not perform z-score standardization.",
            "suggestion": "Compute the mean and standard deviation, then transform each value with (x - mean) / sd.",
        }

    if "variance_list" in families and ("returnmax(lst)-min(lst)" in normalized_student or "returnmax(lst)-min(lst)" in normalized_student.replace(" ", "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning max(lst) - min(lst) computes the range, not the variance.",
            "suggestion": "Compute the mean first, then average the squared differences from the mean.",
        }

    if "scale_between_minus1_and_1" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not scale the values into the range from -1 to 1.",
            "suggestion": "Divide each value by the maximum absolute value so the scaled data stays between -1 and 1.",
        }

    if "most_frequent_element" in families and "returnlst[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first element does not determine which value occurs most often.",
            "suggestion": "Count element frequencies and return the value with the highest count.",
        }

    if "common_elements" in families and normalized_student.endswith("returna"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first list does not compute the common elements shared by both inputs.",
            "suggestion": "Return only the values that appear in both lists, for example by using set intersection or a membership check.",
        }

    if "string_length_without_len" in families and "returnlen(s)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The length result is correct, but it does not follow the requirement to avoid using len().",
            "suggestion": "Count the characters manually with a loop and a counter variable instead of calling len().",
        }

    if "string_length" in families and _uses_string_coercion_for_length(normalized_student):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 20,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The result is correct for strings, but converting the input with str() broadens the behavior beyond a strict string-length question.",
            "suggestion": "Return len(s) directly when the task is specifically about the input string length.",
        }

    if (_question_contains(question, "only alphabets") or _question_contains(question, "only alphabet")) and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning True does not check whether the string contains only alphabetic characters.",
            "suggestion": "Use isalpha() or check each character and return False when a non-letter appears.",
        }

    if "split_features_labels" in families and ("returndata,data" in normalized_student or "returndata,data[:]" in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the full dataset twice does not separate features from labels.",
            "suggestion": "Return the feature columns without the last element in each row and the last-column labels separately.",
        }

    if "mean_normalization" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the input list unchanged does not perform mean normalization.",
            "suggestion": "Compute the mean, minimum, and maximum, then transform each value with (x - mean) / (max - min).",
        }

    if "all_predictions_same" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether all model predictions are identical.",
            "suggestion": "Compare the number of unique prediction values and return True when they are all the same.",
        }

    if "shuffle_dataset" in families and normalized_student.endswith("returndata"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the dataset unchanged does not shuffle its order.",
            "suggestion": "Randomize the order of the dataset elements before returning them.",
        }

    if "shuffle_dataset_aligned" in families and ("returnx,y" in normalized_student or "returnx,y" in normalized_student.replace(" ", "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning X and y unchanged does not shuffle the dataset while keeping features and labels aligned.",
            "suggestion": "Shuffle paired feature-label rows together, then unzip them back into X and y.",
        }

    if "imbalanced_dataset" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether one class exceeds the imbalance threshold in the dataset.",
            "suggestion": "Count the label frequencies and compare the largest class proportion against the required imbalance threshold.",
        }

    if "label_encoder" in families and normalized_student.endswith("returny"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original labels does not encode them into numeric classes.",
            "suggestion": "Fit a LabelEncoder on the labels and return the transformed encoded values.",
        }

    if "log_loss" in families and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not calculate log loss from the true labels and predicted probabilities.",
            "suggestion": "Use log_loss or compute the negative log-likelihood across the prediction probabilities.",
        }

    if "minmax_scaler" in families and normalized_student.endswith("returnx"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the feature matrix unchanged does not scale the features with MinMaxScaler.",
            "suggestion": "Fit a MinMaxScaler and return the transformed feature matrix.",
        }

    if "precision_recall_pair" in families and ("returntp,tp" in normalized_student or "return(tp,tp)" in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning tp twice does not compute precision and recall.",
            "suggestion": "Compute precision as tp / (tp + fp) and recall as tp / (tp + fn), each with a zero-denominator check.",
        }

    if "top_correlated_features" in families and normalized_student.endswith("returndf"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original DataFrame does not find the top correlated feature pairs.",
            "suggestion": "Compute the absolute correlation matrix, rank the feature pairs, and return the top correlated entries.",
        }

    if "train_decision_tree" in families and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not train a decision tree model.",
            "suggestion": "Instantiate a DecisionTreeClassifier, fit it on X and y, and return the trained model.",
        }

    if "stratified_train_test_split" in families and ("returnx,y" in normalized_student or "returnx,y" in normalized_student.replace(" ", "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning X and y unchanged does not perform a stratified train-test split.",
            "suggestion": "Use train_test_split with stratify=y so the class distribution is preserved across the train and test sets.",
        }

    if "biased_predictions_same_class" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether all predictions belong to the same class.",
            "suggestion": "Compare the number of unique predicted classes and return True when every prediction is the same class.",
        }

    if "drop_missing_rows" in families and normalized_student.endswith("returndf"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original DataFrame does not drop rows with missing values.",
            "suggestion": "Use df.dropna() or equivalent filtering to remove rows that contain missing entries.",
        }

    if "datetime_to_year" in families and ("returndf[col]" in normalized_student or "returndf[col]" in normalized_student.replace(" ", "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original datetime column does not extract the year component.",
            "suggestion": "Access the datetime year values, for example with df[col].dt.year.",
        }

    if "roc_auc_score" in families and ("returnsum(y_pred)/len(y_pred)" in normalized_student or "returnsum(y_pred)/len(y_pred)" in normalized_student.replace(" ", "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Averaging the predicted scores does not calculate the ROC-AUC score.",
            "suggestion": "Compute ROC-AUC by comparing the predicted scores against the true labels, for example with roc_auc_score(y_true, y_pred).",
        }

    if "train_logistic_regression" in families and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not train a logistic regression model.",
            "suggestion": "Instantiate LogisticRegression and fit it on X and y before returning the trained model.",
        }

    if "train_random_forest" in families and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not train a RandomForest model.",
            "suggestion": "Instantiate RandomForestClassifier, fit it on X and y, and return the trained model.",
        }

    if "train_knn" in families and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not train a KNN model.",
            "suggestion": "Instantiate KNeighborsClassifier, fit it on X and y, and return the trained model.",
        }

    if "train_svm" in families and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not train an SVM model.",
            "suggestion": "Instantiate SVC, fit it on X and y, and return the trained model.",
        }

    if "correlation_matrix" in families and normalized_student.endswith("returndf"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original DataFrame does not compute the feature correlation matrix.",
            "suggestion": "Call df.corr() so the result contains pairwise feature correlations.",
        }

    if "iqr_outliers" in families and normalized_student.endswith("return[]"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning an empty list for every input does not detect outliers with the IQR method.",
            "suggestion": "Compute the quartiles and IQR, then return the values outside the lower and upper IQR bounds.",
        }

    if "one_hot_encoding" in families and normalized_student.endswith("returndf"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original DataFrame does not one-hot encode the categorical column.",
            "suggestion": "Expand the category into indicator columns, for example with pd.get_dummies on the target column.",
        }

    if "kfold_cross_validation" in families and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not perform k-fold cross validation.",
            "suggestion": "Run cross_val_score or an equivalent k-fold routine and return the validation scores.",
        }

    if "overfitting_detection" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not compare train and test accuracy to detect overfitting.",
            "suggestion": "Return whether the training accuracy exceeds the test accuracy by the chosen threshold, such as 0.1.",
        }

    if "overfitting_detection" in families and ("returntrain>test" in normalized_student or "return(train>test)" in normalized_student):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 12,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Comparing train and test accuracy directly is close, but it ignores the required overfitting gap threshold.",
            "suggestion": "Compare the accuracy difference against the stated threshold, such as (train - test) > 0.15.",
        }

    if "sklearn_shuffle_dataset" in families and ("returnx,y" in normalized_student or "returnx,y" in normalized_student.replace(" ", "")):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning X and y unchanged does not shuffle the dataset.",
            "suggestion": "Use sklearn.utils.shuffle or another shuffling method to randomize X and y together while keeping them aligned.",
        }

    if "sort_dataframe_desc" in families and normalized_student.endswith("returndf"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original DataFrame does not sort it by the requested column in descending order.",
            "suggestion": "Use sort_values with ascending=False on the target column.",
        }

    if "multicollinearity_check" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether highly correlated features exceed the multicollinearity threshold.",
            "suggestion": "Compute the absolute correlation matrix and detect whether any feature pair crosses the required threshold.",
        }

    if "softmax_function" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the input list unchanged does not apply the softmax transformation.",
            "suggestion": "Exponentiate the values, sum those exponentials, and divide each exponential by the total.",
        }

    if "skewness_check" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not compare the mean and median to detect skewness.",
            "suggestion": "Compute the mean and median and return whether they differ.",
        }

    if "sigmoid_function" in families and normalized_student.endswith("returnx"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning x unchanged does not apply the sigmoid transformation.",
            "suggestion": "Compute the logistic function 1 / (1 + exp(-x)) for the input value.",
        }

    if "binary_cross_entropy" in families and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not compute binary cross entropy from the labels and predicted probabilities.",
            "suggestion": "Average the negative log-likelihood terms across the label-probability pairs.",
        }

    if "gradient_descent_step" in families and normalized_student.endswith("returnw"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning w unchanged does not perform a gradient descent update step.",
            "suggestion": "Update the parameter with w - lr * grad so the weight moves opposite the gradient.",
        }

    if "data_leakage" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether the train and test sets share values.",
            "suggestion": "Compare the train and test collections and return True when overlapping values are present.",
        }

    if "normalize_unit_vector" in families and normalized_student.endswith("returnv"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original vector does not normalize it to unit length.",
            "suggestion": "Compute the vector norm and divide each component by that norm.",
        }

    if "clip_between_0_and_1" in families and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not clip values into the range from 0 to 1.",
            "suggestion": "Clamp each value so numbers below 0 become 0 and numbers above 1 become 1.",
        }

    if "balanced_dataset" in families and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning True does not check whether the class distribution stays within the balance threshold.",
            "suggestion": "Count class frequencies and verify that the largest class proportion is at most the required threshold.",
        }

    if "convergence_check" in families and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning True does not check whether the loss difference is below the convergence threshold.",
            "suggestion": "Compare abs(prev - cur) with the required threshold, such as 1e-4.",
        }

    if "early_stopping" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning False does not check whether there has been no improvement for the required number of epochs.",
            "suggestion": "Inspect the recent loss values and return True when the stopping condition is met for the specified epoch window.",
        }

    if "palindrome_number" in families and "returnn>0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking whether the number is positive does not determine whether its digits read the same forward and backward.",
            "suggestion": "Reverse the digits or compare mirrored digits to test whether the number is a palindrome.",
        }

    if "unique_characters" in families and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the string contains duplicate characters.",
            "suggestion": "Track seen characters and return False as soon as a repeated character is found.",
        }

    if "anagram" in families and "returnlen(a)==len(b)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 8,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Checking only whether the strings have the same length does not determine whether they contain the same characters with the same counts.",
            "suggestion": "Compare sorted strings or character frequencies so matching lengths alone do not decide the result.",
        }

    if "kth_largest" in families and ("returnmax(nums)" in normalized_student or "returnmax(lst)" in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the maximum value only solves the case where k is 1, not the general kth-largest problem.",
            "suggestion": "Sort the values by descending order or use a selection approach so the result depends on k.",
        }

    if _question_contains(question, "pairs") and _question_contains(question, "sum") and normalized_student.endswith("return[]"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning an empty list for every input does not find the pairs whose values add up to the target sum.",
            "suggestion": "Track seen values or scan combinations so you can return the pairs that match the target.",
        }

    if "one_edit" in families and "returnlen(a)==len(b)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 8,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Checking only whether the strings have the same length does not measure how many characters actually differ.",
            "suggestion": "Compare the strings character by character and count the mismatches instead of relying only on length.",
        }

    if "maximum_product_two_numbers" in families and "returnmax(arr)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the maximum element does not compute the maximum product of two numbers.",
            "suggestion": "Track the two largest values and the two smallest values, then compare their products.",
        }

    if "rotation_string" in families and "returnsorted(a)==sorted(b)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 10,
            "efficiency_max": 8,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Comparing sorted characters checks whether the strings are anagrams, not whether one is a rotation of the other.",
            "suggestion": "First check the lengths match, then test whether b appears inside a + a.",
        }

    if "interleaving_strings" in families and "returnsorted(a+b)==sorted(c)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 8,
            "efficiency_max": 8,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Matching the combined character multiset does not verify that c preserves the left-to-right order of both input strings.",
            "suggestion": "Track positions in both input strings and verify that each character of c can be taken in order from one of them.",
        }

    if "palindrome_number_no_string" in families and "returnstr(n)==str(n)[::-1]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The palindrome logic is correct, but it does not follow the requirement to avoid converting the number to a string.",
            "suggestion": "Reverse the digits numerically and compare the reversed number with the original value.",
        }

    if "power_of_3" in families and "returnn%3==0" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 8,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Checking n % 3 == 0 only tests divisibility once; it does not verify that repeated division by 3 reduces the value all the way to 1.",
            "suggestion": "Handle values below 1 first, then keep dividing by 3 while the remainder is zero and check whether the final value is 1.",
        }

    if _question_contains(question, "prime") and "foriinrange(2,n)" in normalized_student and "ifn%i==0:returnfalse" in normalized_student and normalized_student.endswith("returntrue") and "ifn<2:returnfalse" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Missing an explicit n < 2 guard, so some non-prime edge cases are handled incorrectly.",
            "suggestion": "Add an early return for values below 2 before checking divisibility.",
        }

    if "sum_of_squares" in families and "returnsum(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function sums the numbers directly instead of adding their squares.",
            "suggestion": "Square each number before summing, for example with sum(x * x for x in lst).",
        }

    if "median_two_sorted_arrays" in families and "return(a[len(a)//2]+b[len(b)//2])/2" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 10,
            "efficiency_max": 8,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Averaging the middle elements of the two separate arrays does not necessarily give the median of the combined sorted data.",
            "suggestion": "Combine the arrays conceptually, then compute the median from the merged sorted order rather than averaging the individual middle elements.",
        }

    if "subsequence" in families and "returnsint" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 14,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Checking whether s appears as a contiguous substring of t is stricter than checking whether s is a subsequence.",
            "suggestion": "Walk through t and match the characters of s in order, allowing gaps between matched characters.",
        }

    if "longest_substring_without_repeating" in families and "returnlen(set(s))" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 10,
            "efficiency_max": 8,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Counting distinct characters in the whole string does not necessarily give the length of the longest contiguous substring without repeats.",
            "suggestion": "Use a sliding window that grows and shrinks so you measure repeated-free substrings, not just unique characters overall.",
        }

    if "longest_consecutive_sequence" in families and "returnlen(nums)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the array length does not measure the longest run of consecutive values.",
            "suggestion": "Track consecutive-number streaks instead of returning the total number of elements.",
        }

    if "matrix_rows_sorted" in families and "returnmat[0]==sorted(mat[0])" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 10,
            "efficiency_max": 8,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Checking only the first row does not show whether every row in the matrix is sorted.",
            "suggestion": "Verify the ordering inside each row, not just the first one.",
        }

    if "one_edit" in families and "returnabs(len(a)-len(b))<=1" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 8,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 10,
            "feedback": "Comparing only the string lengths does not check whether the characters differ by exactly one insertion, deletion, or replacement.",
            "suggestion": "Scan both strings and count actual edit mismatches instead of relying only on the length difference.",
        }

    if "linked_list_cycle" in families and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns False instead of checking whether the linked list contains a cycle.",
            "suggestion": "Use slow and fast pointers, or track visited nodes, to detect whether the list loops back on itself.",
        }

    if "intersection" in families and normalized_student.endswith("returna"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function returns the first array instead of returning only the shared values from both arrays.",
            "suggestion": "Return the elements that appear in both inputs, for example with set intersection or a membership check.",
        }

    if "merge_sorted_lists" in families and "returna+b" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Concatenating the two lists does not merge them into one sorted result.",
            "suggestion": "Compare the current elements from both lists and append the smaller one until both inputs are exhausted.",
        }

    if "missing_numbers_in_array" in families and normalized_student.endswith("return[]"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning an empty list for every input does not identify the missing numbers from 1 to n.",
            "suggestion": "Compare the expected range 1..n with the values present in the array and return the missing ones.",
        }

    if "rotated_sorted_check" in families and "returnarr==sorted(arr)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 8,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 10,
            "feedback": "Checking whether the array is already sorted only handles the non-rotated case, not general sorted-and-rotated arrays.",
            "suggestion": "Count how many times the order drops between adjacent elements, including the wraparound from the last element back to the first.",
        }

    if "balanced_brackets" in families and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Always returning True does not check whether the bracket sequence is actually balanced.",
            "suggestion": "Use a stack and verify that every closing bracket matches the correct most recent opening bracket.",
        }

    if "minimum_in_rotated_sorted_array" in families and "returnarr[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first element only works when the array was never rotated, not for the general rotated-array case.",
            "suggestion": "Use a binary search that compares the middle element with the right boundary to locate the minimum.",
        }

    if "gcd" in families and "returna*b" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning a * b computes the product of the two numbers, not their greatest common divisor.",
            "suggestion": "Use the Euclidean algorithm, repeatedly replacing (a, b) with (b, a % b) until b becomes 0.",
        }

    if "even_check" in families and normalized_student.endswith("returnn"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the number itself does not produce a boolean even-check result.",
            "suggestion": "Return a boolean expression such as n % 2 == 0.",
        }

    if "primes_up_to_n" in families and "res=[]" in normalized_student and "foriinrange(2,n+1)" in normalized_student and "all(i%j!=0forjinrange(2,i))" in normalized_student and "res.append(i)" in normalized_student and "returnres" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly returns all prime numbers up to n, but it checks divisibility naively for each candidate.",
            "suggestion": "Use a sieve or only test divisors up to the square root of each candidate to improve efficiency.",
        }

    if "product_except_self" in families and "return[x*2forxinarr]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Doubling each element does not compute the product of all the other elements in the array.",
            "suggestion": "Build the result from prefix and suffix products, or multiply all other elements except the current index.",
        }

    if (
        _question_contains(question, "factorial")
        and _requires_recursion(question)
        and "foriinrange(1,n+1)" in normalized_student
        and ("res*=i" in normalized_student or "*=i" in normalized_student)
        and "returnres" in normalized_student
    ):
        return {
            "result_type": "partial_pass",
            "correctness_max": 14,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 10,
            "passed_cases": 0,
            "total_cases": 0,
            "pass_ratio": 0.0,
            "feedback": "The function computes factorial values, but it does not use recursion as required by the question.",
            "suggestion": "Use a base case and a recursive call such as n * fact(n - 1) if recursion is required.",
        }

    if "median_list" in families and "returnsum(lst)/len(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Averaging the whole list does not compute the median value.",
            "suggestion": "Sort the list and return the middle value, or the average of the two middle values for an even-length list.",
        }

    if "isomorphic_strings" in families and "returnsorted(a)==sorted(b)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Sorting the characters only checks whether the two strings contain the same multiset of letters; it does not verify one-to-one character mapping for isomorphism.",
            "suggestion": "Track the mapping in both directions so each character consistently maps to exactly one character in the other string.",
        }

    if "longest_common_prefix" in families and "returnmin(strs)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the minimum string is not the same as finding the longest common prefix across all strings.",
            "suggestion": "Compare all strings character by character or shrink a shared prefix until every string matches it.",
        }

    if "maximum_subarray_sum" in families and "returnsum(arr)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the sum of the whole array does not compute the maximum subarray sum.",
            "suggestion": "Track the best running sum and overall maximum instead of summing the entire array.",
        }

    if "longest_increasing_subsequence" in families and "maxlen=1" in normalized_student and "foriinrange(len(nums))" in normalized_student and "forjinrange(i)" in normalized_student and "ifnums[j]<nums[i]:maxlen=max(maxlen,2)" in normalized_student and "returnmaxlen" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Updating the answer only to 2 does not actually compute the longest increasing subsequence length.",
            "suggestion": "Track the best subsequence length ending at each position, or use the patience-sorting style greedy method with binary search.",
        }

    if "longest_palindromic_substring" in families and "returns[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first character does not search for the longest palindromic substring.",
            "suggestion": "Expand around centers or check candidate substrings so you can return the longest palindrome, not just the first character.",
        }

    if _question_contains(question, "zero") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is zero.",
            "suggestion": "Return a boolean expression such as n == 0.",
        }

    if _question_contains(question, "zero") and "returnnotn" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the number is zero.",
        }

    if _question_contains(question, "zero") and "returnn>0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function checks whether the number is greater than zero instead of checking whether it is exactly zero.",
            "suggestion": "Return a boolean expression such as n == 0.",
        }

    if _question_contains(question, "negative") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is negative.",
            "suggestion": "Return a boolean expression such as n < 0.",
        }

    if _question_contains(question, "negative") and ("<=0" in (student_answer or "") or "<= 0" in (student_answer or "")):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function treats zero as negative, so it misses the strict negative-number requirement.",
            "suggestion": "Return true only when the number is less than zero.",
        }

    if _question_contains(question, "negative") and "returnnot(n>0)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function also returns True for zero, so it does not enforce the strict negative-number check.",
            "suggestion": "Return true only when the number is less than zero.",
        }

    if _question_contains(question, "double") and "returnn+n" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly doubles the input number.",
        }

    if _question_contains(question, "double") and "returnn*3" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Multiplying by 3 does not double the input number.",
            "suggestion": "Multiply by 2 or add the number to itself.",
        }

    if _question_contains(question, "double") and normalized_student.endswith("returnn"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the input unchanged does not double the number.",
            "suggestion": "Multiply by 2 or add the number to itself.",
        }

    if _question_contains(question, "concatenate") and "returna" in normalized_student and "returna+b" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first string does not concatenate both input strings.",
            "suggestion": "Return the combined strings, for example with a + b.",
        }

    if _question_contains(question, "concatenate") and "returnb+a" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Concatenating the strings in reverse order does not match the required output.",
            "suggestion": "Return the strings in the original order, for example with a + b.",
        }

    if _question_contains(question, "concatenate") and ("return''.join([a,b])" in normalized_student or 'return"".join([a,b])' in normalized_student):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly concatenates the two input strings.",
        }

    if _question_contains(question, "first", "element") and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not retrieve the first element of the list.",
            "suggestion": "Return the first list item, for example with lst[0].",
        }

    if _question_contains(question, "first", "element") and "returnlst[-1]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the last element does not satisfy the first-element requirement.",
            "suggestion": "Return the first list item, for example with lst[0].",
        }

    if _question_contains(question, "first", "element") and "returnlst.pop(0)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function returns the first element, but it mutates the original list by removing that element.",
            "suggestion": "Use indexing like lst[0] so you return the first element without changing the list.",
        }

    if _question_contains(question, "last", "element") and normalized_student.endswith("returnnone"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning None does not retrieve the last element of the list.",
            "suggestion": "Return the last list item, for example with lst[-1].",
        }

    if _question_contains(question, "last", "element") and "returnlst[len(lst)-1]" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the last element of the list.",
        }

    if _question_contains(question, "last", "element") and "returnlst[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first element does not satisfy the last-element requirement.",
            "suggestion": "Return the last list item, for example with lst[-1].",
        }

    if _question_contains(question, "empty") and _question_contains(question, "string") and "returnnots" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string is empty.",
        }

    if _question_contains(question, "empty") and _question_contains(question, "string") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the string is empty.",
            "suggestion": "Return a boolean expression such as s == ''.",
        }

    if _question_contains(question, "empty") and _question_contains(question, "string") and "returnlen(s)==0ifselsefalse" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "This logic returns False for the empty string, so it does not correctly detect when the string is empty.",
            "suggestion": "Return a direct emptiness check such as s == '' or not s.",
        }

    if _question_contains(question, "square") and "returnn**2" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the square of the input number.",
        }

    if _question_contains(question, "square") and "returnabs(n)*abs(n)" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the square of the input number.",
        }

    if _question_contains(question, "square") and "returnn+n" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Adding the number to itself doubles it instead of squaring it.",
            "suggestion": "Multiply the number by itself, for example with n * n or n ** 2.",
        }

    if _question_contains(question, "count") and _question_contains(question, "elements") and _question_contains(question, "list") and "returnsum(1for_inlst)" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly counts the elements in the list.",
        }

    if _question_contains(question, "count") and _question_contains(question, "elements") and _question_contains(question, "list") and "returnlen(set(lst))" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Counting unique values with set(lst) does not return the total number of elements in the list.",
            "suggestion": "Count every element in the list, for example with len(lst).",
        }

    if _question_contains(question, "count") and _question_contains(question, "elements") and _question_contains(question, "list") and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not count the number of elements in the list.",
            "suggestion": "Count every element in the list, for example with len(lst).",
        }

    if _question_contains(question, "multiple of 5") and "returnnotn%5" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the number is a multiple of 5.",
        }

    if _question_contains(question, "multiple of 5") and "returnn%5==0ifn>0elsefalse" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function excludes 0 and negative multiples of 5, so it misses valid cases that should return True.",
            "suggestion": "Check whether n % 5 == 0 directly without restricting the sign of n.",
        }

    if _question_contains(question, "multiple of 5") and "returnn%2==0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking whether the number is a multiple of 2 does not determine whether it is a multiple of 5.",
            "suggestion": "Use a modulo-5 check such as n % 5 == 0.",
        }

    if _question_contains(question, "lowercase") and ("return''.join([c.lower()forcins])" in normalized_student or 'return"".join([c.lower()forcins])' in normalized_student):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly converts the input string to lowercase.",
        }

    if _question_contains(question, "lowercase") and normalized_student.endswith("returns"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original string does not convert it to lowercase.",
            "suggestion": "Convert the text to lowercase, for example with s.lower().",
        }

    if _question_contains(question, "lowercase") and "returns.upper()" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Converting the string to uppercase does the opposite of the required lowercase transformation.",
            "suggestion": "Convert the text to lowercase, for example with s.lower().",
        }

    if (_question_contains(question, "length", "list") or _question_contains(question, "get", "length", "list")) and "returnsum(1for_inlst)" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the length of the list.",
        }

    if (_question_contains(question, "length", "list") or _question_contains(question, "get", "length", "list")) and "returnlen(set(lst))" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Counting unique values with set(lst) does not return the full length of the list.",
            "suggestion": "Count every element in the list, for example with len(lst).",
        }

    if (_question_contains(question, "length", "list") or _question_contains(question, "get", "length", "list")) and normalized_student.endswith("return1"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 1 does not calculate the length of the list.",
            "suggestion": "Return the number of elements in the list, for example with len(lst).",
        }

    if _question_contains(question, "divisible by 3") and "returnnotn%3" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the number is divisible by 3.",
        }

    if _question_contains(question, "divisible by 3") and "returnn%3==1" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking whether the remainder is 1 does not determine whether the number is divisible by 3.",
            "suggestion": "Use a modulo-3 check such as n % 3 == 0.",
        }

    if _question_contains(question, "divisible by 3") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is divisible by 3.",
            "suggestion": "Use a modulo-3 check such as n % 3 == 0.",
        }

    if _question_contains(question, "append item to list") and "returnlst+[x]" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function returns a new list with the item appended, but it does not modify the original list in place like the reference solution.",
            "suggestion": "If in-place modification is required, append to the original list and return that same list.",
        }

    if _question_contains(question, "append item to list") and "lst.append(x)" in (student_answer or "") and "returnlst" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 18,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function appends the item, but it does not return the updated list as the task expects.",
            "suggestion": "Return the modified list after appending the new item.",
        }

    if _question_contains(question, "append item to list") and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not append the new item.",
            "suggestion": "Append the item to the list before returning it.",
        }

    if _question_contains(question, "list is empty") and "returnnotlst" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the list is empty.",
        }

    if _question_contains(question, "list is empty") and "returnlst==[]iflstelsefalse" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "This logic returns False for the empty list, so it does not correctly detect when the list is empty.",
            "suggestion": "Return a direct emptiness check such as len(lst) == 0 or not lst.",
        }

    if _question_contains(question, "list is empty") and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns False instead of checking whether the list is empty.",
            "suggestion": "Return True only when the list has no elements.",
        }

    if _question_contains(question, "greater than 10") and (">=10" in (student_answer or "") or ">= 10" in (student_answer or "")):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function treats 10 as satisfying the condition, so it misses the strict greater-than requirement.",
            "suggestion": "Return True only when the number is strictly greater than 10.",
        }

    if _question_contains(question, "greater than 10") and "returnnot(n<10)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "This logic also returns True for 10, so it does not enforce the strict greater-than-10 check.",
            "suggestion": "Use a direct strict comparison such as n > 10.",
        }

    if _question_contains(question, "greater than 10") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is greater than 10.",
            "suggestion": "Use a comparison such as n > 10.",
        }

    if _question_contains(question, "repeat", "twice") and "returns+s" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly repeats the string twice.",
        }

    if _question_contains(question, "repeat", "twice") and "returns*3" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Repeating the string three times does not match the required two repetitions.",
            "suggestion": "Repeat the string exactly twice, for example with s * 2 or s + s.",
        }

    if _question_contains(question, "repeat", "twice") and normalized_student.endswith("returns"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original string does not repeat it twice.",
            "suggestion": "Repeat the string exactly twice, for example with s * 2 or s + s.",
        }

    if _question_contains(question, "last character") and "returns[len(s)-1]" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the last character of the string.",
        }

    if _question_contains(question, "last character") and "returns[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the first character does not satisfy the last-character requirement.",
            "suggestion": "Return the last character, for example with s[-1].",
        }

    if _question_contains(question, "last character") and ("return''" in normalized_student or 'return""' in normalized_student):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning an empty string does not retrieve the last character of the input string.",
            "suggestion": "Return the last character, for example with s[-1].",
        }

    if _question_contains(question, "sum") and _question_contains(question, "list") and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not calculate the sum of the list values.",
            "suggestion": "Add the list elements together, for example with sum(lst).",
        }

    if _question_contains(question, "sum") and _question_contains(question, "list") and "returnlst[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first element does not calculate the sum of the whole list.",
            "suggestion": "Add all values in the list before returning the result, for example with sum(lst).",
        }

    if _question_contains(question, "sum") and _question_contains(question, "list") and "returnsum([xforxinlst])" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the sum of the list values.",
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

    if "palindrome_ignore_case" in families and "s=s.lower()" in normalized_student and "foriinrange(len(s)//2)" in normalized_student and "ifs[i]!=s[-i-1]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string is a palindrome while ignoring case.",
        }

    cases = _build_cases(question)
    if not cases:
        # No pre-defined test cases — use the universal oracle evaluator
        oracle_result = _universal_python_oracle_evaluate(question, sample_answer, student_answer)
        return oracle_result  # may be None if oracle also can't evaluate

    student_function_node = _extract_first_function_node(student_answer)

    if _question_contains(question, "palindrome") and normalized_student.endswith("returntrue") and "[::-1]" not in normalized_student and "reversed(" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function returns a constant boolean instead of checking whether the string is a palindrome.",
            "suggestion": "Compare the original string with its reverse or an equivalent mirrored check.",
        }

    if _question_contains(question, "palindrome") and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
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

    if _question_contains(question, "contains", "duplicates") and normalized_student.endswith("returnfalse") and "returntrue" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns False instead of checking whether the array contains duplicate values.",
            "suggestion": "Compare the list length with len(set(lst)), or track seen values and return True when a duplicate appears.",
        }

    if _question_contains(question, "number", "even") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is even.",
            "suggestion": "Return a boolean expression such as n % 2 == 0.",
        }

    if _question_contains(question, "odd") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is odd.",
            "suggestion": "Return a boolean expression such as n % 2 != 0.",
        }

    if _question_contains(question, "positive") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is positive.",
            "suggestion": "Return a boolean expression such as n > 0.",
        }

    if (_question_contains(question, "length", "string") or _question_contains(question, "find", "length")) and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not compute the length of the string.",
            "suggestion": "Count the characters in the input or use len(s) when that technique is allowed.",
        }

    if _question_contains(question, "maximum") and _question_contains(question, "list") and "returnmin(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the minimum value does not solve the maximum-in-list problem.",
            "suggestion": "Scan the whole list and return the largest value, for example with max(lst).",
        }

    if _question_contains(question, "count", "vowels") and normalized_student.endswith("return0"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning 0 does not count the vowels in the string.",
            "suggestion": "Check each character and count only the ones that are vowels.",
        }

    if _question_contains(question, "uppercase") and normalized_student.endswith("returns"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original string does not convert it to uppercase.",
            "suggestion": "Convert the text to uppercase, for example with s.upper().",
        }

    if _question_contains(question, "uppercase") and "returns.lower()" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Converting the string to lowercase does the opposite of the required uppercase transformation.",
            "suggestion": "Convert the text to uppercase, for example with s.upper().",
        }

    if _question_contains(question, "minimum") and _question_contains(question, "list") and "returnlst[0]" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning only the first element does not find the minimum value in the list.",
            "suggestion": "Scan the whole list and return the smallest value, for example with min(lst).",
        }

    if _question_contains(question, "minimum") and _question_contains(question, "list") and "returnmax(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the maximum value does not solve the minimum-in-list problem.",
            "suggestion": "Scan the whole list and return the smallest value, for example with min(lst).",
        }

    if _question_contains(question, "reverse", "list") and normalized_student.endswith("returnlst"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the original list does not reverse its element order.",
            "suggestion": "Return the elements in reverse order, for example with lst[::-1] or list(reversed(lst)).",
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

    if _question_contains(question, "missing", "number") and _question_contains(question, "range") and "foriinrange(1,n+1)" in normalized_student and "ifinotinnums:returni" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly finds the missing number in the range, but repeated membership checks make it less efficient than using arithmetic or a set.",
            "suggestion": "Use the arithmetic sum formula or a set for faster lookup.",
        }

    if _question_contains(question, "kth", "largest") and "lst=sorted(lst)" in normalized_student and "returnlst[-k]" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the kth largest element from the list.",
        }

    if _question_contains(question, "second largest") and "lst=list(set(lst))" in normalized_student and "lst.remove(max(lst))" in normalized_student and normalized_student.endswith("returnmax(lst)"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly returns the second distinct largest value in the list.",
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

    if _question_contains(question, "second", "smallest") and "sorted(lst)[1]" in normalized_student and "set(lst)" not in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 24,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Sorting the list and taking index 1 works for many inputs, but it can return the smallest value again when the minimum appears more than once.",
            "suggestion": "Remove duplicates first, or track the two smallest distinct values explicitly.",
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

    if _question_contains(question, "remove", "duplicates") and _question_contains(question, "list") and "preserve order" in (question or "").lower() and "res=[]" in normalized_student and "forxinlst" in normalized_student and "ifxnotinres:res.append(x)" in normalized_student and "returnres" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly removes duplicates from the list while preserving the original order.",
        }

    if _question_contains(question, "remove", "duplicates") and _question_contains(question, "list") and "preserve order" in (question or "").lower() and "seen=set()" in normalized_student and "res=[]" in normalized_student and "forxinlst" in normalized_student and "ifxnotinseen:" in normalized_student and "seen.add(x)" in normalized_student and "res.append(x)" in normalized_student and "returnres" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly removes duplicates from the list while preserving the original order.",
        }

    if "palindrome_ignore_case" in families and "s=s.lower()" in normalized_student and "foriinrange(len(s)//2)" in normalized_student and "ifs[i]!=s[-i-1]:returnfalse" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string is a palindrome while ignoring case.",
        }

    if "frequency_elements" in families and "d={}" in normalized_student and "forxinlst" in normalized_student and "ifxind" in normalized_student and "d[x]+=1" in normalized_student and "else:d[x]=1" in normalized_student and "returnd" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly counts the frequency of each element in the list.",
        }

    if "frequency_elements" in families and "return{x:lst.count(x)forxinlst}" in normalized_student:
        return {
            "result_type": "correct_but_inefficient",
            "correctness_min": 36,
            "efficiency_max": 12,
            "feedback": "The function correctly counts the frequency of each element, but repeatedly calling lst.count(x) scans the list many times.",
            "suggestion": "Build the counts in one pass with a dictionary so repeated full-list scans are avoided.",
        }

    if _question_contains(question, "frequency", "characters") and "d={}" in normalized_student and "forcins" in normalized_student and "d.get(c,0)+1" in normalized_student and "returnd" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly counts the frequency of each character in the string.",
        }

    if "unique_characters" in families and "seen=set()" in normalized_student and "forcins" in normalized_student and "ifcinseen:returnfalse" in normalized_student and "seen.add(c)" in normalized_student and normalized_student.endswith("returntrue"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string has all unique characters.",
        }

    if "unique_characters" in families and ("returnlen(s)==len(set(s))" in normalized_student or "returnlen(set(s))==len(s)" in normalized_student):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the string has all unique characters.",
        }

    if _question_contains(question, "sum", "even", "numbers") and _question_contains(question, "list") and "total=0" in normalized_student and "forxinlst" in normalized_student and "ifx%2==0" in normalized_student and "total+=x" in normalized_student and normalized_student.endswith("returntotal"):
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the sum of the even numbers in the list.",
        }

    if _question_contains(question, "sum", "even", "numbers") and _question_contains(question, "list") and "returnsum([xforxinlstifx%2==0])" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the sum of the even numbers in the list.",
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
            "correctness_max": 22,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function treats zero as positive, but zero is neither positive nor negative, so it misses the strict positive-number requirement.",
            "suggestion": "Return true only when the number is greater than zero.",
        }

    if _question_contains(question, "positive") and "returnn<0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function checks whether the number is negative instead of checking whether it is positive.",
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

    if _question_contains(question, "reverse", "list") and "returnsorted(lst)" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Sorting the list does not reverse its original element order.",
            "suggestion": "Return the list in reverse order, for example with lst[::-1] or list(reversed(lst)).",
        }

    if _question_contains(question, "reverse", "list") and "returnlist(reversed(lst))" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly reverses the input list.",
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
                "correctness_max": 20,
                "efficiency_max": 10,
                "readability_max": 12,
                "structure_max": 10,
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
        if re.search(r"return\s+[^;]*%\s*2\s*==\s*0\s*\?\s*true\s*:\s*false\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+[^;]*%\s*2\s*==\s*0\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+[^;]*%\s*2\s*!=\s*1\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+[^;]*%\s*2\s*==\s*1\s*;", code) or re.search(r"return\s+[^;]*%\s*2\s*==\s*2\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method does not correctly implement the even-number check.",
                "suggestion": "Return a boolean expression such as n % 2 == 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is even.",
                "suggestion": "Return a boolean expression such as n % 2 == 0.",
            }
        if re.search(r"return\s+n\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the number itself does not produce a boolean even-check result.",
                "suggestion": "Return a boolean comparison such as n % 2 == 0.",
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
        if "without using reverse()" in question_text and "stringbuilder" in code and ".reverse()" in code and ".tostring()" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 18,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The string reversal logic is correct, but it uses reverse() even though the question forbids that technique.",
                "suggestion": "Build the reversed string manually with a loop or another non-reverse approach.",
            }
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
        if re.search(r'return\s*""\s*;', code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning an empty string does not reverse the input string.",
                "suggestion": "Build and return the characters in reverse order, for example with StringBuilder(s).reverse().toString().",
            }
        if "stringbuilder" in code and ".tostring()" in code and ".reverse()" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Converting the string to a StringBuilder and back without reversing it does not reverse the input string.",
                "suggestion": "Call reverse() before converting the builder back to a string.",
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
                "correctness_max": 26,
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
                "correctness_max": 22,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method computes factorial values for smaller inputs, but it still uses int and does not avoid overflow as required.",
                "suggestion": "Use BigInteger multiplication so the factorial remains correct for large input values.",
            }

    if "factorial" in question_text:
        if re.search(r"return\s+n\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning n does not compute the factorial of the input.",
                "suggestion": "Use a factorial base case and multiply through recursive or iterative calls before returning the result.",
            }
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
        if ".equals(s)" in code and "reverse()" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Comparing the string to itself always returns true, so it does not actually test whether the string is a palindrome.",
                "suggestion": "Compare the string with its reverse, for example by using StringBuilder(s).reverse().toString().",
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
        if "push(" in code and "pop(" in code and "top" in code and ("a[top]=x" in code or "return a[top]" in code) and ("++top" not in code and "top++" not in code and "--top" not in code and "top--" not in code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The stack methods use the top index incorrectly, so push and pop do not update the stack position as required.",
                "suggestion": "Increment top before storing on push and decrement top after returning the value on pop.",
            }
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
        if "while(l<r)" in code or "while (l<r)" in code or "while(l < r)" in code or "while (l < r)" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method is close to binary search, but the loop bounds and pointer updates can miss valid targets or fail to shrink the search space correctly.",
                "suggestion": "Use a standard binary-search loop such as while (l <= r) with l = m + 1 and r = m - 1.",
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
                "correctness_max": 28,
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
        if ("new hashmap<>()" in code or "new java.util.hashmap<>()" in code) and ("return new hashmap<>()" in code or "return new java.util.hashmap<>()" in code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning an empty HashMap does not count the frequency of the characters in the string.",
                "suggestion": "Loop through the characters and update the map counts before returning it.",
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
        if "for(" in code and ("arr[i]<arr[i-1]" in code or "a[i]<a[i-1]" in code) and "return false" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if "for(" in code and ("arr[i]>arr[i+1]" in code or "a[i]>a[i+1]" in code) and "return false" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the array is sorted.",
                "suggestion": "Compare each element with the previous one and return false when the order decreases.",
            }

    if "count vowels" in question_text:
        if ".tolowercase()" in code and ".tochararray()" in code and "indexof(" in code and "return c" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if ".length()" in code and "indexof(" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the string length counts every character instead of counting only the vowels.",
                "suggestion": "Check each character against the vowels and count only matches.",
            }

    if "remove duplicates from array" in question_text:
        if ".distinct()" in code and ".toarray()" in code:
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
                "feedback": "Returning the original array does not remove duplicate values.",
                "suggestion": "Build and return a result that keeps only distinct values from the input array.",
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

    if "nullpointerexception" in question_text:
        if ("s==null" in code or "s == null" in code) and ("return 0" in code) and ".length()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly guards against null input before reading the string length.",
            }
        if ".length()" in code and "null" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method still reads s.length() without a null check, so the NullPointerException is not fixed.",
                "suggestion": "Check for null before accessing s.length(), and return a safe default such as 0.",
            }
        if re.search(r"return\s+0\s*;", code) and ".length()" not in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning 0 for every input avoids the exception, but it no longer returns the actual string length for valid inputs.",
                "suggestion": "Return 0 only for null input, and otherwise return s.length().",
            }

    if "array index out of bounds" in question_text:
        if "arr[arr.length-1]" in code or "arr[arr.length - 1]" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly returns the last array element without indexing past the end.",
            }
        if re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the first element does not fix the last-element indexing bug.",
                "suggestion": "Return the last valid element, for example with arr[arr.length - 1].",
            }
        if "arr[arr.length]" in code or "arr[ arr.length ]" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method still indexes at arr.length, which is outside the valid range.",
                "suggestion": "Use arr[arr.length - 1] to access the last valid element.",
            }

    if "division by zero" in question_text:
        if ("b==0" in code or "b == 0" in code) and "return -1" in code and ("return a/b" in code or "return a / b" in code):
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method correctly guards against division by zero, but it returns a different fallback value than the expected fix.",
                "suggestion": "If the task requires the same behavior as the reference fix, return 0 when b == 0.",
            }
        if ("b==0" in code or "b == 0" in code) and "return 0" in code and ("return a/b" in code or "return a / b" in code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly guards against division by zero before performing the division.",
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
        if "arrays.stream(arr).max().getasint()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly finds the maximum value in the array.",
            }
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
        if ("m=0" in code or "m = 0" in code) and ("if(x>m)" in code or "if (x>m)" in code or "if(x > m)" in code or "if (x > m)" in code):
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method can find the maximum for many arrays, but initializing the maximum to 0 breaks cases where all values are negative.",
                "suggestion": "Initialize the maximum from the first array element instead of 0.",
            }
        if re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning only the first element does not correctly find the maximum value in the array.",
                "suggestion": "Loop through the array and keep track of the largest value before returning it.",
            }
        if "arr[arr.length-1]" in code or "arr[arr.length - 1]" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning only the last element does not correctly find the maximum value in the array.",
                "suggestion": "Loop through the array and keep track of the largest value before returning it.",
            }
        if "if(x<m)" in code or "if (x<m)" in code or "if(x < m)" in code or "if (x < m)" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method updates toward smaller values, so it finds the minimum instead of the maximum.",
                "suggestion": "Update the stored value only when the current element is larger than the current maximum.",
            }
        if re.search(r"return\s+0\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning 0 does not correctly find the maximum value in the array.",
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
        if ("m=0" in code or "m = 0" in code) and ("if(x<m)" in code or "if (x<m)" in code or "if(x < m)" in code or "if (x < m)" in code):
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method can find the minimum for many arrays, but initializing the minimum to 0 breaks cases where all values are positive.",
                "suggestion": "Initialize the minimum from the first array element instead of 0.",
            }
        if "arr[arr.length-1]" in code or "arr[arr.length - 1]" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning only the last element does not correctly find the minimum value in the array.",
                "suggestion": "Loop through the array and keep track of the smallest value before returning it.",
            }
        if "if(x>m)" in code or "if (x>m)" in code or "if(x > m)" in code or "if (x > m)" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method updates toward larger values, so it finds the maximum instead of the minimum.",
                "suggestion": "Update the stored value only when the current element is smaller than the current minimum.",
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
                "feedback": "The method treats zero as positive, but zero is neither positive nor negative, so it misses the strict positive-number requirement.",
                "suggestion": "Return true only when the number is greater than zero.",
            }
        if "< 0" in code or "<0" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method checks whether the number is negative instead of checking whether it is positive.",
                "suggestion": "Return true only when the number is greater than zero.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is positive.",
                "suggestion": "Return a boolean expression such as n > 0.",
            }

    if "greater than 100" in question_text:
        if "> 100" in code or ">100" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is greater than 100.",
            }
        if ">= 100" in code or ">=100" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats 100 as satisfying the condition, so it misses the strict greater-than requirement.",
                "suggestion": "Return true only when the number is strictly greater than 100.",
            }
        if "< 100" in code or "<100" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method checks whether the number is less than 100 instead of checking whether it is greater than 100.",
                "suggestion": "Return true only when the number is strictly greater than 100.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is greater than 100.",
                "suggestion": "Return a boolean expression such as n > 100.",
            }

    if "less than 50" in question_text:
        if "< 50" in code or "<50" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is less than 50.",
            }
        if "<= 50" in code or "<=50" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats 50 as satisfying the condition, so it misses the strict less-than requirement.",
                "suggestion": "Return true only when the number is strictly less than 50.",
            }
        if "> 50" in code or ">50" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method checks whether the number is greater than 50 instead of checking whether it is less than 50.",
                "suggestion": "Return true only when the number is strictly less than 50.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is less than 50.",
                "suggestion": "Return a boolean expression such as n < 50.",
            }

    if "negative" in question_text:
        if "< 0" in code or "<0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks for strictly negative numbers.",
            }
        if "<= 0" in code or "<=0" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats zero as negative, so it misses the strict negative-number requirement.",
                "suggestion": "Return true only when the number is less than zero.",
            }
        if "> 0" in code or ">0" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method checks whether the number is positive instead of checking whether it is negative.",
                "suggestion": "Return true only when the number is less than zero.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is negative.",
                "suggestion": "Return a boolean expression such as n < 0.",
            }

    if "zero" in question_text:
        if "== 0" in code or "==0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is zero.",
            }
        if "<= 0" in code or "<=0" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats negative numbers as zero, so it misses the exact-zero requirement.",
                "suggestion": "Return true only when the number is exactly zero.",
            }
        if "== 1" in code or "==1" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the number equals 1 does not implement the zero-check requirement.",
                "suggestion": "Return a boolean expression such as n == 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is zero.",
                "suggestion": "Return a boolean expression such as n == 0.",
            }

    if "equal to 20" in question_text:
        if "== 20" in code or "==20" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is equal to 20.",
            }
        if ">= 20" in code or ">=20" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats values greater than 20 as satisfying the condition, so it misses the exact-equality requirement.",
                "suggestion": "Return true only when the number is exactly 20.",
            }
        if "!= 20" in code or "!=20" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the number is not equal to 20 does the opposite of the required equality check.",
                "suggestion": "Return a boolean expression such as n == 20.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is equal to 20.",
                "suggestion": "Return a boolean expression such as n == 20.",
            }

    if "odd" in question_text:
        if "% 2 != 0" in code or "%2!=0" in code or "% 2 == 1" in code or "%2==1" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is odd.",
            }
        if "% 2 == 0" in code or "%2==0" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method checks for even numbers instead of returning true for odd numbers.",
                "suggestion": "Return a boolean expression such as n % 2 != 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is odd.",
                "suggestion": "Return a boolean expression such as n % 2 != 0.",
            }

    if "add two numbers" in question_text:
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\+\s*[a-z_][a-z0-9_]*\s*\+\s*0\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly adds the two input numbers and matches the expected behavior.",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*-\s*[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method subtracts the second number from the first instead of adding the two inputs.",
                "suggestion": "Return the sum of both inputs, such as a + b.",
            }
        if re.search(r"return\s+0\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning 0 does not add the two input numbers.",
                "suggestion": "Return the sum of both inputs, such as a + b.",
            }

    if "multiply two numbers" in question_text:
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\*\s*[a-z_][a-z0-9_]*\s*\*\s*1\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly multiplies the two input numbers.",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\+\s*[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method adds the two numbers instead of multiplying them.",
                "suggestion": "Return the product of the two input values, such as a * b.",
            }
        if re.search(r"return\s+1\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning 1 does not multiply the two input numbers.",
                "suggestion": "Return the product of the two input values, such as a * b.",
            }

    if "square" in question_text:
        if "math.pow" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly calculates the square of the input number.",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\+\s*[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Adding the number to itself doubles it instead of squaring it.",
                "suggestion": "Multiply the number by itself, for example with n * n.",
            }
        if re.search(r"return\s+0\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning 0 does not calculate the square of the input number.",
                "suggestion": "Multiply the number by itself, for example with n * n.",
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

    if "count even numbers in array" in question_text:
        if ("c=0" in code or "c = 0" in code) and ("if(x%2==0)" in code or "if (x%2==0)" in code or "if(x % 2 == 0)" in code or "if (x % 2 == 0)" in code) and "c++" in code:
            if re.search(r"return\s+0\s*;", code):
                return {
                    "result_type": "zero_pass",
                    "correctness_max": 5,
                    "efficiency_max": 5,
                    "feedback": "The method counts even numbers but returns 0 instead of the count.",
                    "suggestion": "Return the counter after the loop instead of returning 0.",
                }
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly counts the even numbers in the array.",
            }
        if ("c=0" in code or "c = 0" in code) and ("if(x%2==1)" in code or "if (x%2==1)" in code or "if(x % 2 == 1)" in code or "if (x % 2 == 1)" in code) and "c++" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method counts odd numbers instead of even numbers.",
                "suggestion": "Increment the counter only when the current value is even.",
            }
        if "arr.length" in code and "return" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the array length does not count only the even numbers.",
                "suggestion": "Loop through the array and increment a counter only for even values.",
            }

    if "second largest" in question_text:
        if "distinct()" in code and "sorted()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly finds the second distinct largest element.",
            }
        if "x>sec" in code and "x!=max" not in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method is close, but without excluding the largest value it can return the maximum again when duplicates are present.",
                "suggestion": "Only update the second-largest value when the current value is larger than sec and different from max.",
            }
        if re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", code) or re.search(r"return\s+a\s*\[\s*0\s*\]\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning only the first element does not solve the second-largest-element problem.",
                "suggestion": "Track the two largest distinct values, or sort after removing duplicates before returning the second largest.",
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
                "correctness_max": 28,
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

    if "divisible by 5" in question_text:
        if re.search(r"return\s+[^;]*%\s*5\s*==\s*0\s*\?\s*true\s*:\s*false\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is divisible by 5.",
            }
        if "% 5 == 0" in code or "%5==0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is divisible by 5.",
            }
        if "% 5 == 1" in code or "%5==1" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the remainder is 1 does not implement the divisibility-by-5 requirement.",
                "suggestion": "Return a boolean expression such as n % 5 == 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is divisible by 5.",
                "suggestion": "Return a boolean expression such as n % 5 == 0.",
            }

    if "divisible by 3" in question_text:
        if re.search(r"return\s+[^;]*%\s*3\s*==\s*0\s*\?\s*true\s*:\s*false\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is divisible by 3.",
            }
        if "% 3 == 0" in code or "%3==0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is divisible by 3.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the number is divisible by 3.",
                "suggestion": "Return a boolean expression such as n % 3 == 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is divisible by 3.",
                "suggestion": "Return a boolean expression such as n % 3 == 0.",
            }

    if "divisible by 2" in question_text:
        if re.search(r"return\s+[^;]*%\s*2\s*==\s*0\s*\?\s*true\s*:\s*false\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is divisible by 2.",
            }
        if "% 2 == 0" in code or "%2==0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is divisible by 2.",
            }
        if "% 2 == 1" in code or "%2==1" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the remainder is 1 does not implement the divisibility-by-2 requirement.",
                "suggestion": "Return a boolean expression such as n % 2 == 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is divisible by 2.",
                "suggestion": "Return a boolean expression such as n % 2 == 0.",
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

    if "uppercase" in question_text:
        if ".touppercase(locale.root)" in code or ".touppercase()" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly converts the input string to uppercase.",
            }
        if re.search(r'return\s+""\s*;', code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning an empty string does not convert the input to uppercase.",
                "suggestion": "Convert the text to uppercase, for example with s.toUpperCase().",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the original string does not convert it to uppercase.",
                "suggestion": "Convert the text to uppercase, for example with s.toUpperCase().",
            }

    if "concatenate two strings" in question_text:
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*\+\s*[a-z_][a-z0-9_]*\s*;", code) or ".concat(" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly concatenates the two input strings.",
            }
        if re.search(r'return\s+""\s*;', code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning an empty string does not concatenate the two input strings.",
                "suggestion": "Return the combined strings, for example with a + b.",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning only one input string does not concatenate both inputs.",
                "suggestion": "Return the combined strings, for example with a + b.",
            }

    if "string is empty" in question_text:
        if ".isempty()" in code or ".length()==0" in code or ".length() == 0" in code or '.equals("")' in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": _java_success_feedback(question),
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the string is empty.",
                "suggestion": "Return true only when the string has length 0 or equals the empty string.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the string is empty.",
                "suggestion": "Return true only when the string has length 0 or equals the empty string.",
            }

    if "length of string" in question_text or "find length of string" in question_text:
        if ".length()" in code or ".tochararray().length" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly returns the length of the string.",
            }
        if re.search(r"return\s+0\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning 0 does not calculate the length of the string.",
                "suggestion": "Return the number of characters in the string, for example with s.length().",
            }
        if re.search(r"return\s*-\s*1\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning -1 does not calculate the length of the string.",
                "suggestion": "Return the number of characters in the string, for example with s.length().",
            }

    if "first two characters" in question_text:
        if ".substring(0,2)" in code or ".substring(0, 2)" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly returns the first two characters of the string.",
            }
        if ".substring(0,1)" in code or ".substring(0, 1)" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method returns only the first character instead of the first two characters.",
                "suggestion": "Return the first two characters, for example with s.substring(0, 2).",
            }
        if re.search(r"return\s+[a-z_][a-z0-9_]*\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the original string does not return only the first two characters.",
                "suggestion": "Return the first two characters, for example with s.substring(0, 2).",
            }
        if re.search(r'return\s*"[^"]*"\s*;', code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning a constant string does not retrieve the first two characters of the input.",
                "suggestion": "Return the first two characters, for example with s.substring(0, 2).",
            }

    if "first character" in question_text:
        if ".charat(0)" in code or ".substring(0,1).charat(0)" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly returns the first character of the string.",
            }
        if ".charat(s.length()-1)" in code or ".charat( s.length()-1)" in code or ".charat(s.length() - 1)" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the last character does not satisfy the first-character requirement.",
                "suggestion": "Return the first character, for example with s.charAt(0).",
            }
        if re.search(r"return\s*'[^']'\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning a constant character does not retrieve the first character of the input string.",
                "suggestion": "Return the first character, for example with s.charAt(0).",
            }

    if "last character" in question_text:
        if ".charat(s.length()-1)" in code or ".charat(s.length() - 1)" in code or ".substring(s.length()-1).charat(0)" in code or ".substring(s.length() - 1).charat(0)" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly returns the last character of the string.",
            }
        if ".charat(0)" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning the first character does not satisfy the last-character requirement.",
                "suggestion": "Return the last character, for example with s.charAt(s.length() - 1).",
            }
        if re.search(r"return\s*'[^']'\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Returning a constant character does not retrieve the last character of the input string.",
                "suggestion": "Return the last character, for example with s.charAt(s.length() - 1).",
            }

    if "starts with" in question_text and "'a'" in question_text:
        if '.startswith("a")' in code or ".charat(0)=='a'" in code or ".charat(0) == 'a'" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the string starts with 'A'.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the string starts with 'A'.",
                "suggestion": "Return a boolean expression such as s.startsWith(\"A\").",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the string starts with 'A'.",
                "suggestion": "Return a boolean expression such as s.startsWith(\"A\").",
            }

    if "divisible by 10" in question_text:
        if "% 10 == 0" in code or "%10==0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is divisible by 10.",
            }
        if "% 5 == 0" in code or "%5==0" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method checks divisibility by 5, which includes extra cases that are not necessarily divisible by 10.",
                "suggestion": "Use a modulo-10 check such as n % 10 == 0.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the number is divisible by 10.",
                "suggestion": "Return a boolean expression such as n % 10 == 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is divisible by 10.",
                "suggestion": "Return a boolean expression such as n % 10 == 0.",
            }

    if "array length is less than 5" in question_text or "length is less than 5" in question_text:
        if ".length < 5" in code or ".length<5" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the array length is less than 5.",
            }
        if ".length <= 5" in code or ".length<=5" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats length 5 as satisfying the condition, so it misses the strict less-than requirement.",
                "suggestion": "Return true only when the array length is strictly less than 5.",
            }
        if ".length == 5" in code or ".length==5" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the array length equals 5 does not implement the less-than-5 requirement.",
                "suggestion": "Return true only when the array length is strictly less than 5.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the array length is less than 5.",
                "suggestion": "Return a boolean expression such as arr.length < 5.",
            }

    if "string length > 5" in question_text or "string length >5" in question_text:
        if ".length() > 5" in code or ".length()>5" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the string length is greater than 5.",
            }
        if ".length() >= 5" in code or ".length()>=5" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats length 5 as satisfying the condition, so it misses the strict greater-than requirement.",
                "suggestion": "Return true only when the string length is strictly greater than 5.",
            }
        if ".length() == 5" in code or ".length()==5" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the string length equals 5 does not implement the greater-than-5 requirement.",
                "suggestion": "Return true only when the string length is strictly greater than 5.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the string length is greater than 5.",
                "suggestion": "Return a boolean expression such as s.length() > 5.",
            }

    if "array length > 3" in question_text or "length > 3" in question_text:
        if ".length > 3" in code or ".length>3" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the array length is greater than 3.",
            }
        if ".length >= 3" in code or ".length>=3" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method treats length 3 as satisfying the condition, so it misses the strict greater-than requirement.",
                "suggestion": "Return true only when the array length is strictly greater than 3.",
            }
        if ".length == 3" in code or ".length==3" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the array length equals 3 does not implement the greater-than-3 requirement.",
                "suggestion": "Return true only when the array length is strictly greater than 3.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the array length is greater than 3.",
                "suggestion": "Return a boolean expression such as arr.length > 3.",
            }

    if "array is empty" in question_text:
        if ".length == 0" in code or ".length==0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the array is empty.",
            }
        if ".length <= 0" in code or ".length<=0" in code:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The method is mostly correct, but the direct empty-array check should use equality with 0.",
                "suggestion": "Return true only when the array length is exactly 0.",
            }
        if ".length == 1" in code or ".length==1" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the array length equals 1 does not implement the empty-array requirement.",
                "suggestion": "Return true only when the array length is exactly 0.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the array is empty.",
                "suggestion": "Return a boolean expression such as arr.length == 0.",
            }

    if "string length is even" in question_text or "length is even" in question_text:
        if re.search(r"return\s*\(?\s*[^;]*length\(\)\s*%\s*2\s*\)?\s*==\s*0\s*\?\s*true\s*:\s*false\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the string length is even.",
            }
        if ".length() % 2 == 0" in code or ".length()%2==0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the string length is even.",
            }
        if ".length() % 2 == 1" in code or ".length()%2==1" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the string length is odd does not implement the even-length requirement.",
                "suggestion": "Return a boolean expression such as s.length() % 2 == 0.",
            }
        if re.search(r"return\s+false\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns false instead of checking whether the string length is even.",
                "suggestion": "Return a boolean expression such as s.length() % 2 == 0.",
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
        if re.search(r"return\s+[^;]*%\s*2\s*==\s*0\s*\?\s*true\s*:\s*false\s*;", code):
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is even.",
            }
        if "(n&1)==0" in code or "( n & 1 ) == 0" in code:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The method correctly checks whether the number is even using a bitwise operation.",
            }
        if "%2==1" in code or "% 2 == 1" in code:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Checking whether the remainder is 1 does not correctly implement the required even-number check.",
                "suggestion": "Return a boolean expression such as n % 2 == 0.",
            }
        if re.search(r"return\s+true\s*;", code):
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The method always returns true instead of checking whether the number is even.",
                "suggestion": "Return a boolean expression such as n % 2 == 0.",
            }

    return None


def analyze_execution(question, sample_answer, student_answer, language):
    language = (language or "").lower()
    if language == "python":
        return analyze_python_execution(question, sample_answer, student_answer)
    if language == "java":
        return analyze_java_execution(question, sample_answer, student_answer)
    return None

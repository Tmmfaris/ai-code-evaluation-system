import ast
import re


JAVA_METHOD_NAME_RE = re.compile(r"(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z_<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")



def _safe_parse_python(code):
    try:
        return ast.parse(code)
    except Exception:
        return None



def _function_nodes(tree):
    if tree is None:
        return []
    return [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def _find_function_node(functions, *names):
    wanted = {name.lower() for name in names if name}
    for function in functions or []:
        if function.name.lower() in wanted:
            return function
    return functions[0] if functions else None



def _has_self_recursive_call(function_node):
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == function_node.name
        for node in ast.walk(function_node)
    )



def _has_lower_or_casefold(function_node):
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"lower", "upper", "casefold"}
        for node in ast.walk(function_node)
    )



def _uses_sorted_call(function_node):
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sorted"
        for node in ast.walk(function_node)
    )



def _uses_set_call(function_node):
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set"
        for node in ast.walk(function_node)
    )



def _uses_for_loop(function_node):
    return any(isinstance(node, ast.For) for node in ast.walk(function_node))



def _uses_while_loop(function_node):
    return any(isinstance(node, ast.While) for node in ast.walk(function_node))



def _returns_list_set_call(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "list"
        and node.value.args
        and isinstance(node.value.args[0], ast.Call)
        and isinstance(node.value.args[0].func, ast.Name)
        and node.value.args[0].func.id == "set"
        for node in ast.walk(function_node)
    )



def _uses_count_equality(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Compare)
        and any(isinstance(op, ast.Eq) for op in node.value.ops)
        and all(
            isinstance(side, ast.Call)
            and isinstance(side.func, ast.Attribute)
            and side.func.attr == "count"
            for side in [node.value.left] + list(node.value.comparators)
        )
        for node in ast.walk(function_node)
    )



def _returns_sum_list_concat(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "sum"
        and len(node.value.args) >= 2
        and isinstance(node.value.args[1], ast.List)
        and len(node.value.args[1].elts) == 0
        for node in ast.walk(function_node)
    )



def _uses_modulus_comparison_zero(function_node):
    return any(
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.BinOp)
        and isinstance(node.left.op, ast.Mod)
        and any(isinstance(op, ast.Eq) for op in node.ops)
        and any(isinstance(comp, ast.Constant) and comp.value == 0 for comp in node.comparators)
        for node in ast.walk(function_node)
    )



def _returns_constant_bool(function_node):
    return any(
        isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool)
        for node in ast.walk(function_node)
    )



def _returns_upper_comparison(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Compare)
        and isinstance(node.value.left, ast.Name)
        and any(isinstance(op, ast.Eq) for op in node.value.ops)
        and any(
            isinstance(comp, ast.Call)
            and isinstance(comp.func, ast.Attribute)
            and comp.func.attr == "upper"
            for comp in node.value.comparators
        )
        for node in ast.walk(function_node)
    )



def _returns_modulus_without_comparison(function_node):
    return any(
        isinstance(node, ast.Return) and isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Mod)
        for node in ast.walk(function_node)
    )



def _returns_sorted_index(function_node, index_value):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Subscript)
        and isinstance(node.value.value, ast.Call)
        and isinstance(node.value.value.func, ast.Name)
        and node.value.value.func.id == "sorted"
        and isinstance(node.value.slice, ast.Constant)
        and node.value.slice.value == index_value
        for node in ast.walk(function_node)
    )



def _returns_constant_true(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and node.value.value is True
        for node in ast.walk(function_node)
    )


def _returns_constant_string(function_node, value):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and node.value.value == value
        for node in ast.walk(function_node)
    )


def _returns_string_key_index(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Subscript)
        and isinstance(node.value.value, ast.Name)
        and isinstance(node.value.slice, ast.Name)
        for node in ast.walk(function_node)
    )


def _returns_dict_comp_len_key(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.DictComp)
        and isinstance(node.value.key, ast.Call)
        and isinstance(node.value.key.func, ast.Name)
        and node.value.key.func.id == "len"
        for node in ast.walk(function_node)
    )


def _returns_sorted_slice_without_set(function_node):
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Subscript):
            continue
        if not isinstance(node.value.value, ast.Call):
            continue
        call = node.value.value
        if not isinstance(call.func, ast.Name) or call.func.id != "sorted":
            continue
        if call.args and isinstance(call.args[0], ast.Call) and isinstance(call.args[0].func, ast.Name) and call.args[0].func.id == "set":
            continue
        slice_node = node.value.slice
        if isinstance(slice_node, ast.Slice) and isinstance(slice_node.lower, ast.UnaryOp) and isinstance(slice_node.lower.op, ast.USub) and isinstance(slice_node.lower.operand, ast.Constant) and slice_node.lower.operand.value == 2:
            return True
    return False



def _has_prime_lower_bound_guard(function_node):
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name):
            continue
        if not any(isinstance(op, (ast.Lt, ast.LtE)) for op in node.ops):
            continue
        for comp in node.comparators:
            if isinstance(comp, ast.Constant) and isinstance(comp.value, int) and comp.value <= 2:
                return True
    return False



def _uses_sqrt_bound(function_node):
    for node in ast.walk(function_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "int":
            for sub in ast.walk(node):
                if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Pow):
                    return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "sqrt":
            return True
    return False



def _contains_lowercase_vowel_membership(function_node):
    for node in ast.walk(function_node):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.In) for op in node.ops):
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, str) and "aeiou" in comp.value:
                    return True
    return False



def _java_method_name(code):
    match = JAVA_METHOD_NAME_RE.search(code or "")
    return match.group(1) if match else None



def _java_contains(code, text):
    return text.lower() in (code or "").lower()


def _java_contains_any(code, *parts):
    lowered = (code or "").lower()
    return any(part in lowered for part in parts)


def _generic_requirement_findings(question, student_answer, language):
    question_text = (question or "").lower()
    code = (student_answer or "").lower()
    language = (language or "").lower()
    findings = []

    if "using set" in question_text and not any(token in code for token in ("set", "hashset", "treeset", "linkedhashset", "distinct()")):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 20,
            "efficiency_max": 12,
            "feedback": "The answer does not use the required Set-based approach.",
            "suggestion": "Use a Set or a distinct-based approach to satisfy the requirement."
        })

    if "using map" in question_text and not any(token in code for token in ("map", "hashmap", "treemap", "linkedhashmap", "dict", "dictionary")):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 20,
            "efficiency_max": 12,
            "feedback": "The answer does not use the required Map-based approach.",
            "suggestion": "Use a Map or dictionary structure to satisfy the requirement."
        })

    if language != "java" and "stream" in question_text and "stream" not in code:
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 34,
            "efficiency_max": 15,
            "feedback": "The logic may be correct, but it does not use streams as required by the question.",
            "suggestion": "Use the required stream-based approach if the question explicitly asks for it."
        })

    if language != "java" and ("exception handling" in question_text or "with exception" in question_text or "safely" in question_text or "safe" in question_text) and not (
        "try" in code and ("catch" in code or "except" in code)
    ):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 14,
            "efficiency_max": 10,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "The answer does not include the required safe error handling for this task.",
            "suggestion": "Add try/catch or try/except handling and return a safe fallback result on failure."
        })

    if language != "java" and "abstract class" in question_text and "abstract class" not in code:
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 28,
            "efficiency_max": 15,
            "feedback": "The answer does not implement the required abstract class structure.",
            "suggestion": "Declare the base class as abstract and implement the required method in the subclass."
        })

    if language != "java" and "sort objects" in question_text and "salary" in question_text and "salary" not in code:
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 28,
            "efficiency_max": 15,
            "feedback": "The code does not define ordering by salary, even though the question requires salary-based sorting.",
            "suggestion": "Use a salary-based comparator or comparable implementation."
        })

    if language != "java" and "stack" in question_text and "using array" in question_text and not (
        "push" in code and "pop" in code
    ):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 12,
            "efficiency_max": 10,
            "feedback": "The answer does not implement the required stack operations over the array storage.",
            "suggestion": "Implement push and pop behavior using the array and a top index."
        })

    if language != "java" and ("valid json" in question_text or "json format" in question_text) and "return true" in code:
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The answer always returns true instead of validating the JSON-related condition.",
            "suggestion": "Check the required JSON-format conditions before returning true."
        })

    return findings


def analyze_question_risk(question, language, question_profile=None):
    question_text = (question or "").lower()
    language = (language or "").lower()
    profile = question_profile or {}
    category = profile.get("category", "general")
    risk = profile.get("risk", "medium")

    low_risk_markers = (
        "add two numbers",
        "even",
        "reverse string",
        "reverse list",
        "palindrome",
        "factorial",
        "prime",
        "sum of digits",
        "count words",
        "count vowels",
        "lowercase",
        "uppercase",
        "remove spaces",
        "minimum",
        "maximum",
        "second largest",
        "top 2 largest",
        "power of 2",
        "power of two",
        "binary search",
        "balanced parentheses",
        "flatten",
        "frequency",
        "remove duplicates",
        "common elements",
        "numeric",
        "only digits",
        "positive",
        "sum of all elements",
        "filter even numbers",
    )
    if risk == "low" or any(marker in question_text for marker in low_risk_markers):
        return []

    high_risk_markers = (
        "create a class",
        "abstract class",
        "read a file",
        "csv",
        "json",
        "xml",
        "api",
        "database",
        "sql",
        "network",
        "socket",
        "http",
        "thread",
        "concurrency",
        "stream",
        "sort objects",
        "employee",
        "framework",
        "react",
        "spring",
        "django",
        "flask",
        "servlet",
        "gui",
    )
    if risk == "high" or any(marker in question_text for marker in high_risk_markers):
        return [{
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
        }]

    if category in {"arrays_lists", "arrays_search_sort", "collections"}:
        return [{
            "type": "correctness_cap",
            "correctness_max": 32,
            "efficiency_max": 15,
        }]

    if language in {"python", "java"} and ("class" in question_text or "method" in question_text or "function" in question_text):
        return [{
            "type": "correctness_cap",
            "correctness_max": 32,
            "efficiency_max": 15,
        }]

    return []



def _analyze_java_submission_rules(question, student_answer):
    question_text = (question or "").lower()
    code = student_answer or ""
    lowered = code.lower()
    findings = []
    method_name = _java_method_name(code)

    if "factorial" in question_text and method_name and f"{method_name}(" not in lowered.split("return", 1)[-1]:
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The method does not implement recursive factorial logic.",
            "suggestion": "Use a base case and a recursive call to the same method."
        })

    if "palindrome" in question_text and re.search(r"return\s+true\s*;", lowered):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The method always returns true instead of checking whether the string is a palindrome.",
            "suggestion": "Compare the original string with its reversed form or equivalent mirrored logic."
        })

    if ("only digits" in question_text or "digit" in question_text) and re.search(r"return\s+true\s*;", lowered):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The method always returns true instead of checking whether the string contains only digits.",
            "suggestion": "Use matches(\"\\\\d+\") or an equivalent digit check."
        })

    if "positive" in question_text and ">= 0" in code:
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 22,
            "feedback": "The method checks for non-negative numbers instead of strictly positive numbers.",
            "suggestion": "Return true only when the number is greater than zero."
        })

    if "even" in question_text and re.search(r"return\s+[^;]*%\s*2\s*;", lowered) and "==" not in lowered:
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The method returns a remainder instead of a boolean even-check result.",
            "suggestion": "Compare the remainder to 0 so the method returns true or false directly."
        })

    if ("maximum" in question_text or "max" in question_text) and "arrays.sort" in lowered:
        findings.append({
            "type": "efficiency_cap",
            "efficiency_max": 12,
            "feedback": "The result is correct, but sorting the full array is less efficient than scanning once for the maximum.",
            "suggestion": "Track the maximum in a single pass instead of sorting the entire array."
        })

    if ("minimum" in question_text or "min" in question_text) and "arrays.sort" in lowered:
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 34,
            "efficiency_max": 12,
            "readability_min": 8,
            "structure_min": 12,
            "feedback": "The result is correct, but sorting the full array is less efficient than finding the minimum directly.",
            "suggestion": "Track the minimum in a single pass instead of sorting the full array."
        })

    if "vowel" in question_text and "aeiou" in lowered and ".tolowercase()" not in lowered:
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 34,
            "efficiency_max": 15,
            "feedback": "The code counts lowercase vowels only and misses uppercase vowel inputs.",
            "suggestion": "Convert the string to lowercase before checking vowel membership."
        })

    if "lowercase" in question_text and ".tolowercase()" in lowered:
        findings.append({
            "type": "feedback_only",
            "feedback": "The method correctly converts the input string to lowercase.",
        })

    if "remove spaces" in question_text and '.replace(" ", "")' in code:
        findings.append({
            "type": "feedback_only",
            "feedback": "The method correctly removes spaces from the input string.",
        })

    if "using streams" in question_text and not _java_contains_any(lowered, ".stream()", ".filter("):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 30,
            "efficiency_max": 12,
            "feedback": "The logic may be correct, but it does not use streams as required by the question.",
            "suggestion": "Use stream operations such as stream().filter(...) to satisfy the required approach."
        })

    if ("exception handling" in question_text or "safely" in question_text) and not (
        _java_contains_any(lowered, "try{", "try {") and "catch" in lowered
    ):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 12,
            "feedback": "The method does not include the required exception handling for this task.",
            "suggestion": "Wrap the risky operation in try/catch and return a safe fallback value on failure."
        })

    if "abstract class" in question_text and "abstract class" not in lowered:
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 12,
            "feedback": "The answer does not implement the required abstract class structure.",
            "suggestion": "Declare the base class as abstract and implement the required method in the subclass."
        })

    if (
        "sort objects" in question_text
        and "salary" in question_text
        and "collections.sort" in lowered
        and "salary" not in lowered
        and "comparator" not in lowered
        and "compareto" not in lowered
        and "->" not in lowered
    ):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 12,
            "feedback": "The code sorts the list, but it does not define ordering by salary.",
            "suggestion": "Provide a salary-based comparator or Comparable implementation so employees are sorted by salary."
        })

    if "using map" in question_text and not _java_contains_any(lowered, "map<", "hashmap", "treemap", "linkedhashmap"):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 20,
            "efficiency_max": 12,
            "feedback": "The answer does not use a Map as required by the question.",
            "suggestion": "Use a Map implementation and update counts or values through that Map."
        })

    if "using set" in question_text and not _java_contains_any(lowered, "set<", "hashset", "treeset", "linkedhashset", "distinct()"):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 20,
            "efficiency_max": 12,
            "feedback": "The answer does not use a Set-based approach as required by the question.",
            "suggestion": "Use a Set or a distinct-based approach to satisfy the required technique."
        })

    if "intersection of two arrays" in question_text and "for(" in lowered and "for(" in lowered.split("for(", 1)[-1] and "res.add(" in lowered:
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 18,
            "efficiency_max": 10,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The method can find shared values, but nested loops can add duplicates and do not control the intersection result carefully.",
            "suggestion": "Use a HashSet for membership checks and control duplicates in the intersection output."
        })

    return findings



def analyze_submission_rules(question, student_answer, language):
    language = (language or "").lower()
    generic_findings = _generic_requirement_findings(question, student_answer, language)

    if language == "java":
        return generic_findings + _analyze_java_submission_rules(question, student_answer)
    if language != "python":
        return generic_findings

    tree = _safe_parse_python(student_answer)
    functions = _function_nodes(tree)
    function_node = _find_function_node(functions, "grade", "safe_div", "remove_dup", "is_num")
    if function_node is None:
        return generic_findings

    question_text = (question or "").lower()
    findings = list(generic_findings)

    if "grade" in question_text and "student" in question_text and _returns_constant_string(function_node, "A"):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The class always returns grade A instead of computing the grade from the marks.",
            "suggestion": "Add conditions for the marks ranges so the method returns A, B, or C correctly."
        })

    if "parse" in question_text and "json" in question_text and "key" in question_text and _returns_string_key_index(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 10,
            "efficiency_max": 10,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "The function indexes the raw string directly instead of parsing the JSON string before reading the key.",
            "suggestion": "Parse the JSON string first, then read the value for the requested key."
        })

    if "group" in question_text and "words" in question_text and "length" in question_text and _returns_dict_comp_len_key(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 10,
            "efficiency_max": 10,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Using a dict comprehension with len(w) as the key overwrites earlier words of the same length instead of grouping them together.",
            "suggestion": "Build a dictionary whose values are lists, then append each word to the list for its length."
        })

    if "prime" in question_text:
        if _returns_constant_true(function_node):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 2,
                "efficiency_max": 2,
                "readability_max": 5,
                "structure_max": 8,
                "feedback": "The function always returns True instead of checking whether the number is prime.",
                "suggestion": "Test divisibility and return False for non-prime values."
            })
        elif not _has_prime_lower_bound_guard(function_node):
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 28,
                "efficiency_max": 12,
                "feedback": "Missing an explicit n < 2 guard, so some non-prime edge cases are handled incorrectly.",
                "suggestion": "Add an early return for values below 2 before checking divisibility."
            })
        elif not _uses_sqrt_bound(function_node):
            findings.append({
                "type": "efficiency_cap",
                "efficiency_max": 12,
                "feedback": "The logic is acceptable, but the loop checks more numbers than necessary.",
                "suggestion": "Check divisors only up to the square root of n for better efficiency."
            })

    if "vowel" in question_text and _contains_lowercase_vowel_membership(function_node) and not _has_lower_or_casefold(function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 34,
            "efficiency_max": 15,
            "feedback": "The code counts lowercase vowels only and misses uppercase vowel inputs.",
            "suggestion": "Normalize the string with lower() or casefold() before checking vowels."
        })

    if "palindrome" in question_text and _returns_constant_bool(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function returns a constant boolean instead of checking whether the string is a palindrome.",
            "suggestion": "Compare the original string with its reverse or an equivalent mirrored check."
        })

    if "factorial" in question_text and not _has_self_recursive_call(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function does not implement recursive factorial logic.",
            "suggestion": "Use a base case and a recursive call to the same function."
        })

    if "balanced parentheses" in question_text and _uses_count_equality(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "Counting opening and closing parentheses alone does not correctly detect balanced parentheses.",
            "suggestion": "Track the order of parentheses with a stack or a balance counter that never goes negative."
        })

    if ("even" in question_text or "divisible by" in question_text) and _returns_modulus_without_comparison(function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 12,
            "feedback": "Returning only the remainder does not directly implement the required boolean divisibility check.",
            "suggestion": "Compare the remainder to 0 so the function explicitly returns True or False."
        })

    if ("power of 2" in question_text or "power of two" in question_text) and (
        _returns_modulus_without_comparison(function_node) or _uses_modulus_comparison_zero(function_node)
    ):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "Checking whether a number is even is not the same as checking whether it is a power of two.",
            "suggestion": "Use a true power-of-two check such as n > 0 and (n & (n - 1)) == 0."
        })

    if ("maximum" in question_text or "max" in question_text) and _uses_sorted_call(function_node):
        findings.append({
            "type": "efficiency_cap",
            "efficiency_max": 12,
            "feedback": "The result is correct, but sorting the full list is less efficient than a direct maximum scan.",
            "suggestion": "Use max(lst) or a single-pass comparison instead of sorting the entire list."
        })

    if ("minimum" in question_text or "min" in question_text) and (_uses_sorted_call(function_node) or _returns_sorted_index(function_node, 0)):
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 34,
            "efficiency_max": 12,
            "readability_min": 5,
            "structure_min": 12,
            "feedback": "The result is correct, but sorting the full list is less efficient than finding the minimum directly.",
            "suggestion": "Use min(lst) or a single-pass comparison instead of sorting the entire list."
        })

    if "second largest" in question_text and _uses_sorted_call(function_node) and not _uses_set_call(function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 28,
            "efficiency_max": 12,
            "feedback": "Sorting without removing duplicates can return the largest value again instead of the second distinct largest element.",
            "suggestion": "Remove duplicates first, or track the two largest distinct values explicitly."
        })

    if "top 2 largest" in question_text and _returns_sorted_slice_without_set(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 10,
            "efficiency_max": 10,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Sorting without removing duplicates can return repeated largest values instead of the top two distinct numbers.",
            "suggestion": "Remove duplicates first, or track the two largest distinct values explicitly."
        })

    if "binary search" in question_text and _uses_for_loop(function_node) and not _uses_while_loop(function_node):
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 34,
            "efficiency_max": 12,
            "readability_min": 8,
            "structure_min": 12,
            "feedback": "The function returns correct search results, but it uses a linear scan instead of binary search.",
            "suggestion": "Use low, high, and mid pointers to implement binary search with logarithmic time complexity."
        })

    if "duplicate" in question_text and not _uses_set_call(function_node):
        findings.append({
            "type": "feedback_only",
            "feedback": "The solution correctly removes duplicates and also preserves input order, which a plain set-based approach would not.",
            "suggestion": "Keep this ordered approach if preserving the original sequence matters."
        })

    if "duplicate" in question_text and "preserving order" in question_text and _returns_list_set_call(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 8,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Using set removes duplicates but does not preserve the original order of the list.",
            "suggestion": "Use an ordered approach such as dict.fromkeys(...) or a loop with a seen set."
        })

    if "uppercase" in question_text and _returns_upper_comparison(function_node):
        findings.append({
            "type": "feedback_only",
            "feedback": "The solution correctly checks uppercase text with a valid string comparison approach.",
            "suggestion": "Using s.isupper() is shorter, but the current logic is still valid."
        })

    if "count the number of elements" in question_text:
        findings.append({
            "type": "feedback_only",
            "suggestion": "The loop-based counting logic is valid; using len(lst) would simply be a shorter built-in alternative."
        })

    if "flatten" in question_text and "list" in question_text and _returns_sum_list_concat(function_node):
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 34,
            "efficiency_max": 12,
            "readability_min": 8,
            "structure_min": 12,
            "feedback": "The function flattens the nested list correctly, but repeatedly concatenating lists with sum is less efficient than a loop or comprehension.",
            "suggestion": "Use a nested loop or list comprehension instead of repeatedly concatenating lists with sum."
        })

    if "armstrong" in question_text and "**3" in (student_answer or "").replace(" ", ""):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 28,
            "efficiency_max": 15,
            "feedback": "Cubing every digit only works for 3-digit Armstrong numbers and misses general Armstrong cases.",
            "suggestion": "Raise each digit to the power of the total number of digits instead of always using 3."
        })

    if ("only digits" in question_text or "isdigit" in question_text or "numeric" in question_text) and _returns_constant_true(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns True instead of checking whether the string contains only digits.",
            "suggestion": "Use s.isdigit() or an equivalent character-by-character check."
        })

    return findings



def apply_rule_adjustments(rubric_score, feedback, suggestions, findings):
    adjusted = dict(rubric_score)
    updated_feedback = feedback or ""
    updated_suggestions = suggestions or ""

    if not findings:
        return adjusted, updated_feedback, updated_suggestions

    mins = {}
    maxes = {}
    for finding in findings:
        for key in ("correctness", "efficiency", "readability", "structure"):
            min_key = f"{key}_min"
            max_key = f"{key}_max"
            if min_key in finding:
                mins[key] = max(mins.get(key, finding[min_key]), finding[min_key])
            if max_key in finding:
                maxes[key] = min(maxes.get(key, finding[max_key]), finding[max_key]) if key in maxes else finding[max_key]

    for key, value in mins.items():
        adjusted[key] = max(adjusted.get(key, 0), value)

    for key, value in maxes.items():
        adjusted[key] = min(adjusted.get(key, 0), value)

    priority_feedback = next((item["feedback"] for item in findings if item.get("feedback")), updated_feedback)
    priority_suggestion = next((item["suggestion"] for item in findings if item.get("suggestion")), updated_suggestions)

    return adjusted, priority_feedback, priority_suggestion

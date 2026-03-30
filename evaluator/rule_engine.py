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

    return findings



def analyze_submission_rules(question, student_answer, language):
    language = (language or "").lower()
    if language == "java":
        return _analyze_java_submission_rules(question, student_answer)
    if language != "python":
        return []

    tree = _safe_parse_python(student_answer)
    functions = _function_nodes(tree)
    function_node = functions[0] if functions else None
    if function_node is None:
        return []

    question_text = (question or "").lower()
    findings = []

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

    if ("even" in question_text or "divisible by" in question_text) and _returns_modulus_without_comparison(function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 12,
            "feedback": "Returning only the remainder does not directly implement the required boolean divisibility check.",
            "suggestion": "Compare the remainder to 0 so the function explicitly returns True or False."
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

    if "duplicate" in question_text and not _uses_set_call(function_node):
        findings.append({
            "type": "feedback_only",
            "feedback": "The solution correctly removes duplicates and also preserves input order, which a plain set-based approach would not.",
            "suggestion": "Keep this ordered approach if preserving the original sequence matters."
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

    if ("only digits" in question_text or "isdigit" in question_text) and _returns_constant_true(function_node):
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

    for finding in findings:
        if "correctness_min" in finding:
            adjusted["correctness"] = max(adjusted.get("correctness", 0), finding["correctness_min"])
        if "correctness_max" in finding:
            adjusted["correctness"] = min(adjusted.get("correctness", 0), finding["correctness_max"])
        if "efficiency_min" in finding:
            adjusted["efficiency"] = max(adjusted.get("efficiency", 0), finding["efficiency_min"])
        if "efficiency_max" in finding:
            adjusted["efficiency"] = min(adjusted.get("efficiency", 0), finding["efficiency_max"])
        if "readability_min" in finding:
            adjusted["readability"] = max(adjusted.get("readability", 0), finding["readability_min"])
        if "readability_max" in finding:
            adjusted["readability"] = min(adjusted.get("readability", 0), finding["readability_max"])
        if "structure_min" in finding:
            adjusted["structure"] = max(adjusted.get("structure", 0), finding["structure_min"])
        if "structure_max" in finding:
            adjusted["structure"] = min(adjusted.get("structure", 0), finding["structure_max"])

    priority_feedback = next((item["feedback"] for item in findings if item.get("feedback")), updated_feedback)
    priority_suggestion = next((item["suggestion"] for item in findings if item.get("suggestion")), updated_suggestions)

    return adjusted, priority_feedback, priority_suggestion

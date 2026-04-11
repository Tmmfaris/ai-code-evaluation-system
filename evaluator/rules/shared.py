import ast
import re

from evaluator.rules.python_families import (
    analyze_list_rules,
    analyze_number_rules,
    analyze_string_rules,
)
from evaluator.rules.javascript_families import (
    analyze_list_rules as analyze_javascript_list_rules,
    analyze_number_rules as analyze_javascript_number_rules,
    analyze_string_rules as analyze_javascript_string_rules,
)

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
    if function_node is None:
        return False

    if any(
        isinstance(node, (ast.If, ast.For, ast.While, ast.AsyncFor, ast.Try, ast.Match))
        for node in ast.walk(function_node)
        if node is not function_node
    ):
        return False

    returns = [node for node in ast.walk(function_node) if isinstance(node, ast.Return)]
    return bool(returns) and all(
        isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool)
        for node in returns
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
    if function_node is None:
        return False

    returns = [node for node in ast.walk(function_node) if isinstance(node, ast.Return)]
    return bool(returns) and all(
        isinstance(node.value, ast.Constant) and node.value.value is True
        for node in returns
    )


def _returns_constant_string(function_node, value):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and node.value.value == value
        for node in ast.walk(function_node)
    )


def _returns_name(function_node, *names):
    wanted = {name for name in names if name}
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Name)
        and node.value.id in wanted
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


def _returns_dict_comp_count_split(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.DictComp)
        and isinstance(node.value.key, ast.Name)
        and isinstance(node.value.value, ast.Call)
        and isinstance(node.value.value.func, ast.Attribute)
        and node.value.value.func.attr == "count"
        and isinstance(node.value.value.func.value, ast.Name)
        and len(node.value.generators) == 1
        and isinstance(node.value.generators[0].iter, ast.Call)
        and isinstance(node.value.generators[0].iter.func, ast.Attribute)
        and node.value.generators[0].iter.func.attr == "split"
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


def _returns_sorted_split_by_len_last(function_node):
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Subscript):
            continue
        if not isinstance(node.value.value, ast.Call):
            continue
        outer_call = node.value.value
        if not isinstance(outer_call.func, ast.Name) or outer_call.func.id != "sorted":
            continue
        if not outer_call.args:
            continue
        split_call = outer_call.args[0]
        if not (
            isinstance(split_call, ast.Call)
            and isinstance(split_call.func, ast.Attribute)
            and split_call.func.attr == "split"
        ):
            continue
        if not any(
            keyword.arg == "key"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "len"
            for keyword in outer_call.keywords
        ):
            continue
        slice_node = node.value.slice
        if isinstance(slice_node, ast.UnaryOp) and isinstance(slice_node.op, ast.USub) and isinstance(slice_node.operand, ast.Constant) and slice_node.operand.value == 1:
            return True
    return False


def _returns_reversed_list_slice(function_node):
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Subscript)
        and isinstance(node.value.value, ast.Name)
        and isinstance(node.value.slice, ast.Slice)
        and node.value.slice.lower is None
        and node.value.slice.upper is None
        and isinstance(node.value.slice.step, ast.UnaryOp)
        and isinstance(node.value.slice.step.op, ast.USub)
        and isinstance(node.value.slice.step.operand, ast.Constant)
        and node.value.slice.step.operand.value == 1
        for node in ast.walk(function_node)
    )


def _returns_common_elements_listcomp_without_dedup(function_node):
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.ListComp):
            continue
        comp = node.value
        if len(comp.generators) != 1:
            continue
        generator = comp.generators[0]
        if not isinstance(generator.target, ast.Name) or not isinstance(generator.iter, ast.Name):
            continue
        if not isinstance(comp.elt, ast.Name) or comp.elt.id != generator.target.id:
            continue
        if len(generator.ifs) != 1:
            continue
        cond = generator.ifs[0]
        if (
            isinstance(cond, ast.Compare)
            and isinstance(cond.left, ast.Name)
            and cond.left.id == generator.target.id
            and any(isinstance(op, ast.In) for op in cond.ops)
            and any(isinstance(comp_item, ast.Name) for comp_item in cond.comparators)
        ):
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


def _returns_name_gt_one(function_node):
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Compare):
            continue
        compare = node.value
        if not isinstance(compare.left, ast.Name):
            continue
        if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Gt):
            continue
        if len(compare.comparators) != 1:
            continue
        comparator = compare.comparators[0]
        if isinstance(comparator, ast.Constant) and comparator.value == 1:
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


def _requires_recursion(question):
    lowered = (question or "").lower()
    return "recursion" in lowered or "recursive" in lowered


def _generic_requirement_findings(question, student_answer, language):
    question_text = (question or "").lower()
    code = (student_answer or "").lower()
    language = (language or "").lower()
    findings = []

    if language == "css":
        if "center" in question_text and "div" in question_text and "text-align:center" in code.replace(" ", ""):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 8,
                "efficiency_max": 8,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "Using text-align:center only centers inline content horizontally, not the div itself both horizontally and vertically.",
                "suggestion": "Use a layout technique such as flexbox with justify-content and align-items to center the div in both directions."
            })
        if "red" in question_text and "red" not in code:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 8,
                "efficiency_max": 8,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The CSS does not apply the required red styling from the question.",
                "suggestion": "Target the required selector and set its color to red."
            })
        if "red" in question_text and "color" in question_text and ("color" not in code or "red" not in code):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 8,
                "efficiency_max": 8,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The CSS does not apply the required red color styling from the question.",
                "suggestion": "Use the correct selector and set the color property to red."
            })
        if "h1" in question_text and "h1" not in code:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 20,
                "efficiency_max": 12,
                "feedback": "The CSS does not target the required h1 elements from the question.",
                "suggestion": "Use an h1 selector if the question asks to style h1 elements."
            })

    if language == "html":
        if "button" in question_text and "<button" not in code:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 8,
                "efficiency_max": 8,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The HTML does not use a button element even though the question asks for one.",
                "suggestion": "Use a <button> element instead of a generic container tag."
            })
        if "heading" in question_text and not any(tag in code for tag in ("<h1", "<h2", "<h3", "<h4", "<h5", "<h6")):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 10,
                "efficiency_max": 10,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The HTML does not use a heading tag even though the question asks for a heading.",
                "suggestion": "Use an h1-h6 heading tag that matches the requested output."
            })
        if "hello" in question_text and "hello" not in code:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 16,
                "efficiency_max": 10,
                "feedback": "The HTML does not include the required Hello text from the question.",
                "suggestion": "Include the requested Hello text in the heading output."
            })

    if language == "react":
        if ("react component" in question_text or "component" in question_text) and not (
            "return" in code and "<" in code and ">" in code
        ):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 10,
                "efficiency_max": 10,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The answer does not look like a React component that returns JSX.",
                "suggestion": "Define a component and return the required JSX output."
            })
        if "state hook" in question_text and "usestate" not in code:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 8,
                "efficiency_max": 8,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The component does not use the required useState hook.",
                "suggestion": "Initialize component state with useState(...) instead of a plain local variable."
            })
        if "hello" in question_text and "hello" not in code:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 20,
                "efficiency_max": 12,
                "feedback": "The component does not render the required Hello content from the question.",
                "suggestion": "Return JSX that includes the requested Hello text."
            })

    if language == "java":
        normalized_java = code.replace(" ", "")
        if "reverse" in question_text and ("list" in question_text or "array" in question_text):
            if ("collections.sort" in code or "arrays.sort" in code) and "reverse" not in code:
                findings.append({
                    "type": "hard_fail",
                    "correctness_max": 10,
                    "efficiency_max": 10,
                    "readability_max": 10,
                    "structure_max": 12,
                    "feedback": "Sorting the list does not reverse its order.",
                    "suggestion": "Use Collections.reverse(...) or reverse iteration to return the list in reverse order."
                })
            if "returnlist;" in normalized_java and "reverse" not in code:
                findings.append({
                    "type": "correctness_cap",
                    "correctness_max": 16,
                    "efficiency_max": 12,
                    "feedback": "Returning the original list does not reverse its order.",
                    "suggestion": "Reverse the list before returning it."
                })

    if language == "mysql":
        if "select all rows" in question_text and "select *" not in code and "select" in code:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 8,
                "efficiency_max": 8,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The SQL query selects specific columns instead of selecting all columns from every row.",
                "suggestion": "Use SELECT * FROM ... when the question asks for all rows and all columns."
            })
        if "students" in question_text and "students" not in code:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 10,
                "efficiency_max": 10,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The SQL query does not use the required students table from the question.",
                "suggestion": "Query the students table named in the question."
            })
        if "select" in question_text and "select" not in code:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 16,
                "efficiency_max": 10,
                "feedback": "The answer does not use the expected SELECT query form for this task.",
                "suggestion": "Use a SELECT query that matches the requested result."
            })

    if language == "mongodb":
        if "find all documents" in question_text and "findone(" in code:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 20,
                "efficiency_max": 12,
                "feedback": "The MongoDB query retrieves only one document instead of returning all matching documents.",
                "suggestion": "Use find(...) instead of findOne(...) when the task asks for all documents."
            })
        if "insert document" in question_text and "insert()" in code and "insertone(" not in code:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 20,
                "efficiency_max": 12,
                "feedback": "The MongoDB query does not use the expected single-document insert call for this task.",
                "suggestion": "Use insertOne({...}) with the required document contents."
            })
        if "students" in question_text and "students" not in code:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 10,
                "efficiency_max": 10,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "The MongoDB query does not use the required students collection from the question.",
                "suggestion": "Query the students collection named in the question."
            })
        if "active" in question_text and "active" not in code:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 16,
                "efficiency_max": 10,
                "feedback": "The MongoDB query does not include the required active filter from the question.",
                "suggestion": "Include the active condition in the query filter."
            })

    normalized_js_answer = (student_answer or "").replace(" ", "").lower()
    if (
        language == "javascript"
        and "object is empty" in question_text
        and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE)
        and "for(letkinobj)returnfalse;returntrue;" not in normalized_js_answer
    ):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the object has any keys.",
            "suggestion": "Check Object.keys(obj).length === 0 or use an equivalent emptiness check."
        })
    if language == "javascript" and "reverse" in question_text and ("list" in question_text or "array" in question_text):
        if "sort(" in normalized_js_answer and "reverse(" not in normalized_js_answer:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 10,
                "efficiency_max": 10,
                "readability_max": 10,
                "structure_max": 12,
                "feedback": "Sorting the array does not reverse its order.",
                "suggestion": "Use reverse() on the array (or a copied array) to return the elements in reverse order."
            })
        if "returnlst;" in normalized_js_answer and "reverse(" not in normalized_js_answer:
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 16,
                "efficiency_max": 12,
                "feedback": "Returning the original list does not reverse its order.",
                "suggestion": "Reverse the list before returning it."
            })
    if language == "javascript" and "array is empty" in question_text and re.search(r"return\s*!arr\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Checking !arr does not tell you whether an array is empty, because empty arrays are still truthy in JavaScript.",
            "suggestion": "Check arr.length === 0 to determine whether the array has no elements."
        })
    if language == "javascript" and "index as key" in question_text and "object" in question_text and re.search(r"return\s+\{\s*\}\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning an empty object does not convert the array into an object with index keys.",
            "suggestion": "Build an object that maps each index to its corresponding array value."
        })
    if language == "javascript" and "null/undefined" in question_text and "filter(boolean)" in (student_answer or "").lower().replace(" ", ""):
        findings.append({
            "type": "correctness_cap",
            "rule_score": 40,
            "correctness_max": 40,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "filter(Boolean) removes all falsy values, not just null and undefined, so values like 0 or an empty string would also be dropped.",
            "suggestion": "Filter with x != null when the task is specifically to remove only null and undefined."
        })
    if language == "javascript" and "has property" in question_text and "object" in question_text and re.search(r"return\s+true\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns true instead of checking whether the object has the requested property.",
            "suggestion": "Use hasOwnProperty(key) or an equivalent property-existence check."
        })
    if language == "javascript" and "delay execution" in question_text and "promise" in question_text and re.search(r"return\s+ms\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the delay value does not create a Promise-based delay.",
            "suggestion": "Return a Promise that resolves after setTimeout finishes."
        })
    if language == "javascript" and "error handling" in question_text and "fetch" in (student_answer or "").lower() and "try" not in (student_answer or "").lower() and "catch" not in (student_answer or "").lower():
        findings.append({
            "type": "correctness_cap",
            "rule_score": 48,
            "correctness_max": 48,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The request logic is present, but the answer does not include the required error handling around the fetch call.",
            "suggestion": "Wrap the awaited fetch and JSON parsing in try/catch and return the required fallback on failure."
        })
    if language == "javascript" and "sorted ascending" in question_text and "arr[0]<=arr[arr.length-1]" in (student_answer or "").replace(" ", ""):
        findings.append({
            "type": "correctness_cap",
            "rule_score": 24,
            "correctness_max": 24,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Comparing only the first and last elements does not determine whether the whole array is sorted in ascending order.",
            "suggestion": "Check every adjacent pair and return false when a later value is smaller than the previous one."
        })
    if language == "javascript" and "deep clone" in question_text and "object" in question_text and re.search(r"return\s+obj\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original object does not create a deep clone.",
            "suggestion": "Create a new independent object copy instead of returning the same reference."
        })
    if language == "javascript" and "memoize" in question_text and re.search(r"return\s+fn\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original function does not implement memoization.",
            "suggestion": "Wrap the function with a cache so repeated inputs reuse stored results."
        })
    if language == "javascript" and "custom map function" in question_text and re.search(r"return\s+this\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original array does not apply the callback to build a mapped result.",
            "suggestion": "Create a new array and push the callback result for each element."
        })
    if language == "javascript" and "promise chain execution" in question_text and re.search(r"return\s+1\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning a plain value does not implement the required Promise chain.",
            "suggestion": "Return a chained Promise sequence that performs the required steps with then(...)."
        })
    if language == "javascript" and "retry api call" in question_text and re.search(r"return\s+fn\(\)\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 20,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Calling the function once is a start, but this does not implement the required retry behavior.",
            "suggestion": "Retry the call up to the required number of attempts and stop only when one succeeds."
        })
    if language == "javascript" and "event loop order" in question_text and "settimeout" in question_text and "promise" in question_text and all(
        snippet in (student_answer or "").replace(" ", "")
        for snippet in ("console.log(1);", "console.log(2);", "console.log(3);", "console.log(4);")
    ) and "setTimeout" not in (student_answer or "") and "Promise.resolve" not in (student_answer or ""):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The answer logs values directly but does not demonstrate the event-loop order between setTimeout and Promise microtasks.",
            "suggestion": "Include both setTimeout(...) and Promise.resolve().then(...) so the output order reflects the event loop behavior."
        })
    if language == "javascript" and "debounce" in question_text and "immediate" in question_text and re.search(r"return\s+fn\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original function does not implement debouncing or the immediate-execution option.",
            "suggestion": "Wrap the function in a debounce closure and handle the immediate flag when deciding whether to call it right away."
        })
    if language == "javascript" and "flatten nested object" in question_text and re.search(r"return\s+obj\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original object does not flatten nested keys into a flat result.",
            "suggestion": "Traverse nested properties and build flattened keys in the output object."
        })
    if language == "javascript" and "currying function" in question_text and re.search(r"return\s+fn\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original function does not transform it into a curried function.",
            "suggestion": "Return nested functions that collect arguments before calling the original function."
        })
    if language == "javascript" and "lru cache" in question_text and "class" in (student_answer or "").lower() and "constructor" in (student_answer or "").lower() and "get(" not in (student_answer or "").lower() and "put(" not in (student_answer or "").lower():
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The class only stores the capacity and does not implement the required LRU cache operations.",
            "suggestion": "Implement both get and put behavior with eviction of the least recently used entry."
        })
    if language == "javascript" and "function is async" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the target function is async.",
            "suggestion": "Inspect the function metadata, such as its constructor name, before returning the result."
        })
    if language == "javascript" and ("once()" in question_text or "once function" in question_text or "implement once" in question_text) and re.search(r"return\s+fn\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original function does not limit execution to a single call.",
            "suggestion": "Wrap the function so it runs only the first time and ignores later calls."
        })
    if language == "javascript" and "unique characters" in question_text and "string" in question_text and re.search(r"return\s+s\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original string does not remove duplicate characters.",
            "suggestion": "Keep only unique characters and return the deduplicated string."
        })
    if language == "javascript" and "contains duplicates" in question_text and "array" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the array contains duplicate values.",
            "suggestion": "Compare the Set size with the array length or track seen values and return true when a duplicate appears."
        })
    if language == "javascript" and "duplicates" in question_text and "array" in question_text and "newset(arr).length" in (student_answer or "").lower().replace(" ", ""):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Set objects use .size, not .length, so this duplicate check does not work as intended.",
            "suggestion": "Compare new Set(arr).size with arr.length to detect duplicates."
        })
    if language == "javascript" and "capitalize first letter" in question_text and "string" in question_text and re.search(r"return\s+s\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original string does not capitalize its first letter.",
            "suggestion": "Uppercase the first character and concatenate the rest of the string."
        })
    if language == "javascript" and "flatten nested array" in question_text and re.search(r"return\s+arr\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original array does not flatten nested arrays into a single-level result.",
            "suggestion": "Flatten the nested structure, for example with arr.flat(Infinity) or an equivalent recursive approach."
        })
    if language == "javascript" and "flatten nested array" in question_text and ".flat()" in (student_answer or "").lower() and "infinity" not in (student_answer or "").lower():
        findings.append({
            "type": "correctness_cap",
            "rule_score": 48,
            "correctness_max": 48,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using flat() without Infinity only flattens one level, so deeper nesting is still left in the result.",
            "suggestion": "Use arr.flat(Infinity) or a recursive approach when the task expects fully nested arrays to be flattened."
        })
    if language == "javascript" and "contains substring" in question_text and "string" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the string contains the substring.",
            "suggestion": "Use includes(sub) or an equivalent substring search."
        })
    if language == "javascript" and "group array elements by value" in question_text and re.search(r"return\s+\{\s*\}\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning an empty object does not group the array elements by value.",
            "suggestion": "Build an object whose keys are the values and whose entries collect the matching elements."
        })
    if language == "javascript" and "first non-repeating character" in question_text and re.search(r"return\s+s\s*\[\s*0\s*\]\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning only the first character does not find the first non-repeating character.",
            "suggestion": "Check character frequencies or compare first and last positions before returning the first unique character."
        })
    if language == "javascript" and "first unique character" in question_text and re.search(r"return\s+null\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning null immediately does not search for the first unique character.",
            "suggestion": "Scan the string and return the first character whose first and last positions are the same."
        })
    if language == "javascript" and "two arrays are equal" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of comparing whether the two arrays are equal.",
            "suggestion": "Compare the arrays element by element or use an equivalent full-array equality check."
        })
    if language == "javascript" and ("async function" in question_text or "fetch data" in question_text) and re.search(r"return\s+fetch\s*\(", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Calling fetch is a start, but this answer does not await the request or return the parsed response data as the task expects.",
            "suggestion": "Make the function async, await fetch(...), and return the parsed response body."
        })
    if language == "javascript" and "fetch json" in question_text and re.search(r"return\s+fetch\s*\(", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "correctness_cap",
            "rule_score": 24,
            "correctness_max": 24,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Calling fetch is a start, but this answer does not parse and return the JSON response.",
            "suggestion": "Await fetch(...), then await res.json() and return the parsed data."
        })
    if language == "javascript" and "throttle" in question_text and re.search(r"return\s+fn\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original function does not implement throttling behavior.",
            "suggestion": "Wrap the function in a rate-limiting closure that blocks repeated calls until the throttle interval passes."
        })
    if language == "javascript" and "frequency" in question_text and re.search(r"return\s+\{\s*\}\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning an empty object does not count the frequency of the array elements.",
            "suggestion": "Count how many times each value appears and return those counts in an object."
        })
    if language == "javascript" and "fetch api" in question_text and "get request" in question_text and re.search(r"return\s+fetch\s*\(", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Calling fetch is a start, but this answer does not handle the response body as the task expects.",
            "suggestion": "Await the fetch call and return the parsed response data, for example with res.json()."
        })
    if language == "javascript" and "key exists" in question_text and "object" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the key exists in the object.",
            "suggestion": "Use key in obj or an equivalent property-existence check."
        })
    if language == "javascript" and "debounce" in question_text and re.search(r"return\s+fn\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original function does not implement debouncing behavior.",
            "suggestion": "Wrap the function in a timer-based closure that delays execution and clears the previous timeout."
        })
    if language == "javascript" and "debounce" in question_text and "settimeout" in (student_answer or "").lower() and "cleartimeout" not in (student_answer or "").lower():
        findings.append({
            "type": "correctness_cap",
            "rule_score": 32,
            "correctness_max": 32,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using setTimeout alone delays calls, but without clearTimeout it does not actually debounce repeated invocations.",
            "suggestion": "Store the timeout id and clear the previous timeout before scheduling a new one."
        })
    if language == "javascript" and "remove duplicates" in question_text and "array" in question_text and "indexof" in (student_answer or "").lower() and "===i" in (student_answer or "").replace(" ", "").lower():
        findings.append({
            "type": "correct_solution_with_penalty",
            "rule_score": 85,
            "feedback": "The function correctly removes duplicates from the array, though this approach is less efficient than using a Set for larger inputs.",
            "suggestion": "Consider using a Set when you want a shorter and typically more efficient uniqueness check."
        })
    if language == "javascript" and "object is empty" in question_text and "object.keys(obj).length==0" in normalized_js_answer:
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly checks whether the object is empty.",
            "suggestion": ""
        })
    if language == "javascript" and "object is empty" in question_text and "for(letkinobj)returnfalse;returntrue;" in normalized_js_answer:
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly checks whether the object is empty.",
            "suggestion": ""
        })
    if language == "javascript" and "object is empty" in question_text and "json.stringify(obj)==='{}'" in normalized_js_answer:
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly checks whether the object is empty.",
            "suggestion": ""
        })
    if language == "python" and "positive" in question_text and (">=0" in code or ">= 0" in code):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function checks for non-negative numbers instead of strictly positive numbers.",
            "suggestion": "Return true only when the number is greater than zero."
        })

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
            "type": "hard_fail",
            "correctness_max": 8,
            "efficiency_max": 8,
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


def analyze_css_submission_rules(question, student_answer):
    return _generic_requirement_findings(question, student_answer, "css")


def analyze_react_submission_rules(question, student_answer):
    return _generic_requirement_findings(question, student_answer, "react")


def analyze_mysql_submission_rules(question, student_answer):
    return _generic_requirement_findings(question, student_answer, "mysql")


def analyze_mongodb_submission_rules(question, student_answer):
    return _generic_requirement_findings(question, student_answer, "mongodb")


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

    if (
        "factorial" in question_text
        and _requires_recursion(question_text)
        and method_name
        and f"{method_name}(" not in lowered.split("return", 1)[-1]
        and ("for(" in lowered or "while(" in lowered or "*=" in lowered or re.search(r"return\s+[a-z_][a-z0-9_]*\s*\*\s*[a-z_][a-z0-9_]*", lowered))
    ):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 15,
            "feedback": "The method computes factorial values, but it does not use recursion as required by the question.",
            "suggestion": "Use a base case and a recursive call to the same method if recursion is required."
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

    if "armstrong" in question_text and re.search(r"return\s+true\s*;", lowered):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The method always returns true instead of checking whether the number is an Armstrong number.",
            "suggestion": "Compute the required digit-power sum and compare it with the original number."
        })

    java_digit_char_check = (
        ".tochararray()" in lowered
        and (
            re.search(r"c\s*<\s*'0'\s*\|\|\s*c\s*>\s*'9'", lowered)
            or re.search(r"c\s*>\s*'9'\s*\|\|\s*c\s*<\s*'0'", lowered)
        )
        and "return false" in lowered
        and "return true" in lowered
    )

    if ("only digits" in question_text or "digit" in question_text) and re.search(r"return\s+true\s*;", lowered):
        if not (("integer.parseint" in lowered and "catch" in lowered) or java_digit_char_check):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 2,
                "efficiency_max": 2,
                "readability_max": 5,
                "structure_max": 8,
                "feedback": "The method always returns true instead of checking whether the string contains only digits.",
                "suggestion": "Use matches(\"\\\\d+\") or an equivalent digit check."
            })

    if ("only digits" in question_text or "digit" in question_text) and (
        ".length()>0" in lowered or ".length() > 0" in lowered
    ):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Checking only whether the string is non-empty does not determine whether it contains only digits.",
            "suggestion": "Use matches(\"\\\\d+\") or an equivalent digit-only check for every character."
        })

    if "positive" in question_text and (">= 0" in code or ">=0" in code):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
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

    if "remove spaces" in question_text and (
        '.replace(" ", "")' in code
        or (".replaceall(" in lowered and "\\s+" in lowered and '""' in lowered)
    ):
        findings.append({
            "type": "feedback_only",
            "feedback": "The method correctly removes spaces from the input string.",
        })

    if "average of array" in question_text and re.search(r"return\s+[a-z_][a-z0-9_]*\s*/\s*arr\.length\s*;", lowered):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 18,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The method divides by arr.length, but integer division loses the fractional part before returning the result.",
            "suggestion": "Cast the sum or the divisor to double before division so the average keeps its decimal value."
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
        "abstract class" in question_text
        and "shape" in question_text
        and "circle" in question_text
        and "area" in question_text
        and "abstract class" not in lowered
        and "r*r" in lowered
        and "math.pi" not in lowered
    ):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "The answer misses the required abstract Shape design and the Circle area formula is also incorrect.",
            "suggestion": "Make Shape abstract and implement Circle.area() with Math.PI * r * r."
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

    if (
        "using set" in question_text
        and re.search(r"return\s+l\s*;", student_answer or "", re.IGNORECASE)
    ):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "The method returns the original list instead of removing duplicates with a Set-based approach.",
            "suggestion": "Build and return a new list from a Set or distinct-based result."
        })

    if (
        "intersection of two arrays" in question_text
        and "for(" in lowered
        and "for(" in lowered.split("for(", 1)[-1]
        and "res.add(" in lowered
        and "hashset" not in lowered
        and "set<" not in lowered
    ):
        findings.append({
            "type": "correctness_cap",
            "correctness_min": 20,
            "correctness_max": 24,
            "efficiency_max": 10,
            "readability_min": 8,
            "readability_max": 12,
            "structure_min": 10,
            "structure_max": 12,
            "feedback": "The method can find shared values, but nested loops can add duplicates and do not control the intersection result carefully.",
            "suggestion": "Use a HashSet for membership checks and control duplicates in the intersection output."
        })

    if "add two numbers" in question_text and (
        re.search(r"return\s+a\s*;", student_answer or "", re.IGNORECASE)
        or re.search(r"return\s+b\s*;", student_answer or "", re.IGNORECASE)
    ):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The method returns only one input value instead of adding the two numbers.",
            "suggestion": "Return the sum of both inputs, such as a + b."
        })

    return findings



def analyze_submission_rules(question, student_answer, language):
    language = (language or "").lower()
    generic_findings = _generic_requirement_findings(question, student_answer, language)
    question_text = (question or "").lower()

    if language == "java":
        return generic_findings + _analyze_java_submission_rules(question, student_answer)
    if language == "javascript":
        lowered_student = (student_answer or "").lower()
        findings = list(generic_findings)
        findings.extend(analyze_javascript_string_rules(question_text, student_answer, lowered_student))
        findings.extend(analyze_javascript_list_rules(question_text, student_answer, lowered_student))
        findings.extend(analyze_javascript_number_rules(question_text, student_answer, lowered_student))
        return findings
    if language != "python":
        return generic_findings

    tree = _safe_parse_python(student_answer)
    functions = _function_nodes(tree)
    function_node = _find_function_node(functions, "grade", "safe_div", "remove_dup", "is_num")
    if function_node is None:
        return generic_findings

    findings = list(generic_findings)
    helper_map = {
        "_contains_lowercase_vowel_membership": _contains_lowercase_vowel_membership,
        "_has_lower_or_casefold": _has_lower_or_casefold,
        "_returns_constant_bool": _returns_constant_bool,
        "_uses_sorted_call": _uses_sorted_call,
        "_returns_sorted_index": _returns_sorted_index,
        "_uses_set_call": _uses_set_call,
        "_returns_list_set_call": _returns_list_set_call,
        "_returns_common_elements_listcomp_without_dedup": _returns_common_elements_listcomp_without_dedup,
        "_returns_modulus_without_comparison": _returns_modulus_without_comparison,
        "_uses_modulus_comparison_zero": _uses_modulus_comparison_zero,
    }
    findings.extend(analyze_string_rules(question_text, function_node, student_answer, helper_map))
    findings.extend(analyze_list_rules(question_text, function_node, student_answer, helper_map))
    findings.extend(analyze_number_rules(question_text, function_node, student_answer, helper_map))
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

    if "add two numbers" in question_text and _returns_name(function_node, "a", "b"):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The function returns only one input value instead of adding the two numbers.",
            "suggestion": "Return the sum of both inputs, such as a + b."
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

    if "count frequency" in question_text and "word" in question_text and _returns_dict_comp_count_split(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 12,
            "efficiency_max": 10,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Using s.count(w) on each split word does not build a proper word-frequency map and can miscount repeated tokens inefficiently.",
            "suggestion": "Split the text once, then accumulate counts in a dictionary with d[w] = d.get(w, 0) + 1."
        })

    if "prime" in question_text and "prime numbers up to" not in question_text:
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
        elif _returns_name_gt_one(function_node):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 5,
                "efficiency_max": 5,
                "readability_max": 8,
                "structure_max": 10,
                "feedback": "Checking only whether n is greater than 1 does not determine whether the number is prime.",
                "suggestion": "Test divisibility by integers up to the square root of n and return False when a divisor is found."
            })
        elif not _has_prime_lower_bound_guard(function_node):
            findings.append({
                "type": "correctness_cap",
                "correctness_max": 30,
                "efficiency_max": 15,
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

    if "factorial" in question_text and _requires_recursion(question_text) and not _has_self_recursive_call(function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 24,
            "efficiency_max": 15,
            "feedback": "The function computes factorial values, but it does not use recursion as required by the question.",
            "suggestion": "Use a base case and a recursive call to the same function if recursion is required."
        })

    if ("balanced parentheses" in question_text or ("parentheses" in question_text and "balanced" in question_text)) and _uses_count_equality(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "Counting opening and closing parentheses alone does not correctly detect balanced parentheses.",
            "suggestion": "Track the order of parentheses with a stack or a balance counter that never goes negative."
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

    if "longest word" in question_text and _returns_sorted_split_by_len_last(function_node):
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 36,
            "efficiency_max": 12,
            "readability_min": 10,
            "structure_min": 13,
            "feedback": "The function correctly returns the longest word, but sorting all words is less efficient than selecting the maximum directly.",
            "suggestion": "Use max(s.split(), key=len) to find the longest word without sorting the whole list."
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

    if "rotate" in question_text and "list" in question_text and _returns_reversed_list_slice(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 10,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Reversing the list is not the same as rotating it by k steps.",
            "suggestion": "Return the rotated list using slicing such as lst[k:] + lst[:k]."
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

    if "email" in question_text and _returns_constant_true(function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns True instead of checking whether the string satisfies the required basic email conditions.",
            "suggestion": "Check for required markers such as '@' and '.' before returning True."
        })

    if ("csv" in question_text or "file" in question_text) and "average" in question_text and _returns_constant_string(function_node, 0):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The function returns 0 instead of reading the file and calculating the requested average.",
            "suggestion": "Read the CSV or file content, extract the target values, and compute the average before returning it."
        })

    if ("read a file" in question_text or "file" in question_text) and "word" in question_text and _returns_constant_string(function_node, 0):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The function returns 0 instead of reading the file and counting its words.",
            "suggestion": "Open the file, split each line into words, and accumulate the total word count before returning it."
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

    def _finding_priority(item):
        finding_type = item.get("type")
        if finding_type == "hard_fail":
            return 3
        if finding_type in {"correctness_cap", "efficiency_cap", "correct_solution_with_penalty", "equivalent_solution"}:
            return 2
        if finding_type == "feedback_only":
            return 1
        return 0

    ordered_findings = sorted(findings, key=_finding_priority, reverse=True)

    priority_feedback = next((item["feedback"] for item in ordered_findings if item.get("feedback")), updated_feedback)
    priority_suggestion = next((item["suggestion"] for item in ordered_findings if item.get("suggestion")), updated_suggestions)

    return adjusted, priority_feedback, priority_suggestion

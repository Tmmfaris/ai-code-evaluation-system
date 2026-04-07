def analyze_list_rules(question_text, function_node, student_answer, helpers):
    findings = []

    if ("maximum" in question_text or "max" in question_text) and helpers["_uses_sorted_call"](function_node):
        findings.append({
            "type": "efficiency_cap",
            "efficiency_max": 12,
            "feedback": "The result is correct, but sorting the full list is less efficient than a direct maximum scan.",
            "suggestion": "Use max(lst) or a single-pass comparison instead of sorting the entire list."
        })

    if ("maximum" in question_text or "max" in question_text) and helpers["_returns_sorted_index"](function_node, 0):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 8,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Returning the first item from a sorted collection finds the minimum value, not the maximum.",
            "suggestion": "Return the largest value, such as max(lst), or take the last item after sorting."
        })

    if ("minimum" in question_text or "min" in question_text) and (helpers["_uses_sorted_call"](function_node) or helpers["_returns_sorted_index"](function_node, 0)):
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 34,
            "efficiency_max": 12,
            "readability_min": 5,
            "structure_min": 12,
            "feedback": "The result is correct, but sorting the full list is less efficient than finding the minimum directly.",
            "suggestion": "Use min(lst) or a single-pass comparison instead of sorting the entire list."
        })

    if "second largest" in question_text and helpers["_uses_sorted_call"](function_node) and not helpers["_uses_set_call"](function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 28,
            "efficiency_max": 12,
            "feedback": "Sorting without removing duplicates can return the largest value again instead of the second distinct largest element.",
            "suggestion": "Remove duplicates first, or track the two largest distinct values explicitly."
        })

    if "duplicate" in question_text and ("preserving order" in question_text or "preserve order" in question_text) and helpers["_returns_list_set_call"](function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 8,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Using set removes duplicates but does not preserve the original order of the list.",
            "suggestion": "Use an ordered approach such as dict.fromkeys(...) or a loop with a seen set."
        })

    if "common elements" in question_text and helpers["_returns_common_elements_listcomp_without_dedup"](function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 22,
            "efficiency_max": 10,
            "feedback": "The function can find overlapping values, but it can repeat duplicates and does not behave like a proper distinct intersection.",
            "suggestion": "Use sets or another deduping approach so common elements are returned without duplicate inflation."
        })

    return findings

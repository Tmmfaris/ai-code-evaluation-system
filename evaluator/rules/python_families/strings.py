def analyze_string_rules(question_text, function_node, student_answer, helpers):
    findings = []

    if "vowel" in question_text and helpers["_contains_lowercase_vowel_membership"](function_node) and not helpers["_has_lower_or_casefold"](function_node):
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 34,
            "efficiency_max": 15,
            "readability_min": 8,
            "structure_min": 12,
            "feedback": "The code counts lowercase vowels only and misses uppercase vowel inputs.",
            "suggestion": "Normalize the string with lower() or casefold() before checking vowels."
        })

    if "palindrome" in question_text and helpers["_returns_constant_bool"](function_node):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function returns a constant boolean instead of checking whether the string is a palindrome.",
            "suggestion": "Compare the original string with its reverse or an equivalent mirrored check."
        })

    if "count vowels" in question_text and helpers["_contains_lowercase_vowel_membership"](function_node) and not helpers["_has_lower_or_casefold"](function_node):
        findings.append({
            "type": "correct_solution_with_penalty",
            "correctness_min": 30,
            "efficiency_max": 15,
            "readability_min": 8,
            "structure_min": 12,
            "feedback": "The code counts lowercase vowels only and misses uppercase vowel inputs.",
            "suggestion": "Normalize the string or check against both lowercase and uppercase vowels."
        })

    return findings

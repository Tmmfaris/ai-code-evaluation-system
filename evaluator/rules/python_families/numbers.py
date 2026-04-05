def analyze_number_rules(question_text, function_node, student_answer, helpers):
    findings = []

    if ("even" in question_text or "divisible by" in question_text) and helpers["_returns_modulus_without_comparison"](function_node):
        findings.append({
            "type": "correctness_cap",
            "correctness_max": 12,
            "feedback": "Returning only the remainder does not directly implement the required boolean divisibility check.",
            "suggestion": "Compare the remainder to 0 so the function explicitly returns True or False."
        })

    if ("power of 2" in question_text or "power of two" in question_text) and (
        helpers["_returns_modulus_without_comparison"](function_node) or helpers["_uses_modulus_comparison_zero"](function_node)
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

    return findings

def analyze_number_rules(question_text, function_node, student_answer, helpers):
    findings = []
    normalized_student = "".join((student_answer or "").lower().split())

    if "cube" in question_text and helpers["_returns_constant_number"](function_node, 1):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "Returning a constant value does not compute the cube of the input.",
            "suggestion": "Multiply the number by itself three times, for example with n * n * n or n ** 3."
        })
    if "cube" in question_text and ("returnn+n+n" in normalized_student or "returnn+n+n;" in normalized_student):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 8,
            "efficiency_max": 8,
            "readability_max": 10,
            "structure_max": 12,
            "feedback": "Adding the number three times does not compute the cube.",
            "suggestion": "Multiply the number by itself three times, for example with n * n * n or n ** 3."
        })
    if "cube" in question_text and ("returnn*n*n" in normalized_student or "returnn**3" in normalized_student):
        findings.append({
            "type": "equivalent_solution",
            "correctness_min": 38,
            "efficiency_min": 15,
            "readability_min": 10,
            "structure_min": 12,
            "feedback": "The function correctly computes the cube using multiplication.",
            "suggestion": ""
        })

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

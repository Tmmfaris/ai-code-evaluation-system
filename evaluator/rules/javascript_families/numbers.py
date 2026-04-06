import re


def analyze_number_rules(question_text, student_answer, code):
    findings = []
    compact = (student_answer or "").replace(" ", "").lower()

    if "square of a number" in question_text or "return square of a number" in question_text:
        if "returnn*n;" in compact or "return(n*n);" in compact or "returnmath.pow(n,2);" in compact:
            findings.append({
                "type": "equivalent_solution",
                "rule_score": 100,
                "feedback": "The function correctly returns the square of the number.",
                "suggestion": ""
            })
        elif "returnn+n;" in compact:
            findings.append({
                "type": "hard_fail",
                "correctness_max": 5,
                "efficiency_max": 5,
                "readability_max": 8,
                "structure_max": 10,
                "feedback": "Adding the number to itself does not compute its square.",
                "suggestion": "Multiply the number by itself, for example with n * n or Math.pow(n, 2)."
            })
        elif re.search(r"return\s+1\s*;", student_answer or "", re.IGNORECASE):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 5,
                "efficiency_max": 5,
                "readability_max": 8,
                "structure_max": 10,
                "feedback": "Returning 1 does not compute the square of the input.",
                "suggestion": "Multiply the number by itself before returning the result."
            })

    if "add two numbers" in question_text:
        if re.search(r"return\s+a\s*;", student_answer or "", re.IGNORECASE) or re.search(r"return\s+b\s*;", student_answer or "", re.IGNORECASE):
            findings.append({
                "type": "hard_fail",
                "correctness_max": 5,
                "efficiency_max": 5,
                "readability_max": 8,
                "structure_max": 10,
                "feedback": "The function returns only one input value instead of adding the two numbers.",
                "suggestion": "Return the sum of both inputs, such as a + b."
            })

    if "even" in question_text and re.search(r"return\s+n\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the number itself does not produce a boolean even-check result.",
            "suggestion": "Return a boolean comparison such as n % 2 === 0."
        })

    if "positive" in question_text and (">=0" in code or ">= 0" in code):
        findings.append({
            "type": "correctness_cap",
            "rule_score": 48,
            "correctness_max": 48,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function checks for non-negative numbers instead of strictly positive numbers.",
            "suggestion": "Return true only when the number is greater than zero."
        })

    if "prime" in question_text and re.search(r"return\s+true\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns true instead of checking whether the number is prime.",
            "suggestion": "Reject values below 2 and test divisibility before returning true."
        })

    if "sum array" in question_text and re.search(r"return\s+0\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "Returning 0 does not calculate the sum of the array values.",
            "suggestion": "Accumulate the elements, for example with reduce((a, b) => a + b, 0)."
        })

    if "sum array" in question_text and ".reduce(" in code and ",0" not in (student_answer or "").replace(" ", ""):
        findings.append({
            "type": "correctness_cap",
            "rule_score": 52,
            "correctness_max": 52,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using reduce without an initial value works for many non-empty arrays, but it fails on empty arrays.",
            "suggestion": "Provide an initial accumulator value such as 0 so the function also handles empty arrays safely."
        })

    if "check if number is even" in question_text and re.search(r"return\s+n\s*%\s*2\s*==\s*0\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly checks whether the number is even.",
            "suggestion": ""
        })

    if "check if number is even" in question_text and re.search(r"return\s+n\s*%\s*2\s*===\s*1\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The function checks for odd numbers instead of checking whether the number is even.",
            "suggestion": "Return a boolean comparison such as n % 2 === 0."
        })

    if "even" in question_text and re.search(r"return\s+true\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The function always returns true instead of checking whether the number is even.",
            "suggestion": "Return the result of an even check such as n % 2 === 0."
        })

    return findings

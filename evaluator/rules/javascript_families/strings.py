import re


def analyze_string_rules(question_text, student_answer, code):
    findings = []

    if "reverse" in question_text and "string" in question_text and re.search(r"return\s+s\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original string does not reverse it.",
            "suggestion": "Reverse the characters before returning the result."
        })

    compact = (student_answer or "").replace(" ", "").lower()
    if "reverse" in question_text and "string" in question_text and "for(leti=s.length-1;i>=0;i--)r+=s[i];returnr;" in compact:
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly reverses the string.",
            "suggestion": ""
        })

    if "reverse" in question_text and "string" in question_text and "split('').join('')" in compact and "reverse()" not in compact:
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Splitting and joining the string without calling reverse() returns the original character order instead of reversing it.",
            "suggestion": "Call reverse() between split('') and join('') or use an equivalent reverse loop."
        })

    if "count vowels" in question_text and "string" in question_text and re.search(r"return\s+s\.length\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the string length counts every character instead of counting only the vowels.",
            "suggestion": "Check each character against the vowels and count only the matches."
        })

    if "palindrome" in question_text and re.search(r"return\s+true\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns true instead of checking whether the input is a palindrome.",
            "suggestion": "Compare the original value with its reverse or use an equivalent mirrored check."
        })

    compact = (student_answer or "").replace(" ", "")
    if "palindrome" in question_text and "s[0]" in compact and "s[s.length-1]" in compact:
        findings.append({
            "type": "correctness_cap",
            "rule_score": 28,
            "correctness_max": 28,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Checking only the first and last characters is not enough to determine whether the whole string is a palindrome.",
            "suggestion": "Compare the full string with its reverse or check every mirrored character pair."
        })

    if "starts with substring" in question_text and "string" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the string starts with the substring.",
            "suggestion": "Use startsWith(sub) or an equivalent prefix check."
        })

    if ("only digits" in question_text or "contains only digits" in question_text) and "!isnan" in code:
        findings.append({
            "type": "correctness_cap",
            "rule_score": 28,
            "correctness_max": 28,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using !isNaN(s) accepts some values that are not strings made only of digits, such as whitespace or signed or decimal forms.",
            "suggestion": "Use a digit-only check such as /^[0-9]+$/ so the entire string must consist of digits."
        })

    if "numeric" in question_text and "string" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the string is numeric.",
            "suggestion": "Use !isNaN(s) or an equivalent numeric validation check."
        })

    if "convert string to number" in question_text and "parseint" in code:
        findings.append({
            "type": "correctness_cap",
            "rule_score": 48,
            "correctness_max": 48,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "parseInt converts many integer-like strings, but it truncates decimals and can stop early instead of converting the full numeric value.",
            "suggestion": "Use Number(s) when the task asks to convert the whole string to a number."
        })

    if "anagram" in question_text and "a.length===b.length" in compact:
        findings.append({
            "type": "correctness_cap",
            "rule_score": 24,
            "correctness_max": 24,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Matching string lengths alone does not determine whether two strings are anagrams.",
            "suggestion": "Compare sorted characters or character counts so the actual letter frequencies are checked."
        })

    if "unique characters" in question_text and "string" in question_text and re.search(r"return\s+s\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original string does not remove duplicate characters.",
            "suggestion": "Keep only unique characters and return the deduplicated string."
        })

    if "capitalize first letter" in question_text and "string" in question_text and re.search(r"return\s+s\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original string does not capitalize its first letter.",
            "suggestion": "Uppercase the first character and concatenate the rest of the string."
        })

    if "contains substring" in question_text and "string" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the string contains the substring.",
            "suggestion": "Use includes(sub) or an equivalent substring search."
        })

    if "first non-repeating character" in question_text and re.search(r"return\s+s\s*\[\s*0\s*\]\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning only the first character does not find the first non-repeating character.",
            "suggestion": "Check character frequencies or compare first and last positions before returning the first unique character."
        })

    if "first unique character" in question_text and re.search(r"return\s+null\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning null immediately does not search for the first unique character.",
            "suggestion": "Scan the string and return the first character whose first and last positions are the same."
        })

    return findings

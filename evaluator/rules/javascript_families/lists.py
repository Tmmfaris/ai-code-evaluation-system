import re


def analyze_list_rules(question_text, student_answer, code):
    findings = []
    compact = code.replace(" ", "")
    is_flatten_array_question = "flatten array" in question_text or "flatten nested array" in question_text
    is_value_exists_question = (
        ("includes value" in question_text)
        or ("value exists" in question_text and "array" in question_text)
    )
    is_sum_array_question = (
        "sum array" in question_text
        or ("sum of array" in question_text)
        or ("sum" in question_text and "array" in question_text)
    )

    if ("maximum" in question_text or "max" in question_text) and "array" in question_text and re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning only the first element does not find the maximum value in the array.",
            "suggestion": "Scan the whole array or use Math.max(...arr) to return the largest value."
        })

    if ("maximum" in question_text or "max" in question_text) and "array" in question_text and "for(letxofarr)" in compact and "if(x>m)" in compact and "returnm;" in compact:
        if "letm=0" in compact or "letm =0" in code or "let m=0" in code:
            findings.append({
                "type": "correctness_cap",
                "rule_score": 70,
                "correctness_max": 28,
                "efficiency_max": 15,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The function can find the maximum for many arrays, but initializing the maximum to 0 breaks cases where all values are negative.",
                "suggestion": "Initialize the maximum from the first array element instead of 0, or use Math.max(...arr)."
            })
        elif "letm=arr[0]" in compact:
            findings.append({
                "type": "equivalent_solution",
                "rule_score": 100,
                "feedback": "The function correctly finds the maximum value in the array.",
                "suggestion": ""
            })

    if ("maximum" in question_text or "max" in question_text) and "array" in question_text and ".sort()" in code and re.search(r"\[\s*arr\.length\s*-\s*1\s*\]", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "correctness_cap",
            "rule_score": 48,
            "correctness_max": 48,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Sorting and taking the last element can work for some inputs, but JavaScript sort() compares values as strings unless you provide a numeric comparator.",
            "suggestion": "Use Math.max(...arr) or sort with a numeric comparator such as arr.sort((a, b) => a - b)."
        })

    if ("minimum" in question_text or "min" in question_text) and "array" in question_text and re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning only the first element does not find the minimum value in the array.",
            "suggestion": "Scan the whole array or use Math.min(...arr) to return the smallest value."
        })

    if "remove duplicates" in question_text and "array" in question_text and re.search(r"return\s+arr\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original array does not remove duplicate values.",
            "suggestion": "Return only distinct values, for example with [...new Set(arr)] or an equivalent uniqueness check."
        })

    if "filter even numbers" in question_text and "array" in question_text and re.search(r"return\s+arr\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original array does not filter out the odd numbers.",
            "suggestion": "Return only the even values, for example by filtering with x % 2 === 0."
        })

    if "sorted" in question_text and "array" in question_text and re.search(r"return\s+true\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns true instead of checking whether the array is sorted.",
            "suggestion": "Compare adjacent elements and return false when the order decreases."
        })

    if "sorted" in question_text and "array" in question_text and "every((v,i)=>i===0||v>=a[i-1])" in compact:
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly checks whether the array is sorted.",
            "suggestion": ""
        })

    if "sum of even numbers" in question_text and "array" in question_text and re.search(r"return\s+0\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "Returning 0 does not calculate the sum of the even numbers in the array.",
            "suggestion": "Filter the even values and add them together before returning the result."
        })

    if "array is empty" in question_text and re.search(r"return\s*!arr\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Checking !arr does not tell you whether an array is empty, because empty arrays are still truthy in JavaScript.",
            "suggestion": "Check arr.length === 0 to determine whether the array has no elements."
        })

    if "array is empty" in question_text and ("returnarr.length===0;" in compact or "return(arr.length===0);" in compact):
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly checks whether the array is empty.",
            "suggestion": ""
        })

    if "array is empty" in question_text and "return!arr.length;" in compact:
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly checks whether the array is empty.",
            "suggestion": ""
        })

    if "array is empty" in question_text and re.search(r"return\s+arr\s*==\s*\[\s*\]\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Comparing an array directly with [] does not correctly check whether it is empty in JavaScript.",
            "suggestion": "Check arr.length === 0 or use !arr.length instead."
        })

    if "array is empty" in question_text and re.search(r"return\s+true\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Always returning true does not check whether the array is empty.",
            "suggestion": "Return the result of an empty-array check such as arr.length === 0."
        })

    if "second smallest" in question_text and "arr.sort()[1]" in compact:
        findings.append({
            "type": "correctness_cap",
            "rule_score": 24,
            "correctness_max": 24,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Sorting and taking index 1 can fail because sort() is lexical without a numeric comparator, and duplicates are not removed before picking the second smallest value.",
            "suggestion": "Remove duplicates first and sort numerically, or track the two smallest distinct values directly."
        })

    if "occurrences of element" in question_text and "array" in question_text and re.search(r"return\s+0\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "Returning 0 does not count how many times the target element appears in the array.",
            "suggestion": "Filter or count the matching values and return the number of matches."
        })

    if "merge two arrays" in question_text and re.search(r"return\s+a\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning only the first array does not merge the two arrays together.",
            "suggestion": "Combine both arrays into one result, for example with [...a, ...b]."
        })

    if "remove falsy values" in question_text and "array" in question_text and re.search(r"return\s+arr\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original array does not remove falsy values from it.",
            "suggestion": "Filter the array so only truthy values remain, for example with arr.filter(Boolean)."
        })

    if "intersection of two arrays" in question_text and re.search(r"return\s+a\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning only the first array does not compute the intersection shared by both arrays.",
            "suggestion": "Return only the values that appear in both arrays."
        })

    if is_value_exists_question and "indexof" in code:
        compact_code = code.replace(" ", "")
        if "!==-1" in compact_code or "!=-1" in compact_code or ">-1" in compact_code:
            findings.append({
                "type": "equivalent_solution",
                "rule_score": 100,
                "feedback": "The function correctly checks whether the array includes the target value.",
                "suggestion": ""
            })
        else:
            findings.append({
                "type": "correctness_cap",
                "rule_score": 24,
                "correctness_max": 24,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "Returning indexOf(x) gives a numeric index, not a boolean result, and -1 does not behave like false in all contexts.",
                "suggestion": "Compare the index against -1 or use arr.includes(x) so the function returns true or false directly."
            })

    if "sum of odd numbers" in question_text and ".reduce(" in code and "filter" not in code:
        findings.append({
            "type": "correctness_cap",
            "rule_score": 28,
            "correctness_max": 28,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Summing the whole array does not restrict the result to odd values only.",
            "suggestion": "Filter for odd numbers before reducing, or add only the odd elements during accumulation."
        })

    if "contains duplicates" in question_text and "array" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of checking whether the array contains duplicate values.",
            "suggestion": "Compare the Set size with the array length or track seen values and return true when a duplicate appears."
        })

    if "duplicates" in question_text and "array" in question_text and "newset(arr).length" in compact:
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Set objects use .size, not .length, so this duplicate check does not work as intended.",
            "suggestion": "Compare new Set(arr).size with arr.length to detect duplicates."
        })

    if is_flatten_array_question and re.search(r"return\s+arr\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning the original array does not flatten nested arrays into a single-level result.",
            "suggestion": "Flatten the nested structure, for example with arr.flat(Infinity) or an equivalent recursive approach."
        })

    if is_flatten_array_question and ".flat()" in code and "infinity" not in code:
        findings.append({
            "type": "correctness_cap",
            "rule_score": 70,
            "correctness_max": 28,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using flat() without Infinity only flattens one level, so deeper nesting is still left in the result.",
            "suggestion": "Use arr.flat(Infinity) or a recursive approach when the task expects fully nested arrays to be flattened."
        })

    if is_flatten_array_question and ".reduce(" in code and ".concat(" in code and "flat(b)" in compact and ",[])" in compact:
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly flattens the array.",
            "suggestion": ""
        })

    if "group array elements by value" in question_text and re.search(r"return\s+\{\s*\}\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning an empty object does not group the array elements by value.",
            "suggestion": "Build an object whose keys are the values and whose entries collect the matching elements."
        })

    if "two arrays are equal" in question_text and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 2,
            "efficiency_max": 2,
            "readability_max": 5,
            "structure_max": 8,
            "feedback": "The function always returns false instead of comparing whether the two arrays are equal.",
            "suggestion": "Compare the arrays element by element or use an equivalent full-array equality check."
        })

    if is_value_exists_question and re.search(r"return\s+false\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "The function always returns false instead of checking whether the array includes the target value.",
            "suggestion": "Use includes(...) or scan the array and return true when a match is found."
        })

    if is_value_exists_question and re.search(r"arr\s*\[\s*0\s*\]\s*={2,3}\s*x", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Checking only the first array element does not determine whether the array includes the target value anywhere.",
            "suggestion": "Use includes(...) or scan every element until a match is found."
        })

    if is_sum_array_question and "for(letxofarr)" in code.replace(" ", "") and "+=" in code and re.search(r"return\s+s\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "equivalent_solution",
            "rule_score": 100,
            "feedback": "The function correctly calculates the sum of the array values.",
            "suggestion": ""
        })

    if is_sum_array_question and re.search(r"return\s+arr\s*\[\s*0\s*\]\s*;", student_answer or "", re.IGNORECASE):
        findings.append({
            "type": "hard_fail",
            "correctness_max": 5,
            "efficiency_max": 5,
            "readability_max": 8,
            "structure_max": 10,
            "feedback": "Returning only the first element does not calculate the sum of the array values.",
            "suggestion": "Loop through the array or use reduce((a, b) => a + b, 0) to add all values."
        })

    if is_sum_array_question and ".reduce(" in code and ",0" not in (student_answer or "").replace(" ", ""):
        findings.append({
            "type": "correctness_cap",
            "rule_score": 70,
            "correctness_max": 28,
            "efficiency_max": 15,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "Using reduce without an initial value works for many non-empty arrays, but it fails on empty arrays.",
            "suggestion": "Provide an initial accumulator value such as 0 so the function also handles empty arrays safely."
        })

    return findings

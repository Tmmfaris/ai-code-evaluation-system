def _contains(question_text, *parts):
    return all(part in (question_text or "") for part in parts)


def evaluate_number_family(question, question_text, families, normalized_student, student_answer):
    if _contains(question_text, "subtract", "two", "numbers"):
        if "returna-b" in normalized_student:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly subtracts the second number from the first.",
            }
        if "returna+b" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Adding the two numbers does not perform subtraction.",
                "suggestion": "Return a - b to compute the difference.",
            }
        if "returnb-a" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Reversing the operands changes the subtraction result.",
                "suggestion": "Subtract the second number from the first: a - b.",
            }

    if _contains(question_text, "multiply", "two", "numbers") or _contains(question_text, "product", "two", "numbers"):
        if "returna*b" in normalized_student:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly computes the product of the two numbers.",
            }
        if "returna+b" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Adding the numbers does not compute their product.",
                "suggestion": "Use multiplication: a * b.",
            }
        if "returna-b" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Subtracting the numbers does not compute their product.",
                "suggestion": "Use multiplication: a * b.",
            }

    if _contains(question_text, "divide", "two", "numbers") or _contains(question_text, "division", "two", "numbers"):
        if "returna/b" in normalized_student:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly divides the first number by the second.",
            }
        if "returna*b" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Multiplication does not compute the quotient.",
                "suggestion": "Use division: a / b.",
            }
        if "returna+b" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "Adding the numbers does not compute the quotient.",
                "suggestion": "Use division: a / b.",
            }

    if _contains(question_text, "odd") and _contains(question_text, "number"):
        if "returnn%2!=0" in normalized_student or "returnn%2==1" in normalized_student:
            return {
                "result_type": "full_pass",
                "correctness_min": 36,
                "feedback": "The function correctly checks whether the number is odd.",
            }
        if "returnn%2==0" in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "This checks even numbers instead of odd numbers.",
                "suggestion": "Use a modulo check for oddness, such as n % 2 != 0.",
            }
        if normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
            return {
                "result_type": "zero_pass",
                "correctness_max": 5,
                "efficiency_max": 5,
                "feedback": "The function always returns True instead of checking whether the number is odd.",
                "suggestion": "Return the result of an actual odd-number check.",
            }

    if _contains(question_text, "even") and "returnn%2==0ifn>0elsefalse" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function excludes 0 and negative even numbers, so it misses valid even inputs that should return True.",
            "suggestion": "Check whether n % 2 == 0 directly without restricting the sign of n.",
        }

    if _contains(question_text, "zero") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is zero.",
            "suggestion": "Return a boolean expression such as n == 0.",
        }

    if _contains(question_text, "zero") and "returnnotn" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the number is zero.",
        }

    if _contains(question_text, "zero") and "returnn>0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function checks whether the number is greater than zero instead of checking whether it is exactly zero.",
            "suggestion": "Return a boolean expression such as n == 0.",
        }

    if _contains(question_text, "negative") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is negative.",
            "suggestion": "Return a boolean expression such as n < 0.",
        }

    if _contains(question_text, "negative") and ("<=0" in (student_answer or "") or "<= 0" in (student_answer or "")):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function treats zero as negative, so it misses the strict negative-number requirement.",
            "suggestion": "Return true only when the number is less than zero.",
        }

    if _contains(question_text, "negative") and "returnnot(n>0)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function also returns True for zero, so it does not enforce the strict negative-number check.",
            "suggestion": "Return true only when the number is less than zero.",
        }

    if _contains(question_text, "double") and "returnn+n" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly doubles the input number.",
        }

    if _contains(question_text, "double") and "returnn*3" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Multiplying by 3 does not double the input number.",
            "suggestion": "Multiply by 2 or add the number to itself.",
        }

    if _contains(question_text, "double") and normalized_student.endswith("returnn"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning the input unchanged does not double the number.",
            "suggestion": "Multiply by 2 or add the number to itself.",
        }

    if "armstrong" in families and "returnn>0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking whether the number is positive does not determine whether it is an Armstrong number.",
            "suggestion": "Raise each digit to the power of the number of digits, sum those values, and compare the result with the original number.",
        }

    if _contains(question_text, "square") and "returnn**2" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the square of the input number.",
        }

    if _contains(question_text, "square") and "returnabs(n)*abs(n)" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the square of the input number.",
        }

    if _contains(question_text, "square") and "returnn+n" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Adding the number to itself doubles it instead of squaring it.",
            "suggestion": "Multiply the number by itself, for example with n * n or n ** 2.",
        }

    if _contains(question_text, "multiple of 5") and "returnnotn%5" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the number is a multiple of 5.",
        }

    if _contains(question_text, "multiple of 5") and "returnn%5==0ifn>0elsefalse" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function excludes 0 and negative multiples of 5, so it misses valid cases that should return True.",
            "suggestion": "Check whether n % 5 == 0 directly without restricting the sign of n.",
        }

    if _contains(question_text, "multiple of 5") and "returnn%2==0" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking whether the number is a multiple of 2 does not determine whether it is a multiple of 5.",
            "suggestion": "Use a modulo-5 check such as n % 5 == 0.",
        }

    if (
        (_contains(question_text, "divisible by 3") or _contains(question_text, "multiple of 3"))
        and ("returnnotn%3" in normalized_student or "returnn%3==0" in normalized_student)
    ):
        if "returnn%3==0ifnelsefalse" in normalized_student or "returnn%3==0ifn!=0elsefalse" in normalized_student:
            return {
                "result_type": "mostly_correct",
                "correctness_max": 16,
                "efficiency_max": 12,
                "readability_max": 12,
                "structure_max": 12,
                "feedback": "The function incorrectly returns False for 0, but 0 is also divisible by 3.",
                "suggestion": "Check whether n % 3 == 0 directly without treating 0 as a special false case.",
            }
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly checks whether the number is divisible by 3.",
        }

    if (_contains(question_text, "divisible by 3") or _contains(question_text, "multiple of 3")) and "returnn%3==1" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking whether the remainder is 1 does not determine whether the number is divisible by 3.",
            "suggestion": "Use a modulo-3 check such as n % 3 == 0.",
        }

    if (_contains(question_text, "divisible by 3") or _contains(question_text, "multiple of 3")) and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is divisible by 3.",
            "suggestion": "Use a modulo-3 check such as n % 3 == 0.",
        }

    if _contains(question_text, "greater than 10") and (">=10" in (student_answer or "") or ">= 10" in (student_answer or "")):
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "The function treats 10 as satisfying the condition, so it misses the strict greater-than requirement.",
            "suggestion": "Return True only when the number is strictly greater than 10.",
        }

    if _contains(question_text, "greater than 10") and "returnnot(n<10)" in normalized_student:
        return {
            "result_type": "mostly_correct",
            "correctness_max": 16,
            "efficiency_max": 12,
            "readability_max": 12,
            "structure_max": 12,
            "feedback": "This logic also returns True for 10, so it does not enforce the strict greater-than-10 check.",
            "suggestion": "Use a direct strict comparison such as n > 10.",
        }

    if _contains(question_text, "greater than 10") and normalized_student.endswith("returntrue") and "returnfalse" not in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "The function always returns True instead of checking whether the number is greater than 10.",
            "suggestion": "Use a comparison such as n > 10.",
        }

    if _contains(question_text, "sum of digits") and "whilen>0" in normalized_student and "s+=n%10" in normalized_student and "n//=" in normalized_student and "returns" in normalized_student:
        return {
            "result_type": "full_pass",
            "correctness_min": 36,
            "feedback": "The function correctly calculates the sum of the digits.",
        }

    if "factorial" in families and normalized_student.endswith("returnn"):
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Returning n does not compute the factorial of the input.",
            "suggestion": "Use a factorial base case and multiply through recursive or iterative calls before returning the result.",
        }

    if "prime_check" in families and "returnn>1" in normalized_student:
        return {
            "result_type": "zero_pass",
            "correctness_max": 5,
            "efficiency_max": 5,
            "feedback": "Checking only whether n is greater than 1 does not determine whether the number is prime.",
            "suggestion": "Test divisibility by integers up to the square root of n and return False when a divisor is found.",
        }

    return None

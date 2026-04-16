def build_exact_match_feedback(question, language):
    lowered = (question or "").lower()
    language = (language or "").lower()
    noun = "method" if language == "java" else ("function" if language == "python" else "solution")

    if "add two numbers" in lowered:
        return f"The student answer exactly matches the expected {noun} for adding two numbers."
    if "sum of all elements" in lowered or "sum elements" in lowered:
        return f"The student answer exactly matches the expected {noun} for summing all elements."
    if "sum of digits" in lowered or "sum digits" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating the sum of digits."
    if "count words" in lowered:
        return f"The student answer exactly matches the expected {noun} for counting words."
    if "even" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking even numbers."
    if "reverse" in lowered and "string" in lowered:
        return f"The student answer exactly matches the expected {noun} for reversing a string."
    if "reverse" in lowered and "list" in lowered:
        return f"The student answer exactly matches the expected {noun} for reversing a list."
    if "remove spaces" in lowered:
        return f"The student answer exactly matches the expected {noun} for removing spaces."
    if "remove duplicates" in lowered or "duplicate" in lowered:
        return f"The student answer exactly matches the expected {noun} for removing duplicates."
    if "check" in lowered and "lowercase" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking lowercase text."
    if "lowercase" in lowered:
        return f"The student answer exactly matches the expected {noun} for converting text to lowercase."
    if "convert" in lowered and "uppercase" in lowered:
        return f"The student answer exactly matches the expected {noun} for converting text to uppercase."
    if "uppercase" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking uppercase text."
    if "square" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating a square."
    if "cube" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating a cube."
    if "minimum" in lowered or "min" in lowered:
        return f"The student answer exactly matches the expected {noun} for finding the minimum value."
    if "maximum" in lowered or "max" in lowered:
        return f"The student answer exactly matches the expected {noun} for finding the maximum value."
    if "palindrome" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking palindromes."
    if "only digits" in lowered or "isdigit" in lowered or "numeric" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking digit-only text."
    if "factorial" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating factorial."
    if "prime" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking prime numbers."

    return f"The student answer exactly matches the expected {noun} and is fully correct."


def build_exact_match_result(question, language, structure_analysis):
    line_count = structure_analysis.get("line_count", 0) if isinstance(structure_analysis, dict) else 0
    readability = 15 if line_count <= 6 else 13

    return {
        "score": 0,
        "feedback": build_exact_match_feedback(question, language),
        "improvements": "",
        "rubric": {
            "correctness": 40,
            "efficiency": 20,
            "readability": readability,
            "structure": 15,
        },
    }


def build_syntax_error_result(syntax_result):
    message = (syntax_result or {}).get("error", "Syntax error")
    line = (syntax_result or {}).get("line")
    detail = f"{message} on line {line}" if line else message

    return {
        "score": 0,
        "feedback": f"The code has a syntax error and cannot be evaluated correctly: {detail}.",
        "improvements": "Fix the syntax error before resubmitting the answer.",
        "rubric": {
            "correctness": 0,
            "efficiency": 0,
            "readability": 5,
            "structure": 5,
        },
    }


def choose_hybrid_feedback(
    llm_result,
    execution_finding,
    syntax_result,
    language,
    question="",
    template_family="",
):
    if language in {"python", "java", "html", "javascript"} and not syntax_result.get("valid", True):
        syntax_result = build_syntax_error_result(syntax_result)
        return syntax_result["feedback"], syntax_result["improvements"]

    if execution_finding and execution_finding.get("feedback"):
        return execution_finding.get("feedback", ""), execution_finding.get("suggestion", "")

    from evaluator.comparison import feedback_generator

    return (
        feedback_generator.choose_safe_feedback(
            llm_result.get("feedback", ""),
            "",
            question=question,
            language=language,
            template_family=template_family,
        ),
        feedback_generator.choose_safe_improvement(
            llm_result.get("improvements", ""),
            "",
            question=question,
            language=language,
            template_family=template_family,
        ),
    )

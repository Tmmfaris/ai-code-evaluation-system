def build_logic_evaluation(
    sample_answer,
    student_answer,
    execution_finding=None,
    syntax_result=None,
    findings=None,
):
    if syntax_result and not syntax_result.get("valid", True):
        return "The student logic could not be evaluated normally because the code has a syntax error."

    result_type = (execution_finding or {}).get("result_type")
    normalized_sample = (sample_answer or "").strip()
    normalized_student = (student_answer or "").strip()
    same_answer = normalized_sample and normalized_sample == normalized_student

    if same_answer:
        return "The student answer matches the model answer, and the logic is correct."

    if findings:
        for item in findings:
            if item.get("type") == "hard_fail":
                return "The student logic does not correctly solve the problem yet."

    if result_type == "full_pass":
        return "The student used a different approach, but the logic is correct."
    if result_type == "mostly_correct":
        return "The student logic is mostly correct, but it misses an important requirement or edge case."
    if result_type == "correct_but_inefficient":
        return "The student logic is correct, but the approach is less efficient than the model answer."
    if result_type == "partial_pass":
        pass_ratio = float((execution_finding or {}).get("pass_ratio") or 0.0)
        if pass_ratio >= 0.5:
            return "The student logic is mostly correct, but it misses an important requirement or edge case."
        return "The student logic is partially correct, but the solution is not fully correct yet."
    if result_type in {"zero_pass", "execution_error"}:
        return "The student logic does not correctly solve the problem yet."

    if findings:
        for item in findings:
            if item.get("type") == "correct_solution_with_penalty":
                return "The student logic is correct, but the approach is less efficient than the model answer."
            if item.get("type") in {"correctness_cap", "efficiency_cap"}:
                return "The student logic is mostly correct, but it misses an important requirement or edge case."

    if normalized_student and normalized_sample and normalized_student != normalized_sample:
        return "The student used a different approach, but the logic was checked against the model answer."

    return "The student logic was checked against the model answer."

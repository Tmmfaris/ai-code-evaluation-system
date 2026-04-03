def normalize_score(score, concepts, rubric_score):
    logic = concepts.get("logic")
    completeness = concepts.get("completeness")
    correctness = rubric_score.get("correctness", 0) if isinstance(rubric_score, dict) else 0

    if logic == "Strong" and score < 70:
        return max(score, 70)

    if logic == "Weak" and completeness == "Low" and correctness <= 5 and score > 10:
        return min(score, 10)

    if logic == "Weak" and completeness == "Low" and score > 15:
        return min(score, 15)

    return score


def relax_readability_for_simple_correct_code(rubric_score, structure_analysis):
    if not isinstance(rubric_score, dict):
        return rubric_score

    if not isinstance(structure_analysis, dict):
        return rubric_score

    correctness = rubric_score.get("correctness", 0)
    efficiency = rubric_score.get("efficiency", 0)
    readability = rubric_score.get("readability", 0)
    structure = rubric_score.get("structure", 0)
    line_count = structure_analysis.get("line_count", 0)
    if (
        correctness >= 36
        and efficiency >= 17
        and structure >= 13
        and line_count <= 6
        and readability < 15
    ):
        rubric_score = dict(rubric_score)
        rubric_score["readability"] = 15

    return rubric_score


def infer_score_bounds(execution_finding, findings, syntax_result, language):
    if language in {"python", "java", "html", "javascript"} and not syntax_result.get("valid", True):
        return 0, 12

    min_score = 0
    max_score = 100
    result_type = (execution_finding or {}).get("result_type")

    if result_type == "full_pass":
        min_score = max(min_score, 85)
    elif result_type == "mostly_correct":
        min_score = max(min_score, 70)
        max_score = min(max_score, 90)
    elif result_type == "correct_but_inefficient":
        min_score = max(min_score, 80)
        max_score = min(max_score, 95)
    elif result_type == "partial_pass":
        min_score = max(min_score, 30)
        max_score = min(max_score, 70)
    elif result_type == "zero_pass":
        max_score = min(max_score, 12)
    elif result_type == "execution_error":
        max_score = min(max_score, 12)

    has_hard_fail = False
    for finding in findings or []:
        finding_type = finding.get("type")
        correctness_max = finding.get("correctness_max")
        if finding_type == "hard_fail":
            has_hard_fail = True
            max_score = min(max_score, 12)
        elif correctness_max is not None:
            if correctness_max <= 8:
                max_score = min(max_score, 12)
            elif correctness_max <= 14:
                max_score = min(max_score, 15)
            elif correctness_max <= 22:
                max_score = min(max_score, 70)
        if finding_type == "correct_solution_with_penalty":
            min_score = max(min_score, 75)
            max_score = min(max_score, 95)

    if has_hard_fail and max_score < min_score:
        min_score = max_score

    return min_score, max_score


def calibrate_final_score(base_score, llm_score, execution_finding, findings, syntax_result, language):
    if llm_score is None:
        return base_score

    min_score, max_score = infer_score_bounds(
        execution_finding=execution_finding,
        findings=findings,
        syntax_result=syntax_result,
        language=language,
    )
    llm_clamped = max(min_score, min(max_score, int(llm_score)))
    result_type = (execution_finding or {}).get("result_type")
    has_hard_fail = any(finding.get("type") == "hard_fail" for finding in (findings or []))
    has_strict_cap = any(
        finding.get("correctness_max") is not None and finding.get("correctness_max") <= 14
        for finding in (findings or [])
    )

    if has_hard_fail or has_strict_cap or result_type in {"zero_pass", "execution_error"}:
        return min(base_score, llm_clamped)

    if result_type in {"full_pass", "mostly_correct", "correct_but_inefficient"}:
        return max(base_score, llm_clamped)

    if result_type == "partial_pass":
        pass_ratio = (execution_finding or {}).get("pass_ratio")
        if pass_ratio is not None:
            scaled_score = int(round(float(pass_ratio) * 100))
            return max(0, min(100, scaled_score))
        return int(round((base_score + llm_clamped) / 2))

    return llm_clamped

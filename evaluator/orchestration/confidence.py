def infer_evaluation_confidence(language, syntax_result, execution_finding, question_profile=None, exact_match=False):
    language = (language or "").lower()
    profile = question_profile or {}
    risk = profile.get("risk", "medium")

    if exact_match:
        return "high"

    if syntax_result and not syntax_result.get("valid", True):
        return "high"

    result_type = (execution_finding or {}).get("result_type")
    if result_type in {"full_pass", "mostly_correct", "correct_but_inefficient", "partial_pass", "zero_pass"}:
        return "high" if language in {"python", "java"} else "medium"

    if language in {"python", "java"} and risk != "high":
        return "medium"

    if language in {"css", "react", "mongodb", "mysql"}:
        return "low" if risk == "high" else "medium"

    if language in {"javascript", "html"}:
        return "medium"

    return "low"


def infer_confidence_score(language, syntax_result, execution_finding, question_profile=None, exact_match=False):
    confidence = infer_evaluation_confidence(
        language=language,
        syntax_result=syntax_result,
        execution_finding=execution_finding,
        question_profile=question_profile,
        exact_match=exact_match,
    )
    result_type = (execution_finding or {}).get("result_type")

    if exact_match:
        return 0.99

    if syntax_result and not syntax_result.get("valid", True):
        return 0.98

    if confidence == "high":
        mapping = {
            "full_pass": 0.96,
            "correct_but_inefficient": 0.93,
            "mostly_correct": 0.9,
            "partial_pass": 0.84,
            "zero_pass": 0.97,
            "execution_error": 0.8,
        }
        return mapping.get(result_type, 0.88)

    if confidence == "medium":
        mapping = {
            "full_pass": 0.82,
            "correct_but_inefficient": 0.78,
            "mostly_correct": 0.75,
            "partial_pass": 0.68,
            "zero_pass": 0.73,
            "execution_error": 0.6,
        }
        return mapping.get(result_type, 0.7)

    mapping = {
        "full_pass": 0.7,
        "correct_but_inefficient": 0.66,
        "mostly_correct": 0.62,
        "partial_pass": 0.55,
        "zero_pass": 0.58,
        "execution_error": 0.45,
    }
    return mapping.get(result_type, 0.5)


def apply_confidence_bounds(score, confidence, execution_finding, question_profile=None):
    profile = question_profile or {}
    risk = profile.get("risk", "medium")
    result_type = (execution_finding or {}).get("result_type")

    if confidence == "high":
        return score

    if confidence == "medium":
        if result_type in {"full_pass", "mostly_correct", "correct_but_inefficient"}:
            return min(score, 92)
        if risk == "high":
            return min(score, 80)
        return min(score, 88)

    if result_type in {"full_pass", "mostly_correct", "correct_but_inefficient"}:
        return min(score, 75)
    return min(score, 65)

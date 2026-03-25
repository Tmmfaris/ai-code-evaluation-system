# =========================
# SUCCESS RESPONSE
# =========================
def format_success_response(
    student_id,
    score,
    feedback,
    strengths="",
    suggestions="",
    concepts=None
):
    """
    Formats a successful evaluation response
    """

    return {
        "status": "success",
        "student_id": student_id,
        "score": score,
        "feedback": feedback,
        "strengths": strengths,
        "suggestions": suggestions,
        "concepts": concepts or {}
    }


# =========================
# ERROR RESPONSE
# =========================
def format_error_response(student_id, message):
    """
    Formats an error response
    """

    return {
        "status": "error",
        "student_id": student_id,
        "score": 0,
        "feedback": message,
        "strengths": "",
        "suggestions": "",
        "concepts": {}
    }


# =========================
# RUBRIC RESPONSE
# =========================
def format_rubric(rubric_scores):
    """
    Ensures rubric format consistency
    """

    return {
        "correctness": rubric_scores.get("correctness", 0),
        "efficiency": rubric_scores.get("efficiency", 0),
        "readability": rubric_scores.get("readability", 0),
        "structure": rubric_scores.get("structure", 0)
    }


# =========================
# FINAL OUTPUT FORMAT
# =========================
def format_final_output(
    student_id,
    llm_result,
    rubric_scores
):
    """
    Combines LLM output + rubric into final response
    """

    return {
        "status": "success",
        "student_id": student_id,
        "score": llm_result.get("score", 0),
        "feedback": llm_result.get("feedback", ""),
        "strengths": llm_result.get("strengths", ""),
        "suggestions": llm_result.get("improvements", ""),
        "concepts": llm_result.get("concepts", {}),
        "rubric": format_rubric(rubric_scores)
    }
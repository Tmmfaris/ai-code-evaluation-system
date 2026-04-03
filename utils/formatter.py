def format_error_response(student_id, message):
    """
    Formats an error response.
    """

    return {
        "status": "error",
        "student_id": student_id,
        "score": 0,
        "feedback": message,
        "suggestions": "",
        "concepts": {},
    }



def format_rubric(rubric_scores):
    """
    Ensures rubric format consistency.
    """

    return {
        "correctness": rubric_scores.get("correctness", 0),
        "efficiency": rubric_scores.get("efficiency", 0),
        "readability": rubric_scores.get("readability", 0),
        "structure": rubric_scores.get("structure", 0),
    }



def format_final_output(student_id, llm_result, rubric_scores):
    """
    Combines LLM output and rubric into the internal evaluation response.
    """

    return {
        "status": "success",
        "student_id": student_id,
        "score": llm_result.get("score", 0),
        "logic_evaluation": llm_result.get("logic_evaluation"),
        "feedback": llm_result.get("feedback", ""),
        "suggestions": llm_result.get("improvements", ""),
        "concepts": llm_result.get("concepts", {}),
        "rubric": format_rubric(rubric_scores),
    }

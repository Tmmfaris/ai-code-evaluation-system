# evaluator/rubric_engine.py

from config import RUBRIC_WEIGHTS


# ==============================
# 🔧 SAFE VALUE HANDLER
# ==============================
def safe_score(value, max_value):
    """
    Ensures score is valid and within limits
    """
    try:
        value = int(value)
        if value < 0:
            return 0
        if value > max_value:
            return max_value
        return value
    except:
        return 0


# ==============================
# 🧠 MAIN RUBRIC FUNCTION
# ==============================
def calculate_rubric_score(llm_output):
    """
    Extracts and validates rubric scores from LLM output
    """

    default = {
        "correctness": 0,
        "efficiency": 0,
        "readability": 0,
        "structure": 0
    }

    if not isinstance(llm_output, dict):
        return default

    rubric = llm_output.get("rubric", {})

    # Extract and validate each score
    correctness = safe_score(
        rubric.get("correctness", 0),
        RUBRIC_WEIGHTS["correctness"]
    )

    efficiency = safe_score(
        rubric.get("efficiency", 0),
        RUBRIC_WEIGHTS["efficiency"]
    )

    readability = safe_score(
        rubric.get("readability", 0),
        RUBRIC_WEIGHTS["readability"]
    )

    structure = safe_score(
        rubric.get("structure", 0),
        RUBRIC_WEIGHTS["structure"]
    )

    return {
        "correctness": correctness,
        "efficiency": efficiency,
        "readability": readability,
        "structure": structure
    }
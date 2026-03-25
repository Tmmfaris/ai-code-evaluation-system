# evaluator/concept_evaluator.py

# Allowed values for standardization
VALID_LOGIC = ["Strong", "Good", "Weak"]
VALID_EDGE = ["Good", "Needs Improvement", "Needs improvement"]
VALID_COMPLETENESS = ["High", "Medium", "Low"]
VALID_EFFICIENCY = ["Good", "Average", "Poor"]
VALID_READABILITY = ["Good", "Needs Improvement", "Needs improvement"]


# ==============================
# 🔧 SAFE VALUE HANDLER
# ==============================
def normalize_value(value, valid_list, default):
    """
    Ensures the value is within allowed options
    """
    if not isinstance(value, str):
        return default

    value = value.strip()

    for v in valid_list:
        if value.lower() == v.lower():
            return v

    return default


# ==============================
# 🧠 MAIN CONCEPT EVALUATOR
# ==============================
def evaluate_concepts(llm_output):
    """
    Extracts and validates concept-level evaluation
    """

    # Default fallback
    default_result = {
        "logic": "Good",
        "edge_cases": "Needs Improvement",
        "completeness": "Medium",
        "efficiency": "Average",
        "readability": "Needs Improvement"
    }

    if not isinstance(llm_output, dict):
        return default_result

    concepts = llm_output.get("concepts", {})

    logic = normalize_value(
        concepts.get("logic"),
        VALID_LOGIC,
        "Good"
    )

    edge_cases = normalize_value(
        concepts.get("edge_cases"),
        VALID_EDGE,
        "Needs Improvement"
    )

    completeness = normalize_value(
        concepts.get("completeness"),
        VALID_COMPLETENESS,
        "Medium"
    )

    efficiency = normalize_value(
        concepts.get("efficiency"),
        VALID_EFFICIENCY,
        "Average"
    )

    readability = normalize_value(
        concepts.get("readability"),
        VALID_READABILITY,
        "Needs Improvement"
    )

    return {
        "logic": logic,
        "edge_cases": edge_cases,
        "completeness": completeness,
        "efficiency": efficiency,
        "readability": readability
    }
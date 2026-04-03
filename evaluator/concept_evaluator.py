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
    if not isinstance(value, str):
        return default
    value = value.strip()
    for v in valid_list:
        if value.lower() == v.lower():
            return v
    return default


# ==============================
# ⚡ DERIVE CONCEPTS FROM RUBRIC
# ==============================
def derive_concepts_from_rubric(rubric):
    """
    Computes concept labels from rubric scores — avoids asking LLM to output
    them (saves ~50 output tokens = ~10s decode time on CPU).
    """
    correctness = rubric.get("correctness", 0)
    efficiency  = rubric.get("efficiency",  0)
    readability = rubric.get("readability", 0)
    structure   = rubric.get("structure",   0)
    total       = correctness + efficiency + readability + structure

    return {
        "logic":        "Strong" if correctness >= 35 else ("Good" if correctness >= 25 else "Weak"),
        "edge_cases":   "Good"   if correctness >= 35 else "Needs Improvement",
        "completeness": "High"   if total >= 72        else ("Medium" if total >= 50 else "Low"),
        "efficiency":   "Good"   if efficiency  >= 17  else ("Average" if efficiency  >= 10 else "Poor"),
        "readability":  "Good"   if readability >= 13  else "Needs Improvement",
    }


def derive_concepts_from_execution(execution_finding, rubric):
    result_type = ((execution_finding or {}).get("result_type") or "").strip()
    if not result_type:
        return None

    concepts = derive_concepts_from_rubric(rubric or {})

    if result_type == "full_pass":
        concepts["logic"] = "Strong"
        concepts["edge_cases"] = "Good"
        concepts["completeness"] = "High"
        return concepts

    if result_type == "correct_but_inefficient":
        concepts["logic"] = "Strong"
        concepts["edge_cases"] = "Good"
        concepts["completeness"] = "High"
        concepts["efficiency"] = "Average"
        return concepts

    if result_type == "mostly_correct":
        concepts["logic"] = "Good"
        if concepts["completeness"] == "Low":
            concepts["completeness"] = "Medium"
        return concepts

    if result_type == "partial_pass":
        pass_ratio = float((execution_finding or {}).get("pass_ratio") or 0.0)
        if pass_ratio >= 0.5:
            concepts["logic"] = "Good"
            concepts["completeness"] = "Medium"
        else:
            concepts["logic"] = "Weak"
        return concepts

    if result_type in {"zero_pass", "execution_error"}:
        concepts["logic"] = "Weak"
        return concepts

    return concepts


# ==============================
# 🧠 MAIN CONCEPT EVALUATOR
# ==============================
def evaluate_concepts(llm_output, execution_finding=None):
    """
    Extracts concept-level evaluation from llm_output.
    If 'concepts' is absent (compact prompt), derives them from rubric scores.
    """
    if not isinstance(llm_output, dict):
        return derive_concepts_from_execution(execution_finding, {}) or derive_concepts_from_rubric({})

    # Always derive from rubric — LLM concept labels are unreliable
    rubric = llm_output.get("rubric", {})
    execution_concepts = derive_concepts_from_execution(execution_finding, rubric)
    if execution_concepts:
        return execution_concepts
    return derive_concepts_from_rubric(rubric)

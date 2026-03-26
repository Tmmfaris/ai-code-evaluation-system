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


# ==============================
# 🧠 MAIN CONCEPT EVALUATOR
# ==============================
def evaluate_concepts(llm_output):
    """
    Extracts concept-level evaluation from llm_output.
    If 'concepts' is absent (compact prompt), derives them from rubric scores.
    """
    if not isinstance(llm_output, dict):
        return derive_concepts_from_rubric({})

    # Always derive from rubric — LLM concept labels are unreliable
    return derive_concepts_from_rubric(llm_output.get("rubric", {}))
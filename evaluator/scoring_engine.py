# evaluator/scoring_engine.py

from config import TOTAL_SCORE


# ==============================
# 🔧 RUBRIC TOTAL
# ==============================
def calculate_rubric_total(rubric_score):
    """
    Sum rubric components
    """
    return (
        rubric_score.get("correctness", 0) +
        rubric_score.get("efficiency", 0) +
        rubric_score.get("readability", 0) +
        rubric_score.get("structure", 0)
    )


# ==============================
# 🧠 CONCEPT SCORE CONVERSION
# ==============================
def concept_to_score(concepts):
    """
    Convert qualitative concepts into numeric score
    """

    score = 0

    # Logic (max 4)
    if concepts.get("logic") == "Strong":
        score += 4
    elif concepts.get("logic") == "Good":
        score += 2
    elif concepts.get("logic") == "Weak":
        score += 1

    # Edge cases (max 2)
    if concepts.get("edge_cases") == "Good":
        score += 2
    elif concepts.get("edge_cases") in ("Needs Improvement", "Needs improvement"):
        score += 1

    # Completeness (max 2)
    if concepts.get("completeness") == "High":
        score += 2
    elif concepts.get("completeness") == "Medium":
        score += 1
    elif concepts.get("completeness") == "Low":
        score += 0

    # Efficiency (max 1)
    if concepts.get("efficiency") == "Good":
        score += 1
    elif concepts.get("efficiency") == "Average":
        score += 0

    # Readability (max 1)
    if concepts.get("readability") == "Good":
        score += 1
    elif concepts.get("readability") in ("Needs Improvement", "Needs improvement"):
        score += 0

    return score  # max = 10


# ==============================
# 🏁 FINAL SCORE COMBINATION
# ==============================
def combine_scores(rubric_score, concept_score):
    """
    Combine rubric + concept into final score
    """

    # Step 1: Get rubric total
    rubric_total = calculate_rubric_total(rubric_score)

    # Step 2: Convert concept → numeric
    concept_numeric = concept_to_score(concept_score)

    # Step 3: Combine
    final_score = rubric_total + concept_numeric

    # Step 4: Clamp to TOTAL_SCORE
    if final_score > TOTAL_SCORE:
        final_score = TOTAL_SCORE

    return final_score
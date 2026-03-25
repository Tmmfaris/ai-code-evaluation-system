import json


# =========================
# MAIN PARSER FUNCTION
# =========================
def parse_llm_response(response_text):
    """
    Extracts JSON from LLM response safely.
    Handles messy outputs and ensures system stability.
    """

    try:
        # -------------------------
        # Step 1: Find JSON boundaries
        # -------------------------
        start = response_text.find("{")
        end = response_text.rfind("}") + 1

        if start == -1 or end == -1:
            raise ValueError("No JSON found in response")

        json_str = response_text[start:end]

        # -------------------------
        # Step 2: Convert to dict
        # -------------------------
        parsed = json.loads(json_str)

        # -------------------------
        # Step 3: Validate fields
        # -------------------------
        return validate_response(parsed)

    except Exception as e:
        print(f"[Parser] Error: {e}")

        return fallback_response("Failed to parse LLM response")


# =========================
# VALIDATION FUNCTION
# =========================
def validate_response(data):
    """
    Ensures all required fields exist and are valid
    """

    # Default structure
    default = fallback_response()

    # Validate score
    score = data.get("score", default["score"])
    try:
        score = int(score)
        score = max(0, min(100, score))  # clamp 0–100
    except:
        score = default["score"]

    # Validate text fields
    feedback = str(data.get("feedback", default["feedback"]))
    strengths = str(data.get("strengths", default["strengths"]))
    improvements = str(data.get("improvements", default["improvements"]))

    # Validate concepts
    concepts = data.get("concepts", {})

    if not isinstance(concepts, dict):
        concepts = default["concepts"]

    validated_concepts = {
        "logic": concepts.get("logic", default["concepts"]["logic"]),
        "edge_cases": concepts.get("edge_cases", default["concepts"]["edge_cases"]),
        "completeness": concepts.get("completeness", default["concepts"]["completeness"]),
        "efficiency": concepts.get("efficiency", default["concepts"]["efficiency"]),
        "readability": concepts.get("readability", default["concepts"]["readability"]),
    }

    # Validate rubric
    rubric = data.get("rubric", {})
    if not isinstance(rubric, dict):
        rubric = default["rubric"]

    def _safe_int(val, max_val):
        try:
            v = int(val)
            return max(0, min(max_val, v))
        except:
            return 0

    validated_rubric = {
        "correctness": _safe_int(rubric.get("correctness", 0), 40),
        "efficiency":  _safe_int(rubric.get("efficiency",  0), 20),
        "readability": _safe_int(rubric.get("readability", 0), 15),
        "structure":   _safe_int(rubric.get("structure",   0), 15),
    }

    return {
        "score": score,
        "feedback": feedback,
        "strengths": strengths,
        "improvements": improvements,
        "concepts": validated_concepts,
        "rubric": validated_rubric,
    }


# =========================
# FALLBACK RESPONSE
# =========================
def fallback_response(message="LLM response error"):
    """
    Safe fallback when parsing fails
    """

    return {
        "score": 50,
        "feedback": message,
        "strengths": "",
        "improvements": "",
        "concepts": {
            "logic": "Unknown",
            "edge_cases": "Unknown",
            "completeness": "Unknown",
            "efficiency": "Unknown",
            "readability": "Unknown"
        },
        "rubric": {
            "correctness": 0,
            "efficiency": 0,
            "readability": 0,
            "structure": 0
        }
    }
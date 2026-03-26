import json
import re


# =========================
# JSON REPAIR UTILITY
# =========================
def _repair_truncated_json(text):
    """
    Closes unclosed JSON structures in a truncated string.
    Handles: open strings, missing values after ':', trailing commas.
    """
    text = text.strip()

    # If ends with ':' (key with no value), append a null value
    if text.endswith(":"):
        text += ' null'

    # Remove trailing commas
    text = re.sub(r",\s*$", "", text)

    # Walk the string to find unclosed structures
    in_string = False
    escape_next = False
    stack = []

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()

    # If we are mid-string after walking, close it
    if in_string:
        text += '"'
        # Re-check for trailing colon after closing
        if text.rstrip('"').rstrip().endswith(":"):
            text += ": null"

    # Close unclosed containers in reverse order
    text += "".join(reversed(stack))

    return text


# =========================
# MAIN PARSER FUNCTION
# =========================
def parse_llm_response(response_text):
    """
    Extracts JSON from LLM response safely.
    1. Tries every { position for complete valid JSON.
    2. Falls back to repairing the largest truncated JSON fragment.
    """

    print(f"[Parser] Raw LLM output:\n{response_text}")

    # Step 1: Clean trailing commas
    cleaned = re.sub(r",\s*([}\]])", r"\1", response_text)

    decoder = json.JSONDecoder()

    # Step 2: Try every { — use first complete JSON with evaluation fields
    pos = 0
    best_start = -1
    while True:
        idx = cleaned.find("{", pos)
        if idx == -1:
            break
        try:
            parsed, _ = decoder.raw_decode(cleaned, idx)
            if any(k in parsed for k in ("score", "feedback", "rubric", "concepts")):
                print(f"[Parser] Successfully parsed JSON at position {idx}")
                return validate_response(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
        # Track the { that starts the longest fragment
        if best_start == -1:
            best_start = idx
        pos = idx + 1

    # Step 3: Repair the truncated JSON fragment
    if best_start != -1:
        fragment = cleaned[best_start:]
        try:
            repaired = _repair_truncated_json(fragment)
            repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
            parsed = json.loads(repaired)
            if any(k in parsed for k in ("score", "feedback", "rubric", "concepts")):
                print(f"[Parser] Repaired truncated JSON successfully")
                return validate_response(parsed)
        except Exception as e:
            print(f"[Parser] Repair failed: {e}")

    print(f"[Parser] All strategies failed — returning fallback")
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
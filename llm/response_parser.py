import json
import re



def _repair_truncated_json(text):
    """
    Closes unclosed JSON structures in a truncated string.
    Handles open strings, missing values after ':', and trailing commas.
    """
    text = text.strip()

    if text.endswith(":"):
        text += " null"

    text = re.sub(r",\s*$", "", text)

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

    if in_string:
        text += '"'
        if text.rstrip('"').rstrip().endswith(":"):
            text += ": null"

    text += "".join(reversed(stack))
    return text



def parse_llm_response(response_text):
    """
    Extracts JSON from LLM response safely.
    1. Tries every { position for complete valid JSON.
    2. Falls back to repairing the largest truncated JSON fragment.
    """

    print(f"[Parser] Raw LLM output:\n{response_text}")

    cleaned = re.sub(r",\s*([}\]])", r"\1", response_text)
    decoder = json.JSONDecoder()

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
        if best_start == -1:
            best_start = idx
        pos = idx + 1

    if best_start != -1:
        fragment = cleaned[best_start:]
        try:
            repaired = _repair_truncated_json(fragment)
            repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
            parsed = json.loads(repaired)
            if any(k in parsed for k in ("score", "feedback", "rubric", "concepts")):
                print("[Parser] Repaired truncated JSON successfully")
                return validate_response(parsed)
        except Exception as exc:
            print(f"[Parser] Repair failed: {exc}")

    print("[Parser] All strategies failed, returning fallback")
    return fallback_response("LLM response parsing failed, so a safe fallback evaluation was used.")



def validate_response(data):
    """
    Ensures all required fields exist and are valid.
    """

    default = fallback_response()

    score = data.get("score", default["score"])
    try:
        score = int(score)
        score = max(0, min(100, score))
    except Exception:
        score = default["score"]

    feedback = str(data.get("feedback", default["feedback"]))
    improvements = str(data.get("improvements", default["improvements"]))

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

    rubric = data.get("rubric", {})
    if not isinstance(rubric, dict):
        rubric = default["rubric"]

    def _safe_int(val, max_val):
        try:
            value = int(val)
            return max(0, min(max_val, value))
        except Exception:
            return 0

    validated_rubric = {
        "correctness": _safe_int(rubric.get("correctness", 0), 40),
        "efficiency": _safe_int(rubric.get("efficiency", 0), 20),
        "readability": _safe_int(rubric.get("readability", 0), 15),
        "structure": _safe_int(rubric.get("structure", 0), 15),
    }

    return {
        "score": score,
        "feedback": feedback,
        "improvements": improvements,
        "concepts": validated_concepts,
        "rubric": validated_rubric,
    }



def fallback_response(message="LLM response error"):
    """
    Safe fallback when parsing fails.
    """

    return {
        "score": 55,
        "feedback": message,
        "improvements": "Retry the evaluation or rely on rule-based checks for common question types.",
        "concepts": {
            "logic": "Unknown",
            "edge_cases": "Unknown",
            "completeness": "Unknown",
            "efficiency": "Unknown",
            "readability": "Unknown",
        },
        "rubric": {
            "correctness": 20,
            "efficiency": 10,
            "readability": 5,
            "structure": 10,
        },
    }

def build_deterministic_result(execution_finding, structure_analysis):
    result_type = (execution_finding or {}).get("result_type")

    if result_type == "full_pass":
        rubric = {
            "correctness": 40,
            "efficiency": 20,
            "readability": 15,
            "structure": 15,
        }
    elif result_type == "mostly_correct":
        line_count = structure_analysis.get("line_count", 0) if isinstance(structure_analysis, dict) else 0
        readability = 15 if line_count <= 6 else 13
        rubric = {
            "correctness": 34,
            "efficiency": 14,
            "readability": readability,
            "structure": 15,
        }
    elif result_type == "correct_but_inefficient":
        line_count = structure_analysis.get("line_count", 0) if isinstance(structure_analysis, dict) else 0
        readability = 15 if line_count <= 6 else 13
        rubric = {
            "correctness": 36,
            "efficiency": 12,
            "readability": readability,
            "structure": 15,
        }
    elif result_type == "partial_pass":
        rubric = {
            "correctness": 28,
            "efficiency": 15,
            "readability": 10,
            "structure": 12,
        }
    elif result_type == "execution_error":
        rubric = {
            "correctness": 5,
            "efficiency": 5,
            "readability": 8,
            "structure": 8,
        }
    else:
        rubric = {
            "correctness": 5,
            "efficiency": 5,
            "readability": 8,
            "structure": 10,
        }

    return {
        "score": 0,
        "feedback": execution_finding.get("feedback", ""),
        "improvements": execution_finding.get("suggestion", ""),
        "rubric": rubric,
    }


def merge_hybrid_rubric(llm_rubric, execution_finding, structure_analysis):
    if not isinstance(llm_rubric, dict):
        llm_rubric = {}

    merged = {
        "correctness": llm_rubric.get("correctness", 0),
        "efficiency": llm_rubric.get("efficiency", 0),
        "readability": llm_rubric.get("readability", 0),
        "structure": llm_rubric.get("structure", 0),
    }

    if not execution_finding:
        return merged

    deterministic = build_deterministic_result(
        execution_finding=execution_finding,
        structure_analysis=structure_analysis,
    )["rubric"]
    result_type = execution_finding.get("result_type")

    if result_type == "full_pass":
        for key in ("correctness", "efficiency", "readability", "structure"):
            merged[key] = max(merged.get(key, 0), deterministic.get(key, 0))
        return merged

    if result_type in {"mostly_correct", "correct_but_inefficient"}:
        merged["correctness"] = max(merged.get("correctness", 0), deterministic.get("correctness", 0))
        merged["readability"] = max(merged.get("readability", 0), deterministic.get("readability", 0))
        merged["structure"] = max(merged.get("structure", 0), deterministic.get("structure", 0))
        merged["efficiency"] = min(merged.get("efficiency", 0), deterministic.get("efficiency", 0))
        return merged

    if result_type in {"partial_pass", "execution_error", "zero_pass"}:
        for key in ("correctness", "efficiency", "readability", "structure"):
            merged[key] = min(merged.get(key, 0), deterministic.get(key, 0))
        return merged

    return merged

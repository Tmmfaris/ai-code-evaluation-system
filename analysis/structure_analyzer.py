from utils.helpers import is_comment_line


def analyze_structure(code):
    """
    Analyzes structural elements of code.

    Returns:
        dict:
        {
            "has_loop": bool,
            "has_condition": bool,
            "has_function": bool,
            "has_class": bool,
            "line_count": int,
            "comment_lines": int,
            "blank_lines": int
        }
    """

    if not code:
        return {
            "has_loop": False,
            "has_condition": False,
            "has_function": False,
            "has_class": False,
            "line_count": 0,
            "comment_lines": 0,
            "blank_lines": 0
        }

    lines = code.split("\n")
    code_lower = code.lower()

    # -------------------------
    # Detect patterns
    # -------------------------
    has_loop = any(keyword in code_lower for keyword in ["for", "while"])
    has_condition = "if" in code_lower
    has_function = any(keyword in code_lower for keyword in ["def", "function"])
    has_class = "class" in code_lower

    # -------------------------
    # Count lines
    # -------------------------
    total_lines = len(lines)
    blank_lines = 0
    comment_lines = 0

    for line in lines:
        stripped = line.strip()

        if stripped == "":
            blank_lines += 1

        elif is_comment_line(stripped):
            comment_lines += 1

    # -------------------------
    # Return result
    # -------------------------
    return {
        "has_loop": has_loop,
        "has_condition": has_condition,
        "has_function": has_function,
        "has_class": has_class,
        "line_count": total_lines,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines
    }


# is_comment_line() moved to utils/helpers.py — imported above
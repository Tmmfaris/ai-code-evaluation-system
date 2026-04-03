def _balanced_pairs_ok(code):
    stack = []
    pairs = {"(": ")", "{": "}", "[": "]"}
    closing = {value: key for key, value in pairs.items()}

    for ch in code:
        if ch in pairs:
            stack.append(ch)
        elif ch in closing:
            if not stack or stack[-1] != closing[ch]:
                return False
            stack.pop()

    return not stack


def check_mysql_syntax(code):
    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty MySQL submission",
            "line": None,
        }

    stripped = code.strip()
    lowered = stripped.lower()

    if not _balanced_pairs_ok(stripped):
        return {
            "valid": False,
            "error": "Unbalanced SQL parentheses or brackets",
            "line": None,
        }

    if not any(
        lowered.startswith(keyword)
        for keyword in ("select", "insert", "update", "delete", "create", "alter", "drop", "with")
    ):
        return {
            "valid": False,
            "error": "Submission does not start with a recognizable SQL statement",
            "line": None,
        }

    return {
        "valid": True,
        "error": None,
        "line": None,
    }

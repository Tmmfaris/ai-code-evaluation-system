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


def check_mongodb_syntax(code):
    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty MongoDB submission",
            "line": None,
        }

    stripped = code.strip()
    lowered = stripped.lower()

    if not _balanced_pairs_ok(stripped):
        return {
            "valid": False,
            "error": "Unbalanced MongoDB query brackets or braces",
            "line": None,
        }

    if not any(token in lowered for token in ("db.", ".find(", ".aggregate(", ".insert", ".update", ".delete")):
        return {
            "valid": False,
            "error": "Submission does not look like a MongoDB query or command",
            "line": None,
        }

    return {
        "valid": True,
        "error": None,
        "line": None,
    }

def _balanced_pairs_ok(code):
    stack = []
    pairs = {"{": "}", "(": ")", "[": "]"}
    closing = {value: key for key, value in pairs.items()}

    for ch in code:
        if ch in pairs:
            stack.append(ch)
        elif ch in closing:
            if not stack or stack[-1] != closing[ch]:
                return False
            stack.pop()

    return not stack


def check_css_syntax(code):
    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty CSS submission",
            "line": None,
        }

    stripped = code.strip()

    if not _balanced_pairs_ok(stripped):
        return {
            "valid": False,
            "error": "Unbalanced CSS braces or brackets",
            "line": None,
        }

    if "{" not in stripped or "}" not in stripped:
        return {
            "valid": False,
            "error": "Missing CSS rule block",
            "line": None,
        }

    if ":" not in stripped:
        return {
            "valid": False,
            "error": "Missing CSS property declaration",
            "line": None,
        }

    return {
        "valid": True,
        "error": None,
        "line": None,
    }

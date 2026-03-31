def _balanced_pairs_ok(code):
    pairs = {"(": ")", "{": "}", "[": "]"}
    closing = {value: key for key, value in pairs.items()}
    stack = []

    for ch in code:
        if ch in pairs:
            stack.append(ch)
        elif ch in closing:
            if not stack or stack[-1] != closing[ch]:
                return False
            stack.pop()

    return not stack


def check_javascript_syntax(code):
    """
    Performs a lightweight JavaScript syntax sanity check.

    This is not a full parser, but it catches common malformed inputs and
    avoids treating clearly broken JavaScript as valid.
    """

    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty JavaScript submission",
            "line": None,
        }

    stripped = code.strip()
    lowered = stripped.lower()

    if not _balanced_pairs_ok(stripped):
        return {
            "valid": False,
            "error": "Unbalanced brackets or parentheses",
            "line": None,
        }

    if lowered.count("function") > 0 and "(" not in stripped:
        return {
            "valid": False,
            "error": "Malformed function declaration",
            "line": None,
        }

    if "return" in lowered and ";" not in stripped and "=>" not in stripped:
        return {
            "valid": False,
            "error": "Possible missing statement terminator",
            "line": None,
        }

    return {
        "valid": True,
        "error": None,
        "line": None,
    }

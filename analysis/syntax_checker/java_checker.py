import re


JAVA_METHOD_PATTERN = re.compile(
    r"(public|private|protected)?\s*(static\s+)?[A-Za-z_<>\[\]]+\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)



def _looks_like_java_method(code):
    return bool(JAVA_METHOD_PATTERN.search(code or ""))



def check_java_syntax(code):
    """
    Performs basic Java syntax and structure validation.
    Accepts either a full class or a standalone method snippet,
    which is common in academy-style answers.
    """

    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty code submission",
            "line": None,
        }

    has_class = "class" in code
    has_method = _looks_like_java_method(code)

    if not has_class and not has_method:
        return {
            "valid": False,
            "error": "Expected a Java class or method definition",
            "line": None,
        }

    open_braces = code.count("{")
    close_braces = code.count("}")
    if open_braces != close_braces:
        return {
            "valid": False,
            "error": f"Unbalanced braces: {open_braces} open, {close_braces} close",
            "line": None,
        }

    if ";" not in code:
        return {
            "valid": False,
            "error": "No semicolons found - invalid Java syntax",
            "line": None,
        }

    return {
        "valid": True,
        "error": None,
        "line": None,
    }

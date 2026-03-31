import re


JAVA_METHOD_PATTERN = re.compile(
    r"(public|private|protected)?\s*(static\s+)?[A-Za-z_<>\[\]]+\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*(throws\s+[A-Za-z0-9_.,\s]+)?\{",
    re.MULTILINE,
)

JAVA_STATEMENT_PATTERN = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_<>.\[\]]*\s*\([^;]*\)\s*;\s*$",
    re.MULTILINE,
)


def _looks_like_java_method(code):
    return bool(JAVA_METHOD_PATTERN.search(code or ""))


def _looks_like_java_statement(code):
    text = (code or "").strip()
    if not text:
        return False
    if "class " in text or "interface " in text or "enum " in text:
        return False
    return bool(JAVA_STATEMENT_PATTERN.match(text))



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
    has_statement = _looks_like_java_statement(code)

    if not has_class and not has_method and not has_statement:
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

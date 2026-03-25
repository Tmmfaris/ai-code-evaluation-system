def check_java_syntax(code):
    """
    Performs basic Java syntax and structure validation.

    NOTE:
    This is a lightweight checker (not full compilation).
    Suitable for AI evaluation systems.
    """

    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty code submission",
            "line": None
        }

    lines = code.split("\n")

    # -------------------------
    # 1. Check for class keyword
    # -------------------------
    if "class" not in code:
        return {
            "valid": False,
            "error": "Missing class definition",
            "line": None
        }

    # -------------------------
    # 2. Check braces balance
    # -------------------------
    open_braces = code.count("{")
    close_braces = code.count("}")

    if open_braces != close_braces:
        return {
            "valid": False,
            "error": f"Unbalanced braces: {open_braces} open, {close_braces} close",
            "line": None
        }

    # -------------------------
    # 3. Check for semicolons
    # -------------------------
    if ";" not in code:
        return {
            "valid": False,
            "error": "No semicolons found — invalid Java syntax",
            "line": None
        }

    # -------------------------
    # VALID JAVA
    # -------------------------
    return {
        "valid": True,
        "error": None,
        "line": None
    }
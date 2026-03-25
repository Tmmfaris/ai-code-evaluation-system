import ast


def check_python_syntax(code):
    """
    Checks Python code syntax using AST parsing.

    Parameters:
        code (str): Python code submitted by student

    Returns:
        dict: {
            "valid": bool,
            "error": str or None,
            "line": int or None
        }
    """

    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty code submission",
            "line": None
        }

    try:
        # Parse code using AST
        ast.parse(code)

        return {
            "valid": True,
            "error": None,
            "line": None
        }

    except SyntaxError as e:
        return {
            "valid": False,
            "error": e.msg,
            "line": e.lineno
        }

    except Exception as e:
        return {
            "valid": False,
            "error": f"Unexpected error: {str(e)}",
            "line": None
        }
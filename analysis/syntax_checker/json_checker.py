import json


def check_json_syntax(code):
    """
    Validates JSON syntax using Python's json module.

    Parameters:
        code (str): JSON string submitted by student

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
            "error": "Empty JSON submission",
            "line": None
        }

    try:
        json.loads(code)

        return {
            "valid": True,
            "error": None,
            "line": None
        }

    except json.JSONDecodeError as e:
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
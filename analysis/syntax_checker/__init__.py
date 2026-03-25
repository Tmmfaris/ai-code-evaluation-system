# =========================
# IMPORT ALL CHECKERS
# =========================

from .python_checker import check_python_syntax
from .java_checker import check_java_syntax
from .html_checker import check_html_syntax
from .json_checker import check_json_syntax


# =========================
# SUPPORTED LANGUAGES MAP
# =========================

SYNTAX_CHECKERS = {
    "python": check_python_syntax,
    "java": check_java_syntax,
    "html": check_html_syntax,
    "json": check_json_syntax,
}


# =========================
# MAIN SYNTAX CHECK FUNCTION
# =========================

def check_syntax(code, language):
    """
    Unified syntax checker for multiple languages

    Parameters:
        code (str): Student code
        language (str): Programming language

    Returns:
        dict: {
            "valid": bool,
            "error": str or None
        }
    """

    if not code:
        return {
            "valid": False,
            "error": "Empty code submission"
        }

    language = (language or "").lower().strip()

    checker = SYNTAX_CHECKERS.get(language)

    if checker:
        try:
            return checker(code)
        except Exception as e:
            return {
                "valid": False,
                "error": f"Syntax checker error: {str(e)}"
            }

    return {
        "valid": False,
        "error": f"No syntax checker available for '{language}'"
    }
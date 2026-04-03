try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency fallback
    BeautifulSoup = None


def check_html_syntax(code):
    """
    Performs basic HTML validation using BeautifulSoup.

    Checks:
    - Empty code
    - Basic parsing
    - Presence of HTML structure
    """

    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty HTML submission",
            "line": None
        }

    try:
        if BeautifulSoup is None:
            open_tags = code.count("<")
            close_tags = code.count(">")
            if open_tags == 0 or close_tags == 0:
                return {
                    "valid": False,
                    "error": "No valid HTML tags found",
                    "line": None
                }
            if open_tags != close_tags:
                return {
                    "valid": False,
                    "error": "Unbalanced HTML tags",
                    "line": None
                }
            warning = None if "<html" in code.lower() else "Missing <html> root element (optional but recommended)"
            return {
                "valid": True,
                "error": warning,
                "line": None
            }

        soup = BeautifulSoup(code, "html.parser")

        # -------------------------
        # 1. Check if any tags exist
        # -------------------------
        if not soup.find():
            return {
                "valid": False,
                "error": "No valid HTML tags found",
                "line": None
            }

        # -------------------------
        # 2. Check for basic structure
        # -------------------------
        if "<html" not in code.lower():
            warning = "Missing <html> root element (optional but recommended)"
        else:
            warning = None

        # -------------------------
        # 3. Check unclosed tags (basic)
        # -------------------------
        # BeautifulSoup auto-fixes HTML, so we approximate
        open_tags = code.count("<")
        close_tags = code.count(">")

        if open_tags != close_tags:
            return {
                "valid": False,
                "error": "Unbalanced HTML tags",
                "line": None
            }

        # -------------------------
        # VALID HTML
        # -------------------------
        return {
            "valid": True,
            "error": warning,
            "line": None
        }

    except Exception as e:
        return {
            "valid": False,
            "error": f"HTML parsing error: {str(e)}",
            "line": None
        }

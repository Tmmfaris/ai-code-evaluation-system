import re


# =========================
# CLEAN TEXT
# =========================
def clean_text(text):
    """
    Removes extra spaces and normalizes text
    """
    if not text:
        return ""

    return text.strip()


# =========================
# NORMALIZE CODE
# =========================
def normalize_code(code):
    """
    Removes unnecessary spaces and blank lines
    """
    if not code:
        return ""

    lines = code.split("\n")
    cleaned = [line.rstrip() for line in lines if line.strip() != ""]

    return "\n".join(cleaned)


# =========================
# DETECT LANGUAGE (BASIC)
# =========================
def detect_language(code):
    """
    Simple language detection based on keywords
    """

    code_lower = code.lower()

    if "def " in code_lower:
        return "python"

    if "public class" in code_lower:
        return "java"

    if "<html" in code_lower or "<div" in code_lower:
        return "html"

    if code.strip().startswith("{"):
        return "json"

    return "unknown"


# =========================
# TRUNCATE TEXT (FOR LOGGING)
# =========================
def truncate_text(text, length=100):
    """
    Shortens long text for logging
    """
    if not text:
        return ""

    return text[:length] + "..." if len(text) > length else text


# =========================
# SAFE INTEGER CONVERSION
# =========================
def safe_int(value, default=0):
    """
    Converts value to int safely
    """
    try:
        return int(value)
    except:
        return default


# =========================
# REMOVE EXTRA WHITESPACES
# =========================
def remove_extra_spaces(text):
    """
    Replace multiple spaces with single space
    """
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


# =========================
# DETECT COMMENT LINE
# =========================
def is_comment_line(line):
    """
    Detects comment lines across Python, Java, HTML
    """
    if not line:
        return False

    comment_symbols = [
        "#",       # Python
        "//",      # Java, C++
        "/*",      # Block comment start
        "*/",      # Block comment end
        "<!--"     # HTML
    ]

    return any(line.startswith(symbol) for symbol in comment_symbols)


# =========================
# CHECK EMPTY INPUT
# =========================
def is_empty(text):
    """
    Check if input is empty or whitespace
    """
    return not text or not text.strip()
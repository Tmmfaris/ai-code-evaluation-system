import re
import ast


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


def normalize_python_structure(code):
    """
    Repairs a narrow Python payload formatting issue:
    function headers written as `def f(...): stmt` followed by more indented lines.
    """
    normalized = normalize_code(code)
    if not normalized:
        return normalized

    try:
        ast.parse(normalized)
        return normalized
    except Exception:
        pass

    lines = normalized.split("\n")
    if len(lines) < 2:
        return normalized

    first_line = lines[0]
    match = re.match(r"^(\s*(?:async\s+)?def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(.*\)\s*:)\s+(.+)$", first_line)
    if not match:
        return normalized

    remaining = lines[1:]
    indent = None
    for line in remaining:
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = line[: len(line) - len(stripped)]
        if indent:
            break
    if indent is None:
        indent = "    "

    rebuilt = "\n".join([match.group(1), f"{indent}{match.group(2)}", *remaining])
    try:
        ast.parse(rebuilt)
        return rebuilt
    except Exception:
        return normalized


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

    if any(token in code_lower for token in ("export default", "usestate", "useeffect", "return (", "jsx", "react.")):
        return "react"

    if "<html" in code_lower or ("<div" in code_lower and "return (" not in code_lower):
        return "html"

    if any(token in code_lower for token in (".class", "#id", "@media", "{", "color:", "display:")) and "function " not in code_lower:
        return "css"

    if "function " in code_lower or "const " in code_lower or "let " in code_lower or "=>" in code_lower:
        return "javascript"

    if any(token in code_lower for token in ("select ", "insert ", "update ", "delete ", "create table", "from ")):
        return "mysql"

    if any(token in code_lower for token in ("db.", ".find(", ".aggregate(", ".insertone(", ".updateone(")):
        return "mongodb"

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

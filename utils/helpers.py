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
    Intelligently repairs Python indentation by mapping relative whitespace levels.
    Handles 'merged' headers and messy copy-paste indentation.
    """
    if not code:
        return ""

    # If it already parses, don't touch it.
    try:
        ast.parse(code)
        return code
    except Exception:
        pass

    processed_lines = [line.rstrip() for line in code.split("\n")]
    if not processed_lines:
        return code

    # Step 1: Split "def f(): stmt" into two lines
    # This prepares the code for our block-level re-indenter
    first_line = processed_lines[0]
    match = re.match(r"^(\s*(?:async\s+)?def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(.*\)\s*:)\s+(.+)$", first_line)
    if match:
        processed_lines[0] = match.group(1)
        # We give the second line a slightly deeper indent than the header to mark it as body
        header_indent = len(first_line) - len(first_line.lstrip())
        processed_lines.insert(1, " " * (header_indent + 1) + match.group(2))

    # Step 2: Relative Indentation Mapping
    # 1. Identify all unique indentation levels used
    # 2. Sort them and map them to 4-space multiples
    line_data = [] # List of (indent_amount, text)
    levels = set()
    
    for line in processed_lines:
        stripped = line.lstrip()
        if not stripped:
            continue
        indent_amount = len(line) - len(stripped)
        line_data.append((indent_amount, stripped))
        levels.add(indent_amount)
    
    sorted_levels = sorted(list(levels))
    level_map = {val: i * 4 for i, val in enumerate(sorted_levels)}
    
    rebuilt_lines = []
    for indent, text in line_data:
        new_indent = level_map.get(indent, 0)
        rebuilt_lines.append(" " * new_indent + text)
        
    rebuilt = "\n".join(rebuilt_lines)
    
    # Final check: if it still doesn't parse, try a brute-force trim
    try:
        ast.parse(rebuilt)
        return rebuilt
    except Exception:
        # Last resort: just strip everything and indent 4-spaces for everything after the first line
        final_attempt = []
        for i, (indent, text) in enumerate(line_data):
            if i == 0:
                final_attempt.append(text)
            else:
                final_attempt.append("    " + text)
        return "\n".join(final_attempt)


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

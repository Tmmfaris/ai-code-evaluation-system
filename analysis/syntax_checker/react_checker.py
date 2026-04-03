import re

from .javascript_checker import check_javascript_syntax


def _balanced_angle_brackets(code):
    opens = len(re.findall(r"<[A-Za-z][^>/]*?>", code))
    closes = len(re.findall(r"</[A-Za-z][^>]*?>", code))
    self_closing = len(re.findall(r"<[A-Za-z][^>]*?/>", code))
    return opens <= closes + self_closing or closes > 0 or self_closing > 0


def check_react_syntax(code):
    if not code or not code.strip():
        return {
            "valid": False,
            "error": "Empty React submission",
            "line": None,
        }

    stripped = code.strip()
    base = check_javascript_syntax(stripped)
    if not base.get("valid"):
        return base

    lowered = stripped.lower()
    has_component_shape = any(
        token in lowered for token in ("return (", "return<", "jsx", "usestate", "useeffect", "export default")
    ) or "<" in stripped

    if not has_component_shape:
        return {
            "valid": False,
            "error": "Submission does not look like a React component or JSX snippet",
            "line": None,
        }

    if "<" in stripped and ">" in stripped and not _balanced_angle_brackets(stripped):
        return {
            "valid": False,
            "error": "Unbalanced JSX tags",
            "line": None,
        }

    return {
        "valid": True,
        "error": None,
        "line": None,
    }

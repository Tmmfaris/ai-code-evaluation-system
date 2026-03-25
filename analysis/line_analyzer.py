from utils.helpers import is_comment_line


def analyze_lines(code):
    """
    Performs line-by-line analysis of code.

    Returns:
        list of dicts:
        [
            {
                "line_number": int,
                "content": str,
                "length": int,
                "is_comment": bool,
                "is_blank": bool
            }
        ]
    """

    if not code:
        return []

    lines = code.split("\n")
    analyzed = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        analyzed.append({
            "line_number": i + 1,
            "content": stripped,
            "length": len(stripped),
            "is_comment": is_comment_line(stripped),
            "is_blank": stripped == ""
        })

    return analyzed


# is_comment_line() moved to utils/helpers.py — imported above
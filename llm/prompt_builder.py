def build_prompt(
    question,
    sample_answer,
    student_answer,
    language,
    syntax_result=None,
    structure_analysis=None,
    line_analysis=None,
    rag_context=None
):
    """
    Builds a structured prompt for LLM-based evaluation.
    """

    if syntax_result and isinstance(syntax_result, dict):
        if syntax_result.get("valid"):
            syntax_text = "No syntax errors detected"
        else:
            err = syntax_result.get("error", "Unknown error")
            line_num = syntax_result.get("line")
            syntax_text = f"SYNTAX ERROR: {err}" + (f" (line {line_num})" if line_num else "")
    else:
        syntax_text = "No syntax issues detected"

    if structure_analysis and isinstance(structure_analysis, dict):
        parts = [
            f"Has loop: {structure_analysis.get('has_loop', False)}",
            f"Has condition: {structure_analysis.get('has_condition', False)}",
            f"Has function: {structure_analysis.get('has_function', False)}",
            f"Has class: {structure_analysis.get('has_class', False)}",
            f"Total lines: {structure_analysis.get('line_count', 0)}",
            f"Comment lines: {structure_analysis.get('comment_lines', 0)}",
            f"Blank lines: {structure_analysis.get('blank_lines', 0)}",
        ]
        structure_text = " | ".join(parts)
    else:
        structure_text = "Not provided"

    if line_analysis and isinstance(line_analysis, list):
        line_parts = []
        for item in line_analysis:
            if item.get("is_blank"):
                continue
            ln = item.get("line_number", "?")
            content = item.get("content", "")
            tag = " [comment]" if item.get("is_comment") else ""
            line_parts.append(f"  Line {ln}: {content}{tag}")
            if len(line_parts) >= 10:
                line_parts.append("  ... (truncated)")
                break
        line_text = "\n".join(line_parts) if line_parts else "No code lines found"
    else:
        line_text = "Not provided"

    prompt = f"""<|user|>
You are a strict programming evaluator. Evaluate ONLY the STUDENT CODE. Do NOT give credit for the CORRECT SOLUTION.

Language: {language} | Syntax: {syntax_text}
Question: {question}

CORRECT SOLUTION (for reference only):
{sample_answer}

STUDENT CODE (evaluate this):
{student_answer}

Structure summary: {structure_text}
Line summary:
{line_text}

Evaluation rules:
- Do not penalize alternative correct solutions just because they differ from the reference answer.
- Do not suggest replacing working logic with a built-in function unless the current approach has a meaningful correctness, efficiency, or readability problem.
- Do not ask the student to match the reference solution style for consistency alone.
- If the student solution is correct, feedback should focus on real issues only, not preference-based rewrites.
- Follow these rules strictly.
- Score correctness first.
- Minor inefficiencies must not reduce correctness score.
- If logic is mostly correct but has an edge-case mistake, the overall score should usually stay in the 60-80 range.
- If logic is completely wrong, the overall score should usually stay in the 0-20 range.
- Keep feedback simple, direct, and accurate.

Rubric:
- correctness (0-40): Does the student code produce the expected behavior for the required inputs? If not, keep this low. If fully correct, use 36-40.
- efficiency (0-20): Is the approach reasonably efficient for the problem? If correctness is 0, efficiency should also stay low.
- readability (0-15): Is the code clear and understandable? Do not require comments for short, simple, correct solutions.
- structure (0-15): Is the function definition and organization appropriate?
score = sum of rubric.

Return ONLY this compact single-line JSON (no spaces/newlines):
{{"score":<0-100>,"feedback":"<2-3 concise sentences with a clear explanation>","improvements":"<one short improvement sentence or empty string>","rubric":{{"correctness":<0-40>,"efficiency":<0-20>,"readability":<0-15>,"structure":<0-15>}}}}
<|end|>
<|assistant|>
"""

    return prompt

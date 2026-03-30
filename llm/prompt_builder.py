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
    Builds a structured prompt for LLM-based evaluation
    """

    # =========================
    # FORMAT ANALYSIS INPUTS
    # =========================

    # Format syntax result
    if syntax_result and isinstance(syntax_result, dict):
        if syntax_result.get("valid"):
            syntax_text = "No syntax errors detected"
        else:
            err = syntax_result.get("error", "Unknown error")
            line_num = syntax_result.get("line")
            syntax_text = f"SYNTAX ERROR: {err}" + (f" (line {line_num})" if line_num else "")
    else:
        syntax_text = "No syntax issues detected"

    # Format structure analysis
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

    # Format line-by-line analysis (compact, max 10 lines to save tokens)
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

    # =========================
    # PROMPT TEMPLATE (Phi-3 instruct chat format)
    # =========================
    prompt = f"""<|user|>
You are a strict programming evaluator. Evaluate ONLY the STUDENT CODE. Do NOT give credit for the CORRECT SOLUTION.

Language: {language} | Syntax: {syntax_text}
Question: {question}

CORRECT SOLUTION (for reference only):
{sample_answer}

STUDENT CODE (evaluate this):
{student_answer}

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
- correctness (0-40): Does student code produce same output as correct solution for all inputs? If not → 0 to 10. If fully correct → 36-40.
- efficiency (0-20): Is algorithm efficient? If correctness=0 then efficiency must also be 0-5.
- readability (0-15): Comments present, clear naming? No comments → deduct 5-8.
- structure (0-15): Proper function definition and organisation?
score = sum of rubric.

Return ONLY this compact single-line JSON (no spaces/newlines):
{{"score":<0-100>,"feedback":"<2-3 concise sentences with a clear explanation>","improvements":"<one short improvement sentence or empty string>","rubric":{{"correctness":<0-40>,"efficiency":<0-20>,"readability":<0-15>,"structure":<0-15>}}}}
<|end|>
<|assistant|>
"""

    return prompt

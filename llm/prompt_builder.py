def build_prompt(
    question,
    sample_answer,
    student_answer,
    language,
    question_profile=None,
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

    if isinstance(question_profile, dict):
        category = question_profile.get("category", "general")
        task_type = question_profile.get("task_type", "unknown")
        risk = question_profile.get("risk", "medium")
        markers = ", ".join(question_profile.get("markers", [])) or "none"
        profile_text = f"Category: {category} | Task: {task_type} | Risk: {risk} | Markers: {markers}"
    else:
        profile_text = "Category: general | Task: unknown | Risk: medium | Markers: none"

    context_text = ""
    if rag_context:
        context_text = f"Additional context:\n{rag_context}\n\n"

    prompt = f"""<|user|>
You are a strict programming evaluator. Compare the STUDENT CODE against the CORRECT SOLUTION for logic, but evaluate ONLY the STUDENT CODE. Do NOT give credit just because the reference answer is correct.

Language: {language} | Syntax: {syntax_text}
Question profile: {profile_text}
Question: {question}

{context_text}CORRECT SOLUTION (for reference only):
{sample_answer}

STUDENT CODE (evaluate this):
{student_answer}

Structure summary: {structure_text}
Line summary:
{line_text}

Evaluation rules:
- First compare the student answer against the reference answer for intended logic and expected behavior.
- Do not penalize alternative correct solutions just because they differ from the reference answer.
- Do not suggest replacing working logic with a built-in function unless the current approach has a meaningful correctness, efficiency, or readability problem.
- Do not ask the student to match the reference solution style for consistency alone.
- If the student solution is correct, feedback should focus on real issues only, not preference-based rewrites.
- If the question explicitly requires a technique or construct, such as recursion, streams, Set, Map, exception handling, abstract class design, or a specific safety requirement, treat missing that requirement as a real grading issue.
- Use the question profile as routing context: respect the task category and risk level when deciding whether a solution is fully correct, partially correct, or unsafe to over-score.
- For CSS, React, MongoDB, and MySQL submissions, prefer cautious grading unless the behavior/structure is clearly correct from the provided code.
- Do not label valid standalone Java methods or valid Java statement snippets as syntax errors just because they are not wrapped in a full class.
- Follow these rules strictly.
- Score correctness first.
- Minor inefficiencies must not reduce correctness score.
- If logic is mostly correct but has an edge-case mistake, the overall score should usually stay in the 60-80 range.
- If logic is completely wrong, the overall score should usually stay in the 0-20 range.
- Keep feedback simple, direct, and accurate.
- Do not include code snippets or inline code in feedback; describe the issue in plain language.

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


def build_comparison_prompt(
    question,
    sample_answer,
    student_answer,
    language,
    question_profile=None,
    syntax_result=None,
    structure_analysis=None,
    line_analysis=None,
    rag_context=None,
):
    """
    Explicit alias for the mentor-preferred evaluation framing:
    compare model answer and student answer, judge logic, then score and feedback.
    """
    return build_prompt(
        question=question,
        sample_answer=sample_answer,
        student_answer=student_answer,
        language=language,
        question_profile=question_profile,
        syntax_result=syntax_result,
        structure_analysis=structure_analysis,
        line_analysis=line_analysis,
        rag_context=rag_context,
    )


def build_audit_prompt(
    question,
    sample_answer,
    student_answer,
    language,
    initial_score,
    initial_feedback,
    initial_improvements,
    initial_rubric,
    question_profile=None,
    syntax_result=None,
    execution_finding=None,
    rule_findings=None,
    confidence=None,
):
    if syntax_result and isinstance(syntax_result, dict):
        if syntax_result.get("valid"):
            syntax_text = "No syntax errors detected"
        else:
            err = syntax_result.get("error", "Unknown error")
            line_num = syntax_result.get("line")
            syntax_text = f"SYNTAX ERROR: {err}" + (f" (line {line_num})" if line_num else "")
    else:
        syntax_text = "No syntax issues detected"

    if isinstance(question_profile, dict):
        category = question_profile.get("category", "general")
        task_type = question_profile.get("task_type", "unknown")
        risk = question_profile.get("risk", "medium")
        markers = ", ".join(question_profile.get("markers", [])) or "none"
        profile_text = f"Category: {category} | Task: {task_type} | Risk: {risk} | Markers: {markers}"
    else:
        profile_text = "Category: general | Task: unknown | Risk: medium | Markers: none"

    execution_text = "None"
    if isinstance(execution_finding, dict) and execution_finding:
        execution_text = (
            f"Type: {execution_finding.get('result_type', 'unknown')} | "
            f"Feedback: {execution_finding.get('feedback', '')} | "
            f"Suggestion: {execution_finding.get('suggestion', '')}"
        )

    rules_text = "None"
    if isinstance(rule_findings, list) and rule_findings:
        rendered = []
        for item in rule_findings[:6]:
            rendered.append(
                f"{item.get('type', 'finding')} | "
                f"correctness_max={item.get('correctness_max')} | "
                f"feedback={item.get('feedback', '')}"
            )
        rules_text = " || ".join(rendered)

    rubric = initial_rubric or {}

    prompt = f"""<|user|>
You are a strict evaluation auditor. Your job is to check whether an EXISTING evaluation is correct, and correct it if needed.

Language: {language} | Syntax: {syntax_text}
Question profile: {profile_text}
Confidence: {confidence or "unknown"}
Question: {question}

CORRECT SOLUTION (reference only):
{sample_answer}

STUDENT CODE:
{student_answer}

Initial evaluation:
- score: {initial_score}
- feedback: {initial_feedback}
- improvements: {initial_improvements}
- rubric: {rubric}

Deterministic evidence:
- execution: {execution_text}
- rule findings: {rules_text}

Audit rules:
- If the initial evaluation is correct, keep it close.
- If the initial evaluation is wrong, correct both score and feedback.
- Respect strong deterministic evidence such as syntax failure, hard fail, zero-pass, or full-pass behavior.
- Do not over-score clearly wrong solutions.
- Do not under-score clearly correct solutions.
- Feedback must explain the real issue, not style preferences.
- Return ONLY a compact single-line JSON.

Return:
{{"score":<0-100>,"feedback":"<corrected concise feedback>","improvements":"<short correction/improvement sentence or empty string>","rubric":{{"correctness":<0-40>,"efficiency":<0-20>,"readability":<0-15>,"structure":<0-15>}}}}
<|end|>
<|assistant|>
"""

    return prompt


def build_rephrase_prompt(question, language, feedback, improvements):
    prompt = f"""<|user|>
You are a rewrite assistant. Rephrase the feedback to be clearer and more helpful, without changing its meaning or correctness.

Rules:
- Do NOT change the verdict.
- Do NOT introduce new errors or new requirements.
- Keep feedback concise: 1-2 sentences.
- Improvements can be a short sentence or empty string.
- Do not include code snippets or inline code in feedback.
- Preserve the exact mistake from the original feedback when one is already known.
- If the original feedback mentions a specific bug, such as checking the wrong condition, failing on empty strings, returning a constant, or using the wrong element, keep that concrete detail.
- Do not replace specific feedback with generic phrases like "ensure the function works correctly", "implement a fallback", "for consistency", or "reliably".
- Return ONLY compact single-line JSON.

Language: {language}
Question: {question}

Original feedback:
{feedback}

Original improvements:
{improvements}

Return:
{{"feedback":"<rephrased feedback>","improvements":"<rephrased improvements or empty>"}}
<|end|>
<|assistant|>
"""
    return prompt

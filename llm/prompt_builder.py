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

    # Format line-by-line analysis (compact)
    if line_analysis and isinstance(line_analysis, list):
        line_parts = []
        for item in line_analysis:
            ln = item.get("line_number", "?")
            content = item.get("content", "")
            if item.get("is_blank"):
                continue  # skip blank lines for brevity
            tag = " [comment]" if item.get("is_comment") else ""
            line_parts.append(f"  Line {ln}: {content}{tag}")
        line_text = "\n".join(line_parts) if line_parts else "No code lines found"
    else:
        line_text = "Not provided"

    context_text = rag_context if rag_context else "No additional context"

    # =========================
    # PROMPT TEMPLATE
    # =========================
    prompt = f"""
You are an expert programming evaluator and teacher.

Your task is to evaluate a student's answer based on a given question and sample answer.

----------------------------------------
🔹 Programming Language:
{language}

🔹 Question:
{question}

🔹 Sample Answer:
{sample_answer}

🔹 Student Answer:
{student_answer}

----------------------------------------
🔹 Syntax Analysis:
{syntax_text}

🔹 Structure Analysis:
{structure_text}

🔹 Line-by-Line Analysis (use this to check each part of the student's code):
{line_text}

🔹 Additional Context (RAG):
{context_text}

----------------------------------------

Evaluate the student answer based on the following criteria:

1. Correctness:
   - Does the answer solve the problem correctly?

2. Logical Approach:
   - Is the logic valid and sound?
   - Alternative approaches (e.g., recursion vs loop) are allowed.
   - Use the Line-by-Line Analysis above to trace the student's logic step by step.

3. Edge Cases:
   - Does the code handle edge cases (empty input, zero, null, boundaries)?

4. Completeness:
   - Are all requirements of the question covered?

5. Efficiency:
   - Is the approach efficient (time/space complexity)?

6. Code Quality & Readability:
   - Readability, naming, structure, formatting

----------------------------------------

⚠️ IMPORTANT RULES:

- Students may use different but correct approaches.
- DO NOT penalize valid alternative logic.
- Penalize incorrect logic or incomplete answers.
- Be fair and consistent like a real teacher.
- Use strict but reasonable scoring.
- Base line-level feedback on the Line-by-Line Analysis provided above.

----------------------------------------

📊 RUBRIC SCORING (max points per category):

- correctness  : up to 40 points  — Is the answer logically correct?
- efficiency   : up to 20 points  — Is the approach efficient?
- readability  : up to 15 points  — Is the code readable and well-named?
- structure    : up to 15 points  — Is the code well-structured?

📊 OVERALL SCORE GUIDELINES:

- 90–100 → Fully correct, efficient, handles edge cases, clean code
- 70–89  → Mostly correct, minor issues
- 40–69  → Partially correct, missing logic or edge cases
- 0–39   → Incorrect or irrelevant

----------------------------------------

📌 OUTPUT FORMAT (STRICT JSON ONLY):

{{
  "score": number (0–100, sum of rubric scores below),
  "feedback": "clear explanation of evaluation",
  "strengths": "what the student did well",
  "improvements": "what needs improvement",
  "rubric": {{
    "correctness": number (0–40),
    "efficiency": number (0–20),
    "readability": number (0–15),
    "structure": number (0–15)
  }},
  "concepts": {{
    "logic": "Strong / Good / Weak",
    "edge_cases": "Good / Needs Improvement",
    "completeness": "High / Medium / Low",
    "efficiency": "Good / Average / Poor",
    "readability": "Good / Needs Improvement"
  }}
}}

Do NOT include any extra text outside JSON.
"""

    return prompt
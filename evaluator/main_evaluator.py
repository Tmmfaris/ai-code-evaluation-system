from analysis.syntax_checker import check_syntax
from analysis.line_analyzer import analyze_lines
from analysis.structure_analyzer import analyze_structure

from llm.prompt_builder import build_prompt
from llm.llm_engine import call_llm
from llm.response_parser import parse_llm_response

from evaluator.rubric_engine import calculate_rubric_score
from evaluator.concept_evaluator import evaluate_concepts
from evaluator.scoring_engine import combine_scores

from utils.logger import log_info, log_error, log_request, log_result
from utils.formatter import format_final_output, format_error_response
from utils.helpers import clean_text, normalize_code, is_empty

from config import ENABLE_SYNTAX_CHECK, SUPPORTED_LANGUAGES


# ==============================
# 🔧 SYNTAX CHECK HANDLER
# ==============================
def run_syntax_check(code, language):
    if not ENABLE_SYNTAX_CHECK:
        return {"valid": True, "error": None}

    return check_syntax(code, language)


# ==============================
# 🧠 MAIN PUBLIC FUNCTION
# ==============================
def evaluate_submission(
    student_id,
    question,
    sample_answer,
    student_answer,
    language
):
    """
    Main entry point for evaluation
    """

    try:
        # ==========================
        # 📝 Logging request
        # ==========================
        log_request(student_id, question)

        # ==========================
        # 🧹 Clean inputs
        # ==========================
        question = clean_text(question)
        sample_answer = clean_text(sample_answer)
        student_answer = normalize_code(student_answer)

        # ==========================
        # 🚫 Validate input
        # ==========================
        if is_empty(student_answer):
            return format_error_response(student_id, "Empty student submission")

        # ==========================
        # 🌐 Validate language
        # ==========================
        language = (language or "").lower()
        if language not in SUPPORTED_LANGUAGES:
            language = "general"

        log_info(f"Processing evaluation | Student: {student_id} | Language: {language}")

        # ==========================
        # 1. Syntax Check
        # ==========================
        syntax_result = run_syntax_check(student_answer, language)

        # ==========================
        # 2. Line Analysis
        # ==========================
        line_analysis = analyze_lines(student_answer)

        # ==========================
        # 3. Structure Analysis
        # ==========================
        structure_analysis = analyze_structure(student_answer)

        # ==========================
        # 4. Build Prompt
        # ==========================
        prompt = build_prompt(
            question=question,
            sample_answer=sample_answer,
            student_answer=student_answer,
            language=language,
            syntax_result=syntax_result,
            line_analysis=line_analysis,
            structure_analysis=structure_analysis,
            rag_context=None   # RAG not implemented — future feature: retrieve relevant examples from knowledge base
        )

        # ==========================
        # 5. LLM Evaluation
        # ==========================
        log_info("Calling LLM...")
        raw_llm_output = call_llm(prompt)

        parsed_llm = parse_llm_response(raw_llm_output)

        # ==========================
        # 6. Rubric Scoring
        # ==========================
        rubric_score = calculate_rubric_score(parsed_llm)

        # ==========================
        # 7. Concept Evaluation
        # ==========================
        concept_result = evaluate_concepts(parsed_llm)

        # ==========================
        # 8. Final Score
        # ==========================
        final_score = combine_scores(
            rubric_score=rubric_score,
            concept_score=concept_result
        )


        # ==========================
        # 9. Final Output
        # ==========================
        result = format_final_output(
            student_id=student_id,
            llm_result=parsed_llm,
            rubric_scores=rubric_score
        )

        # Override score with combined score
        result["score"] = final_score
        result["concepts"] = concept_result

        # ==========================
        # 📝 Log result
        # ==========================
        log_result(student_id, final_score)

        return result

    except Exception as e:
        log_error(f"Evaluation failed | Student: {student_id} | Error: {str(e)}")
        return format_error_response(student_id, "Evaluation failed due to system error")
from evaluator.orchestration import apply_confidence_bounds
from llm.llm_engine import call_llm
from llm.prompt_builder import build_audit_prompt, build_comparison_prompt
from llm.response_parser import parse_llm_response

from .feedback_generator import (
    choose_safe_feedback,
    choose_safe_improvement,
    is_clean_llm_text,
)
from .score_calibrator import calibrate_final_score


def compare_answers_with_llm(
    question,
    sample_answer,
    student_answer,
    language,
    question_profile,
    syntax_result,
    line_analysis,
    structure_analysis,
):
    prompt = build_comparison_prompt(
        question=question,
        sample_answer=sample_answer,
        student_answer=student_answer,
        language=language,
        question_profile=question_profile,
        syntax_result=syntax_result,
        line_analysis=line_analysis,
        structure_analysis=structure_analysis,
        rag_context=None,
    )

    raw_llm_output = call_llm(prompt)
    return parse_llm_response(raw_llm_output)


def audit_evaluation_with_llm(
    question,
    sample_answer,
    student_answer,
    language,
    question_profile,
    syntax_result,
    execution_finding,
    rule_findings,
    confidence,
    score,
    feedback,
    improvements,
    rubric_score,
):
    if language in {"python", "java", "html", "javascript"} and not syntax_result.get("valid", True):
        return {
            "score": score,
            "feedback": feedback,
            "improvements": improvements,
        }

    prompt = build_audit_prompt(
        question=question,
        sample_answer=sample_answer,
        student_answer=student_answer,
        language=language,
        initial_score=score,
        initial_feedback=feedback,
        initial_improvements=improvements,
        initial_rubric=rubric_score,
        question_profile=question_profile,
        syntax_result=syntax_result,
        execution_finding=execution_finding,
        rule_findings=rule_findings,
        confidence=confidence,
    )

    raw_audit_output = call_llm(prompt)
    parsed_audit = parse_llm_response(raw_audit_output)
    if parsed_audit.get("_llm_fallback"):
        return {
            "score": score,
            "feedback": feedback,
            "improvements": improvements,
            "_llm_fallback": True,
        }

    corrected_score = calibrate_final_score(
        base_score=score,
        llm_score=parsed_audit.get("score"),
        execution_finding=execution_finding,
        findings=rule_findings,
        syntax_result=syntax_result,
        language=language,
    )
    corrected_score = apply_confidence_bounds(
        score=corrected_score,
        confidence=confidence,
        execution_finding=execution_finding,
        question_profile=question_profile,
    )

    constrained_by_rules = any(
        (item or {}).get("type") in {
            "hard_fail",
            "correctness_cap",
            "efficiency_cap",
            "correct_solution_with_penalty",
            "equivalent_solution",
        }
        for item in (rule_findings or [])
    )

    if constrained_by_rules:
        corrected_feedback = feedback
        corrected_improvements = improvements
    else:
        corrected_feedback = choose_safe_feedback(parsed_audit.get("feedback"), feedback)
        corrected_improvements = choose_safe_improvement(parsed_audit.get("improvements"), improvements)

    return {
        "score": corrected_score,
        "feedback": corrected_feedback,
        "improvements": corrected_improvements,
        "_llm_fallback": False,
    }


def should_audit_with_llm(confidence, execution_finding, rule_findings, feedback, improvements):
    result_type = (execution_finding or {}).get("result_type")
    has_hard_fail = any((item or {}).get("type") == "hard_fail" for item in (rule_findings or []))
    has_strict_rule_cap = any(
        (item or {}).get("type") in {"hard_fail", "correctness_cap", "efficiency_cap", "correct_solution_with_penalty", "equivalent_solution"}
        for item in (rule_findings or [])
    )
    clean_feedback = is_clean_llm_text(feedback)
    clean_improvements = not improvements or is_clean_llm_text(improvements)

    if not execution_finding and has_strict_rule_cap:
        return False

    if has_strict_rule_cap and clean_feedback and clean_improvements:
        return False

    if confidence != "high":
        return True

    if not execution_finding:
        return True

    if result_type in {"partial_pass", "mostly_correct"} and clean_feedback and clean_improvements:
        return False

    if result_type in {"partial_pass", "mostly_correct"} and not (has_strict_rule_cap and clean_feedback and clean_improvements):
        return True

    if not clean_feedback or not clean_improvements:
        return True

    if has_hard_fail and result_type in {"zero_pass", "execution_error"}:
        return False

    if has_strict_rule_cap and result_type in {"partial_pass", "mostly_correct", "zero_pass", "execution_error"}:
        return False

    if result_type in {"full_pass", "correct_but_inefficient", "zero_pass", "execution_error"}:
        return False

    return True

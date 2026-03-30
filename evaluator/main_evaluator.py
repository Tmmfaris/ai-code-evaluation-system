from analysis.syntax_checker import check_syntax
from analysis.line_analyzer import analyze_lines
from analysis.structure_analyzer import analyze_structure

from llm.prompt_builder import build_prompt
from llm.llm_engine import call_llm
from llm.response_parser import parse_llm_response

from evaluator.rubric_engine import calculate_rubric_score
from evaluator.concept_evaluator import evaluate_concepts
from evaluator.execution_engine import analyze_execution
from evaluator.rule_engine import analyze_submission_rules, apply_rule_adjustments
from evaluator.scoring_engine import combine_scores

from utils.logger import log_info, log_error, log_request, log_result
from utils.formatter import format_final_output, format_error_response
from utils.helpers import clean_text, normalize_code, is_empty

from config import ENABLE_SYNTAX_CHECK, SUPPORTED_LANGUAGES



def run_syntax_check(code, language):
    if not ENABLE_SYNTAX_CHECK:
        return {"valid": True, "error": None}

    return check_syntax(code, language)



def normalize_score(score, concepts, rubric_score):
    logic = concepts.get("logic")
    completeness = concepts.get("completeness")
    correctness = rubric_score.get("correctness", 0) if isinstance(rubric_score, dict) else 0

    if logic == "Strong" and score < 70:
        return max(score, 70)

    if logic == "Weak" and completeness == "Low" and correctness <= 5 and score > 12:
        return min(score, 12)

    if logic == "Weak" and completeness == "Low" and score > 18:
        return min(score, 18)

    if logic == "Weak" and completeness == "Medium" and score < 60:
        return max(score, 60)

    return score



def cleanup_improvements(improvements, rubric_score, concepts):
    text = (improvements or "").strip()
    if not text:
        return text

    correctness = rubric_score.get("correctness", 0)
    efficiency = rubric_score.get("efficiency", 0)
    logic = concepts.get("logic")

    noisy_phrases = (
        "use built-in",
        "consider using the provided solution",
        "for consistency",
        "shorter built-in alternative",
        "add comments",
        "comments for clarity",
    )

    if correctness >= 36 and logic == "Strong" and efficiency >= 17:
        lowered = text.lower()
        if any(phrase in lowered for phrase in noisy_phrases):
            return ""

    return text



def relax_readability_for_simple_correct_code(rubric_score, structure_analysis):
    if not isinstance(rubric_score, dict):
        return rubric_score

    if not isinstance(structure_analysis, dict):
        return rubric_score

    correctness = rubric_score.get("correctness", 0)
    efficiency = rubric_score.get("efficiency", 0)
    readability = rubric_score.get("readability", 0)
    structure = rubric_score.get("structure", 0)
    line_count = structure_analysis.get("line_count", 0)
    if (
        correctness >= 36
        and efficiency >= 17
        and structure >= 13
        and line_count <= 6
        and readability < 15
    ):
        rubric_score = dict(rubric_score)
        rubric_score["readability"] = 15

    return rubric_score



def build_deterministic_result(execution_finding, structure_analysis):
    result_type = (execution_finding or {}).get("result_type")
    line_count = structure_analysis.get("line_count", 0) if isinstance(structure_analysis, dict) else 0

    if result_type == "full_pass":
        readability = 15 if line_count <= 6 else 13
        rubric = {
            "correctness": 40,
            "efficiency": 20,
            "readability": readability,
            "structure": 15,
        }
    elif result_type == "correct_but_inefficient":
        readability = 15 if line_count <= 6 else 13
        rubric = {
            "correctness": 36,
            "efficiency": 12,
            "readability": readability,
            "structure": 15,
        }
    elif result_type == "partial_pass":
        rubric = {
            "correctness": 28,
            "efficiency": 15,
            "readability": 10,
            "structure": 12,
        }
    elif result_type == "execution_error":
        rubric = {
            "correctness": 5,
            "efficiency": 5,
            "readability": 8,
            "structure": 8,
        }
    else:
        rubric = {
            "correctness": 5,
            "efficiency": 5,
            "readability": 8,
            "structure": 10,
        }

    return {
        "score": 0,
        "feedback": execution_finding.get("feedback", ""),
        "improvements": execution_finding.get("suggestion", ""),
        "rubric": rubric,
    }


def build_exact_match_feedback(question, language):
    lowered = (question or "").lower()
    language = (language or "").lower()
    noun = "method" if language == "java" else ("function" if language == "python" else "solution")

    if "add two numbers" in lowered:
        return f"The student answer exactly matches the expected {noun} for adding two numbers."
    if "sum of all elements" in lowered or "sum elements" in lowered:
        return f"The student answer exactly matches the expected {noun} for summing all elements."
    if "sum of digits" in lowered or "sum digits" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating the sum of digits."
    if "count words" in lowered:
        return f"The student answer exactly matches the expected {noun} for counting words."
    if "even" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking even numbers."
    if "reverse" in lowered and "string" in lowered:
        return f"The student answer exactly matches the expected {noun} for reversing a string."
    if "reverse" in lowered and "list" in lowered:
        return f"The student answer exactly matches the expected {noun} for reversing a list."
    if "remove spaces" in lowered:
        return f"The student answer exactly matches the expected {noun} for removing spaces."
    if "remove duplicates" in lowered or "duplicate" in lowered:
        return f"The student answer exactly matches the expected {noun} for removing duplicates."
    if "lowercase" in lowered:
        return f"The student answer exactly matches the expected {noun} for converting text to lowercase."
    if "convert" in lowered and "uppercase" in lowered:
        return f"The student answer exactly matches the expected {noun} for converting text to uppercase."
    if "uppercase" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking uppercase text."
    if "square" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating a square."
    if "cube" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating a cube."
    if "minimum" in lowered or "min" in lowered:
        return f"The student answer exactly matches the expected {noun} for finding the minimum value."
    if "maximum" in lowered or "max" in lowered:
        return f"The student answer exactly matches the expected {noun} for finding the maximum value."
    if "palindrome" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking palindromes."
    if "only digits" in lowered or "isdigit" in lowered or "numeric" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking digit-only text."
    if "factorial" in lowered:
        return f"The student answer exactly matches the expected {noun} for calculating factorial."
    if "prime" in lowered:
        return f"The student answer exactly matches the expected {noun} for checking prime numbers."

    return f"The student answer exactly matches the expected {noun} and is fully correct."


def build_exact_match_result(question, language, structure_analysis):
    line_count = structure_analysis.get("line_count", 0) if isinstance(structure_analysis, dict) else 0
    readability = 15 if line_count <= 6 else 13

    return {
        "score": 0,
        "feedback": build_exact_match_feedback(question, language),
        "improvements": "",
        "rubric": {
            "correctness": 40,
            "efficiency": 20,
            "readability": readability,
            "structure": 15,
        },
    }



def evaluate_submission(student_id, question, sample_answer, student_answer, language):
    """
    Main entry point for evaluation.
    """

    try:
        log_request(student_id, question)

        question = clean_text(question)
        sample_answer = clean_text(sample_answer)
        student_answer = normalize_code(student_answer)

        if is_empty(student_answer):
            return format_error_response(student_id, "Empty student submission")

        language = (language or "").lower()
        if language not in SUPPORTED_LANGUAGES:
            language = "general"

        log_info(f"Processing evaluation | Student: {student_id} | Language: {language}")

        structure_analysis = analyze_structure(student_answer)
        if normalize_code(sample_answer) == student_answer:
            log_info(
                f"Evaluation path | Student: {student_id} | Language: {language} | Mode: exact_match"
            )
            parsed_llm = build_exact_match_result(
                question=question,
                language=language,
                structure_analysis=structure_analysis,
            )
            rubric_score = dict(parsed_llm["rubric"])
            concept_result = evaluate_concepts(parsed_llm)
            final_score = combine_scores(
                rubric_score=rubric_score,
                concept_score=concept_result,
            )
            final_score = normalize_score(final_score, concept_result, rubric_score)
            result = format_final_output(
                student_id=student_id,
                llm_result=parsed_llm,
                rubric_scores=rubric_score,
            )
            result["score"] = final_score
            result["concepts"] = concept_result
            result["suggestions"] = ""
            log_result(student_id, final_score)
            return result

        syntax_result = run_syntax_check(student_answer, language)
        line_analysis = analyze_lines(student_answer)

        rule_findings = analyze_submission_rules(
            question=question,
            student_answer=student_answer,
            language=language,
        )
        execution_finding = analyze_execution(
            question=question,
            sample_answer=sample_answer,
            student_answer=student_answer,
            language=language,
        )
        if execution_finding:
            rule_findings.append(execution_finding)

        if language in {"python", "java"} and execution_finding:
            log_info(
                f"Evaluation path | Student: {student_id} | Language: {language} | Mode: deterministic | "
                f"Type: {execution_finding.get('result_type', 'unknown')}"
            )
            parsed_llm = build_deterministic_result(
                execution_finding=execution_finding,
                structure_analysis=structure_analysis,
            )
            rubric_score = dict(parsed_llm["rubric"])
        else:
            reason = "no deterministic pattern matched"
            if language not in {"python", "java"}:
                reason = "language not on deterministic path"
            log_info(
                f"Evaluation path | Student: {student_id} | Language: {language} | Mode: llm | Reason: {reason}"
            )
            prompt = build_prompt(
                question=question,
                sample_answer=sample_answer,
                student_answer=student_answer,
                language=language,
                syntax_result=syntax_result,
                line_analysis=line_analysis,
                structure_analysis=structure_analysis,
                rag_context=None,
            )

            log_info("Calling LLM...")
            raw_llm_output = call_llm(prompt)
            parsed_llm = parse_llm_response(raw_llm_output)
            rubric_score = calculate_rubric_score(parsed_llm)

        rubric_score, parsed_llm["feedback"], parsed_llm["improvements"] = apply_rule_adjustments(
            rubric_score=rubric_score,
            feedback=parsed_llm.get("feedback", ""),
            suggestions=parsed_llm.get("improvements", ""),
            findings=rule_findings,
        )
        rubric_score = relax_readability_for_simple_correct_code(
            rubric_score=rubric_score,
            structure_analysis=structure_analysis,
        )
        parsed_llm["rubric"] = rubric_score

        concept_result = evaluate_concepts(parsed_llm)

        final_score = combine_scores(
            rubric_score=rubric_score,
            concept_score=concept_result,
        )
        final_score = normalize_score(final_score, concept_result, rubric_score)

        result = format_final_output(
            student_id=student_id,
            llm_result=parsed_llm,
            rubric_scores=rubric_score,
        )

        result["score"] = final_score
        result["concepts"] = concept_result
        result["suggestions"] = cleanup_improvements(
            result.get("suggestions", ""),
            rubric_score,
            concept_result,
        )

        log_result(student_id, final_score)
        return result

    except Exception as exc:
        log_error(f"Evaluation failed | Student: {student_id} | Error: {str(exc)}")
        return format_error_response(student_id, "Evaluation failed due to system error")

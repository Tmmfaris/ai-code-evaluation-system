from .generic_rules import analyze_generic_requirements, apply_rule_adjustments
from .java_rules import analyze_java_submission_rules
from .python_rules import analyze_python_submission_rules


def analyze_submission_rules(question, student_answer, language):
    language = (language or "").lower()

    if language == "java":
        return analyze_java_submission_rules(question, student_answer)
    if language == "python":
        return analyze_python_submission_rules(question, student_answer)
    return analyze_generic_requirements(question, student_answer, language)

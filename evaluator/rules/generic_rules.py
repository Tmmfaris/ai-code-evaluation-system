from . import shared


def analyze_generic_requirements(question, student_answer, language):
    return shared._generic_requirement_findings(question, student_answer, language)


def analyze_question_risk(question, language, question_profile=None):
    return shared.analyze_question_risk(question, language, question_profile)


def apply_rule_adjustments(rubric_score, feedback, suggestions, findings):
    return shared.apply_rule_adjustments(rubric_score, feedback, suggestions, findings)

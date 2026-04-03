from copy import deepcopy
import hashlib
from pathlib import Path

from .generic_rules import analyze_generic_requirements, analyze_question_risk as _analyze_question_risk, apply_rule_adjustments
from .java_rules import analyze_java_submission_rules
from .python_rules import analyze_python_submission_rules
from .css_rules import analyze_css_submission_rules
from .react_rules import analyze_react_submission_rules
from .mysql_rules import analyze_mysql_submission_rules
from .mongodb_rules import analyze_mongodb_submission_rules


def _freeze_cache_value(value):
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze_cache_value(val)) for key, val in value.items()))
    if isinstance(value, list):
        return tuple(_freeze_cache_value(item) for item in value)
    return value


def _build_rules_cache_version():
    base_dir = Path(__file__).resolve().parent
    fingerprint_paths = [
        base_dir / "__init__.py",
        base_dir / "shared.py",
        base_dir / "java_rules.py",
        base_dir / "python_rules.py",
        base_dir / "generic_rules.py",
    ]
    digest = hashlib.sha256()
    for path in fingerprint_paths:
        try:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            digest.update(f"{path.name}:missing".encode("utf-8"))
    return digest.hexdigest()


def _analyze_submission_rules_cached(cache_version, question, student_answer, language):
    language = (language or "").lower()

    if language == "java":
        return tuple(analyze_java_submission_rules(question, student_answer))
    if language == "python":
        return tuple(analyze_python_submission_rules(question, student_answer))
    if language == "css":
        return tuple(analyze_css_submission_rules(question, student_answer))
    if language == "react":
        return tuple(analyze_react_submission_rules(question, student_answer))
    if language == "mysql":
        return tuple(analyze_mysql_submission_rules(question, student_answer))
    if language == "mongodb":
        return tuple(analyze_mongodb_submission_rules(question, student_answer))
    return tuple(analyze_generic_requirements(question, student_answer, language))


def analyze_submission_rules(question, student_answer, language):
    return deepcopy(
        list(
            _analyze_submission_rules_cached(
                _build_rules_cache_version(),
                question or "",
                student_answer or "",
                language or "",
            )
        )
    )

def _analyze_question_risk_cached(cache_version, question, language, question_profile_key):
    profile = dict(question_profile_key) if isinstance(question_profile_key, tuple) else None
    return tuple(_analyze_question_risk(question, language, profile))


def analyze_question_risk(question, language, question_profile=None):
    profile_key = _freeze_cache_value(question_profile or {}) if isinstance(question_profile, dict) else None
    return deepcopy(
        list(
            _analyze_question_risk_cached(
                _build_rules_cache_version(),
                question or "",
                language or "",
                profile_key,
            )
        )
    )

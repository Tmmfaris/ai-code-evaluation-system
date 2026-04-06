from copy import deepcopy
import hashlib
from pathlib import Path

from evaluator.orchestration.pipeline import evaluate_submission as _evaluate_submission_uncached


def _build_evaluator_cache_version():
    base_dir = Path(__file__).resolve().parent
    fingerprint_paths = [
        base_dir / "main_evaluator.py",
        base_dir / "orchestration" / "pipeline.py",
        base_dir / "execution" / "shared.py",
        base_dir / "rules" / "shared.py",
        base_dir / "comparison" / "logic_summary.py",
        base_dir / "comparison" / "score_calibrator.py",
    ]
    digest = hashlib.sha256()
    for path in fingerprint_paths:
        try:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            digest.update(f"{path.name}:missing".encode("utf-8"))
    return digest.hexdigest()


def evaluate_submission(student_id, question, sample_answer, student_answer, language, reference_answers=None, question_metadata=None):
    result = deepcopy(
        _evaluate_submission_uncached(
            "cache",
            question,
            sample_answer,
            student_answer,
            language,
            reference_answers=reference_answers,
            question_metadata=question_metadata,
        )
    )
    result["student_id"] = student_id
    return result


__all__ = ["evaluate_submission"]

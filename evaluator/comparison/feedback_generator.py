import re


def cleanup_improvements(improvements, rubric_score, concepts):
    text = _sanitize_llm_text(improvements)
    if not text:
        return ""

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


def _sanitize_llm_text(text):
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    suspicious_fragments = (
        "ayer code:",
        "written in english",
        "<|assistant|>",
        "<|user|>",
        '"rubric"',
        '"score"',
        "corrected solution",
        "corrected code",
    )
    lowered = cleaned.lower()
    if any(fragment in lowered for fragment in suspicious_fragments):
        return ""

    if cleaned.count("{") or cleaned.count("}"):
        return ""

    if len(cleaned) < 8:
        return ""

    return cleaned


def is_clean_llm_text(text):
    return bool(_sanitize_llm_text(text))


def choose_safe_feedback(audit_feedback, fallback_feedback):
    cleaned = _sanitize_llm_text(audit_feedback)
    return cleaned or (fallback_feedback or "").strip()


def choose_safe_improvement(audit_improvement, fallback_improvement):
    cleaned = _sanitize_llm_text(audit_improvement)
    return cleaned or (fallback_improvement or "").strip()


def sanitize_text_or_fallback(text, fallback=""):
    cleaned = _sanitize_llm_text(text)
    return cleaned or (fallback or "").strip()

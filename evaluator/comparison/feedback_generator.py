import re


def _infer_feedback_context(question="", language="", template_family=""):
    question_text = (question or "").lower()
    family = (template_family or "").lower()
    context = {
        "question": question_text,
        "language": (language or "").lower(),
        "template_family": family,
    }
    if any(
        token in question_text
        for token in (
            "first and last character",
            "first character",
            "last character",
            "string",
            "substring",
            "slice",
        )
    ) or "string" in family:
        context["domain"] = "strings"
    elif any(
        token in question_text
        for token in (
            "list",
            "array",
            "length",
            "len(",
            "elements",
        )
    ) or "list" in family:
        context["domain"] = "lists"
    elif any(
        token in question_text
        for token in (
            "number",
            "multiple",
            "divisible",
            "prime",
            "factorial",
            "sum of digits",
        )
    ) or "number" in family:
        context["domain"] = "numbers"
    else:
        context["domain"] = ""
    return context


def _is_feedback_relevant(text, question="", language="", template_family=""):
    cleaned = _sanitize_llm_text(text)
    if not cleaned:
        return False

    lowered = cleaned.lower()
    context = _infer_feedback_context(
        question=question,
        language=language,
        template_family=template_family,
    )
    domain = context.get("domain", "")

    if domain == "strings":
        irrelevant_terms = (
            "f-string",
            "f string",
            "formatted string",
            "interpolation",
            "print formatting",
            "dataframe",
            "numpy",
            "matplotlib",
            "django",
            "fastapi",
        )
        if any(term in lowered for term in irrelevant_terms):
            return False

    if domain == "lists":
        irrelevant_terms = (
            "f-string",
            "f string",
            "formatted string",
            "interpolation",
        )
        if any(term in lowered for term in irrelevant_terms):
            return False

    return True


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
    cleaned = _dedupe_sentences(cleaned)
    if re.search(r"\bdoes not\b\s*$", cleaned.lower()):
        return ""
    if cleaned.lower() in {"the provided solution", "the solution", "the function", "the code"}:
        return ""
    if "`" in cleaned:
        return ""

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


def _dedupe_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    seen = set()
    kept = []
    for sentence in sentences:
        normalized = sentence.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        kept.append(sentence.strip())
    return " ".join(kept).strip()


def is_clean_llm_text(text):
    return bool(_sanitize_llm_text(text))


def choose_safe_feedback(audit_feedback, fallback_feedback, question="", language="", template_family=""):
    cleaned = _sanitize_llm_text(audit_feedback)
    if cleaned and _is_feedback_relevant(
        cleaned,
        question=question,
        language=language,
        template_family=template_family,
    ):
        return cleaned
    return (fallback_feedback or "").strip()


def choose_safe_improvement(audit_improvement, fallback_improvement, question="", language="", template_family=""):
    cleaned = _sanitize_llm_text(audit_improvement)
    if cleaned and _is_feedback_relevant(
        cleaned,
        question=question,
        language=language,
        template_family=template_family,
    ):
        return cleaned
    return (fallback_improvement or "").strip()


def sanitize_text_or_fallback(text, fallback="", question="", language="", template_family=""):
    cleaned = _sanitize_llm_text(text)
    if cleaned and _is_feedback_relevant(
        cleaned,
        question=question,
        language=language,
        template_family=template_family,
    ):
        return cleaned
    return (fallback or "").strip()

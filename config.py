# ==============================
# 🔧 GENERAL CONFIGURATION
# ==============================

import os

APP_NAME = "AI Intelligent Evaluation Model"
VERSION = "2.0"

ENABLE_RAG = False          # ❌ disable (not needed now)
ENABLE_LOGGING = True


# ==============================
# 🤖 LLM CONFIGURATION
# ==============================

# Provider: "llama_cpp" (GGUF) or "ollama"
LLM_PROVIDER = "llama_cpp"

# =========================
# 🧠 GGUF MODEL SETTINGS
# =========================

# Path to your model
GGUF_MODEL_PATH = "models/Phi-3-mini-4k-instruct-q4.gguf"

# ⚡ Performance tuning
N_CTX = 512             # conservative for 8 GB RAM
N_THREADS = 4           # conservative for 8 GB RAM
N_GPU_LAYERS = 0        # keep 0 (CPU mode)

# =========================
# 🔁 OLLAMA (FALLBACK)
# =========================

LLM_MODEL = "phi3-gguf"
OLLAMA_BASE_URL = "http://localhost:11434/api/generate"

# =========================
# ⚙️ LLM PARAMETERS
# =========================

LLM_TEMPERATURE = 0.1     # stable output
LLM_MAX_TOKENS = 150      # compact JSON with a little extra headroom


# ==============================
# 📊 RUBRIC SCORING
# ==============================

RUBRIC_WEIGHTS = {
    "correctness": 40,
    "efficiency": 20,
    "readability": 15,
    "structure": 15
}

TOTAL_SCORE = 100


# ==============================
# 🧠 CONCEPT EVALUATION
# ==============================

CONCEPT_WEIGHTS = {
    "logic": 4,
    "edge_cases": 2,
    "completeness": 2,
    "efficiency": 1,
    "readability": 1
}


# ==============================
# 📚 RAG (DISABLED)
# ==============================

KNOWLEDGE_BASE_PATH = "rag/knowledge_base/"
TOP_K_RESULTS = 3


# ==============================
# 🔍 ANALYSIS SETTINGS
# ==============================

ENABLE_SYNTAX_CHECK = True
ENABLE_LINE_ANALYSIS = True
ENABLE_STRUCTURE_ANALYSIS = True


# ==============================
# ⚠️ ERROR HANDLING
# ==============================

DEFAULT_SCORE_ON_ERROR = 50
DEFAULT_FEEDBACK_ON_ERROR = "Evaluation failed. Default scoring applied."


# ==============================
# 🧪 SUPPORTED LANGUAGES
# ==============================

SUPPORTED_LANGUAGES = [
    "python",
    "java",
    "html",
    "javascript",
    "css",
    "react",
    "mongodb",
    "mysql",
]


# ==============================
# 📝 PROMPT SETTINGS
# ==============================

STRICT_JSON_OUTPUT = True
MAX_FEEDBACK_LENGTH = 250   # ⚡ reduced


# ==============================
# ⏱ PERFORMANCE SETTINGS
# ==============================

MAX_EXECUTION_TIME = 8   # ⚡ reduced from 10


# ==============================
# QUESTION PROFILE STORAGE
# ==============================

QUESTION_PROFILE_BACKEND = os.getenv("AI_EVAL_QUESTION_PROFILE_BACKEND", "sqlite")
QUESTION_PROFILE_STORE_PATH = os.getenv("AI_EVAL_QUESTION_PROFILE_STORE_PATH", "data/question_profiles.json")
QUESTION_PROFILE_DB_PATH = os.getenv("AI_EVAL_QUESTION_PROFILE_DB_PATH", "data/question_profiles.db")


# ==============================
# AUTO RULE GENERATION
# ==============================

AUTO_GENERATE_QUESTION_RULES = True
AUTO_FILL_MISSING_REGISTRATION_FIELDS = True
AUTO_GENERATE_MAX_ALTERNATIVES = 3
AUTO_GENERATE_MAX_HIDDEN_TESTS = 8
ORACLE_TEST_CASES_BASE = 15
ORACLE_TEST_CASES_EXPANDED = 30
QUESTION_REGISTER_MAX_ATTEMPTS = 5  # retries per question when LLM is disabled
QUESTION_REGISTER_HARD_MAX_ATTEMPTS = 12  # hard cap for non-LLM repair loops
QUESTION_REGISTER_LLM_MAX_ATTEMPTS = 1  # cap GGUF register attempts to avoid local hangs
QUESTION_REGISTER_LLM_REPAIR_ATTEMPTS = 1  # one tiny JSON-only repair call if GGUF returns malformed registration JSON
STARTUP_REFRESH_USES_LLM = False  # avoid GGUF repair loops during uvicorn reload/startup
AUTO_ACTIVATE_VALIDATED_QUESTIONS = True
REQUIRE_VALIDATED_QUESTION_PACKAGE = True
STRICT_EVALUATION_BY_QUESTION_ID = True
REQUIRE_FACULTY_APPROVAL_FOR_LIVE = False
MIN_PACKAGE_CONFIDENCE_FOR_EXAM = 0.75
FORCE_LLM_WHEN_NOT_DETERMINISTIC = False
LLM_REVIEW_MAX_ATTEMPTS = 3
ALWAYS_LLM_REVIEW = False
AUTO_REPAIR_BAD_PACKAGES = True
LLM_REPHRASE_FEEDBACK = True
LLM_GENERATE_FEEDBACK_ALWAYS = False
LLM_REVIEW_HARD_MAX_ATTEMPTS = 8
LLM_ALLOW_SCORE_AUDIT = False
DETERMINISTIC_PACKAGE_SCORING_ONLY = True
REQUIRE_PACKAGE_COVERAGE_FOR_REGISTRATION = False
EXECUTION_SCORE_BOUNDS = {
    "full_pass_min": 90,
    "zero_pass_max": 10,
    "partial_pass_max": 70,
    "mostly_correct_min": 60,
    "mostly_correct_max": 85,
    "correct_but_inefficient_min": 80,
    "pass_ratio_caps": [
        (0.2, 20),
        (0.5, 50),
        (0.8, 75),
        (1.0, 85),
    ],
}
REGISTER_STRICT_VALIDATE = False
REGISTER_STRICT_MIN_CONFIDENCE = 0.9
REGISTER_REJECT_GENERIC_TEMPLATES = True
REGISTER_REQUIRE_LLM_ASSISTANCE = True
MONITOR_SUSPICIOUS_EVALUATIONS = True
SUSPICIOUS_EVALUATION_MAX_REASONABLE_SCORE = 20
SUSPICIOUS_FEEDBACK_MIN_LENGTH = 24


# ==============================
# PACKAGE / RUNTIME FEATURE MAPS
# ==============================

QUESTION_PACKAGE_FEATURES = {
    "llm_generation": AUTO_GENERATE_QUESTION_RULES,
    "auto_activate_validated": AUTO_ACTIVATE_VALIDATED_QUESTIONS,
    "require_faculty_approval": REQUIRE_FACULTY_APPROVAL_FOR_LIVE,
    "min_exam_confidence": MIN_PACKAGE_CONFIDENCE_FOR_EXAM,
}

EVALUATION_RUNTIME_FEATURES = {
    "require_validated_package": REQUIRE_VALIDATED_QUESTION_PACKAGE,
    "strict_question_id_mode": STRICT_EVALUATION_BY_QUESTION_ID,
}

HIDDEN_TEST_RUNTIME_FEATURES = {
    "python": True,
    "java": True,
    "javascript": True,
    "html": False,
    "css": False,
    "react": False,
    "mysql": False,
    "mongodb": False,
}


# ==============================
# EVALUATION HISTORY STORAGE
# ==============================

EVALUATION_HISTORY_BACKEND = "sqlite"
EVALUATION_HISTORY_DB_PATH = os.getenv("AI_EVAL_EVALUATION_HISTORY_DB_PATH", "data/evaluation_history.db")


# ==============================
# QUESTION LEARNING STORAGE
# ==============================

QUESTION_LEARNING_DB_PATH = os.getenv("AI_EVAL_QUESTION_LEARNING_DB_PATH", "data/question_learning.db")

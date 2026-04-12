# ==============================
# 🔧 GENERAL CONFIGURATION
# ==============================

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

QUESTION_PROFILE_BACKEND = "sqlite"
QUESTION_PROFILE_STORE_PATH = "data/question_profiles.json"
QUESTION_PROFILE_DB_PATH = "data/question_profiles.db"


# ==============================
# AUTO RULE GENERATION
# ==============================

AUTO_GENERATE_QUESTION_RULES = True
AUTO_GENERATE_MAX_ALTERNATIVES = 3
AUTO_GENERATE_MAX_HIDDEN_TESTS = 5
QUESTION_REGISTER_MAX_ATTEMPTS = 5  # retries per question when LLM is enabled
QUESTION_REGISTER_HARD_MAX_ATTEMPTS = 12  # hard cap for register endpoint when chasing a fully-correct package
AUTO_ACTIVATE_VALIDATED_QUESTIONS = True
REQUIRE_VALIDATED_QUESTION_PACKAGE = False
STRICT_EVALUATION_BY_QUESTION_ID = True
REQUIRE_FACULTY_APPROVAL_FOR_LIVE = True
MIN_PACKAGE_CONFIDENCE_FOR_EXAM = 0.75
FORCE_LLM_WHEN_NOT_DETERMINISTIC = True
LLM_REVIEW_MAX_ATTEMPTS = 3
ALWAYS_LLM_REVIEW = True
AUTO_REPAIR_BAD_PACKAGES = True
LLM_REPHRASE_FEEDBACK = True
LLM_REVIEW_HARD_MAX_ATTEMPTS = 8


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
EVALUATION_HISTORY_DB_PATH = "data/evaluation_history.db"


# ==============================
# QUESTION LEARNING STORAGE
# ==============================

QUESTION_LEARNING_DB_PATH = "data/question_learning.db"

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
N_CTX = 1024            # prompt ~200 tok + response ~130 tok; 1024 is plenty
N_THREADS = 8           # 👉 set 6–8 if strong CPU
N_GPU_LAYERS = 0        # keep 0 (CPU mode)

# =========================
# 🔁 OLLAMA (FALLBACK)
# =========================

LLM_MODEL = "mistral"
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
    "javascript"
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

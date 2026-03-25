# ==============================
# 🔧 GENERAL CONFIGURATION
# ==============================

APP_NAME = "AI Intelligent Evaluation Model"
VERSION = "1.0"

# Enable / Disable features
ENABLE_RAG = True
ENABLE_LOGGING = True


# ==============================
# 🤖 LLM CONFIGURATION
# ==============================

# Local LLM (Ollama)
LLM_PROVIDER = "ollama"
LLM_MODEL = "mistral"   # options: mistral, codellama, llama3

# Ollama API URL
OLLAMA_BASE_URL = "http://localhost:11434/api/generate"

# LLM parameters
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 1000


# ==============================
# 📊 RUBRIC SCORING WEIGHTS
# ==============================

RUBRIC_WEIGHTS = {
    "correctness": 40,
    "efficiency": 20,
    "readability": 15,
    "structure": 15
}

# Total = 90 (remaining handled by concept/LLM)
TOTAL_SCORE = 100


# ==============================
# 🧠 CONCEPT EVALUATION WEIGHTS
# ==============================

CONCEPT_WEIGHTS = {
    "logic": 4,
    "edge_cases": 2,
    "completeness": 2,
    "efficiency": 1,
    "readability": 1
}
# Total concept max = 10, rubric max = 90, combined max = 100


# ==============================
# 📚 RAG CONFIGURATION
# ==============================

# Path to knowledge base
KNOWLEDGE_BASE_PATH = "rag/knowledge_base/"

# Retrieval settings
TOP_K_RESULTS = 3


# ==============================
# 🔍 ANALYSIS SETTINGS
# ==============================

# Syntax check enabled
ENABLE_SYNTAX_CHECK = True

# Line analysis enabled
ENABLE_LINE_ANALYSIS = True

# Structure analysis enabled
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
    "json"
]


# ==============================
# 📝 PROMPT SETTINGS
# ==============================

STRICT_JSON_OUTPUT = True
MAX_FEEDBACK_LENGTH = 300


# ==============================
# ⏱ PERFORMANCE SETTINGS
# ==============================

MAX_EXECUTION_TIME = 10  # seconds
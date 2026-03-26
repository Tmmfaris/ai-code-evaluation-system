import requests
import time

from config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL, LLM_MODEL,
    LLM_TEMPERATURE, LLM_MAX_TOKENS,
    GGUF_MODEL_PATH, N_CTX, N_THREADS, N_GPU_LAYERS
)

# =========================
# CONFIGURATION
# =========================
TIMEOUT = 120       # reduced (GGUF is fast)
MAX_RETRIES = 2     # faster retry

# Fallback response
_FALLBACK_JSON = (
    '{"score": 50, "feedback": "LLM evaluation failed. Please try again.", '
    '"strengths": "", "improvements": "", "concepts": {'
    '"logic": "Unknown", "edge_cases": "Unknown", "completeness": "Unknown", '
    '"efficiency": "Unknown", "readability": "Unknown"}, '
    '"rubric": {"correctness": 0, "efficiency": 0, "readability": 0, "structure": 0}}'
)

# =========================
# GGUF MODEL INSTANCE
# =========================
_llm_instance = None


def _get_llm_instance():
    """
    Load GGUF model once (singleton pattern)
    """
    global _llm_instance

    if _llm_instance is None:
        try:
            from llama_cpp import Llama

            print(f"[LLM] Loading GGUF model from: {GGUF_MODEL_PATH}")

            _llm_instance = Llama(
                model_path=GGUF_MODEL_PATH,
                n_ctx=N_CTX,
                n_threads=N_THREADS,
                n_batch=512,
                n_gpu_layers=N_GPU_LAYERS,
                verbose=False
            )

            print("[LLM] GGUF model loaded successfully")

        except Exception as e:
            raise RuntimeError(f"[LLM] Failed to load GGUF model: {e}")

    return _llm_instance


# =========================
# GGUF INFERENCE ENGINE
# =========================
def _call_llama_cpp(prompt):
    """
    Fast local inference using GGUF (llama-cpp-python)
    """
    try:
        llm = _get_llm_instance()

        print("[LLM] Running GGUF inference...")

        output = llm(
            prompt,
            max_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
            top_k=1,
            top_p=1.0,
            repeat_penalty=1.0,
            stop=["\n"],    # compact JSON has no newlines — stop the instant it ends
            echo=False
        )

        text = output["choices"][0]["text"].strip()

        print("[LLM] GGUF inference complete")

        return text if text else _FALLBACK_JSON

    except Exception as e:
        print(f"[LLM] GGUF ERROR: {e}")
        return _FALLBACK_JSON


# =========================
# OLLAMA ENGINE (FALLBACK)
# =========================
def _call_ollama(prompt):
    """
    External Ollama API (fallback only)
    """
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[LLM] Ollama request (attempt {attempt + 1})...")

            response = requests.post(
                OLLAMA_BASE_URL,
                json={
                    "model": LLM_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": LLM_TEMPERATURE,
                        "num_predict": LLM_MAX_TOKENS
                    }
                },
                timeout=TIMEOUT
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            data = response.json()

            if "response" not in data:
                raise Exception("Invalid response format")

            print("[LLM] Ollama response received")

            return data["response"]

        except Exception as e:
            print(f"[LLM] Ollama ERROR: {e}")

            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
            else:
                print("[LLM] Final failure → fallback response")
                return _FALLBACK_JSON


# =========================
# MAIN ENTRY FUNCTION
# =========================
def call_llm(prompt):
    """
    Main router:
    - llama_cpp → GGUF local inference
    - ollama    → external API fallback
    """
    if LLM_PROVIDER == "llama_cpp":
        return _call_llama_cpp(prompt)
    else:
        return _call_ollama(prompt)
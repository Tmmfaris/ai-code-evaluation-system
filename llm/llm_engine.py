import requests
import time
import threading

from config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    GGUF_MODEL_PATH,
    N_CTX,
    N_THREADS,
    N_GPU_LAYERS,
)

TIMEOUT = 120
MAX_RETRIES = 2

_FALLBACK_JSON = (
    '{"score": 50, "feedback": "LLM evaluation failed. Please try again.", '
    '"improvements": "", "concepts": {'
    '"logic": "Unknown", "edge_cases": "Unknown", "completeness": "Unknown", '
    '"efficiency": "Unknown", "readability": "Unknown"}, '
    '"rubric": {"correctness": 0, "efficiency": 0, "readability": 0, "structure": 0}}'
)

_llm_instance = None
_llm_init_lock = threading.Lock()
_llm_inference_lock = threading.Lock()



def _get_llm_instance():
    """
    Load the GGUF model once using a singleton pattern.
    """
    global _llm_instance

    if _llm_instance is None:
        with _llm_init_lock:
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
                        verbose=False,
                    )
                    print("[LLM] GGUF model loaded successfully")
                except Exception as exc:
                    raise RuntimeError(f"[LLM] Failed to load GGUF model: {exc}")

    return _llm_instance



def _call_llama_cpp(prompt):
    """
    Fast local inference using llama-cpp-python.
    """
    try:
        llm = _get_llm_instance()
        print("[LLM] Running GGUF inference...")

        with _llm_inference_lock:
            output = llm(
                prompt,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                top_k=1,
                top_p=1.0,
                repeat_penalty=1.0,
                stop=["\n"],
                echo=False,
            )

        text = output["choices"][0]["text"].strip()
        print("[LLM] GGUF inference complete")
        return text if text else _FALLBACK_JSON

    except Exception as exc:
        print(f"[LLM] GGUF ERROR: {exc}")
        return _FALLBACK_JSON



def _call_ollama(prompt):
    """
    External Ollama API fallback.
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
                        "num_predict": LLM_MAX_TOKENS,
                    },
                },
                timeout=TIMEOUT,
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            data = response.json()
            if "response" not in data:
                raise Exception("Invalid response format")

            print("[LLM] Ollama response received")
            return data["response"]

        except Exception as exc:
            print(f"[LLM] Ollama ERROR: {exc}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
            else:
                print("[LLM] Final failure, using fallback response")
                return _FALLBACK_JSON



def call_llm(prompt):
    """
    Route the prompt to the configured LLM provider.
    """
    if LLM_PROVIDER == "llama_cpp":
        return _call_llama_cpp(prompt)
    return _call_ollama(prompt)

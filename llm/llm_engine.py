try:
    import requests
except ImportError:  # pragma: no cover - optional dependency fallback
    requests = None
import time
import threading
from collections import OrderedDict

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
    '{"score": 50, "feedback": "The solution was evaluated with a safe fallback because the primary review could not be completed reliably.", '
    '"improvements": "Retry the evaluation or rely on rule-based checks for common question types.", "concepts": {'
    '"logic": "Unknown", "edge_cases": "Unknown", "completeness": "Unknown", '
    '"efficiency": "Unknown", "readability": "Unknown"}, '
    '"rubric": {"correctness": 0, "efficiency": 0, "readability": 0, "structure": 0}}'
)

_llm_instance = None
_llm_unavailable_reason = None
_llm_init_lock = threading.Lock()
_llm_inference_lock = threading.Lock()
_PROMPT_CACHE_LOCK = threading.Lock()
_PROMPT_CACHE = OrderedDict()
_PROMPT_CACHE_MAXSIZE = 256
_INFLIGHT_REQUESTS = {}


def is_llm_available():
    if LLM_PROVIDER == "llama_cpp":
        try:
            from llama_cpp import Llama  # noqa: F401
            return True
        except Exception:
            return False
    if LLM_PROVIDER == "ollama":
        return requests is not None
    return False

def _get_llm_instance():
    """
    Load the GGUF model once using a singleton pattern.
    """
    global _llm_instance, _llm_unavailable_reason

    if _llm_unavailable_reason:
        raise RuntimeError(_llm_unavailable_reason)

    if _llm_instance is None:
        with _llm_init_lock:
            if _llm_unavailable_reason:
                raise RuntimeError(_llm_unavailable_reason)
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
                    _llm_unavailable_reason = f"[LLM] Failed to load GGUF model: {exc}"
                    raise RuntimeError(_llm_unavailable_reason)

    return _llm_instance



def _call_llama_cpp(prompt):
    """
    Fast local inference using llama-cpp-python.
    """
    if _llm_unavailable_reason:
        return _FALLBACK_JSON

    try:
        llm = _get_llm_instance()
        print("[LLM] Running GGUF inference...")

        for attempt in range(MAX_RETRIES):
            with _llm_inference_lock:
                output = llm(
                    prompt,
                    max_tokens=LLM_MAX_TOKENS,
                    temperature=LLM_TEMPERATURE,
                    top_k=1,
                    top_p=1.0,
                    repeat_penalty=1.0,
                    stop=["<|end|>", "</s>"],
                    echo=False,
                )

            text = output["choices"][0]["text"].strip()
            if text:
                print("[LLM] GGUF inference complete")
                return text
            print(f"[LLM] Empty GGUF response (attempt {attempt + 1}), retrying...")

        print("[LLM] GGUF inference complete with empty response, using fallback")
        return _FALLBACK_JSON

    except Exception as exc:
        print(f"[LLM] GGUF ERROR: {exc}")
        return _FALLBACK_JSON



def _call_ollama(prompt):
    """
    External Ollama API fallback.
    """
    if requests is None:
        return _FALLBACK_JSON

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
    prompt = (prompt or "").strip()
    if not prompt:
        return _FALLBACK_JSON

    if LLM_PROVIDER == "llama_cpp" and not is_llm_available():
        return _FALLBACK_JSON

    with _PROMPT_CACHE_LOCK:
        if prompt in _PROMPT_CACHE:
            cached = _PROMPT_CACHE.pop(prompt)
            _PROMPT_CACHE[prompt] = cached
            return cached

        inflight = _INFLIGHT_REQUESTS.get(prompt)
        if inflight is None:
            inflight = {"event": threading.Event(), "response": _FALLBACK_JSON}
            _INFLIGHT_REQUESTS[prompt] = inflight
            owner = True
        else:
            owner = False

    if not owner:
        inflight["event"].wait(timeout=TIMEOUT)
        return inflight.get("response", _FALLBACK_JSON)

    try:
        if LLM_PROVIDER == "llama_cpp":
            response = _call_llama_cpp(prompt)
        else:
            response = _call_ollama(prompt)
    finally:
        with _PROMPT_CACHE_LOCK:
            holder = _INFLIGHT_REQUESTS.pop(prompt, inflight)
            holder["response"] = locals().get("response", _FALLBACK_JSON)
            holder["event"].set()

    with _PROMPT_CACHE_LOCK:
        _PROMPT_CACHE[prompt] = response
        while len(_PROMPT_CACHE) > _PROMPT_CACHE_MAXSIZE:
            _PROMPT_CACHE.popitem(last=False)

    return response

import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import GGUF_MODEL_PATH, LLM_MAX_TOKENS, N_CTX, N_GPU_LAYERS, N_THREADS


def main():
    model_path = Path(GGUF_MODEL_PATH)
    if not model_path.is_absolute():
        model_path = ROOT / model_path

    print(f"[GGUF] Model path: {model_path}")
    print(f"[GGUF] Exists: {model_path.exists()}")

    if not model_path.exists():
        print("[GGUF] ERROR: Model file not found.")
        raise SystemExit(1)

    try:
        from llama_cpp import Llama
    except Exception as exc:
        print(f"[GGUF] ERROR: Could not import llama_cpp: {exc}")
        print("[GGUF] Install/build llama-cpp-python first.")
        raise SystemExit(1)

    print("[GGUF] Loading model with conservative settings...")
    print(f"[GGUF] n_ctx={N_CTX}, n_threads={N_THREADS}, n_gpu_layers={N_GPU_LAYERS}")

    started = time.time()
    try:
        llm = Llama(
            model_path=str(model_path),
            n_ctx=N_CTX,
            n_threads=N_THREADS,
            n_batch=128,
            n_gpu_layers=N_GPU_LAYERS,
            verbose=False,
        )
    except Exception as exc:
        print(f"[GGUF] ERROR: Model load failed: {exc}")
        raise SystemExit(1)

    load_seconds = time.time() - started
    print(f"[GGUF] Model loaded in {load_seconds:.2f}s")

    prompt = "Say OK. Respond with only OK.\nOK:"
    print(f"[GGUF] Prompt: {prompt}")

    infer_started = time.time()
    try:
        result = llm(
            prompt,
            max_tokens=min(LLM_MAX_TOKENS, 32),
            temperature=0.2,
            top_k=40,
            top_p=0.95,
            repeat_penalty=1.0,
            stop=[],
            echo=False,
        )
    except Exception as exc:
        print(f"[GGUF] ERROR: Inference failed: {exc}")
        raise SystemExit(1)

    infer_seconds = time.time() - infer_started
    text = ""
    try:
        text = (result.get("choices") or [{}])[0].get("text", "").strip()
    except Exception:
        text = str(result).strip()

    print(f"[GGUF] Inference completed in {infer_seconds:.2f}s")
    if not text:
        print("[GGUF] Output was empty; showing raw response for debugging.")
        print(f"[GGUF] Raw response: {result}")
    else:
        print(f"[GGUF] Output: {text}")
    print("[GGUF] Smoke test passed.")


if __name__ == "__main__":
    main()

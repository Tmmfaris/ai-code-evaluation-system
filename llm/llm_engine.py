import requests
import time

from config import OLLAMA_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS

# =========================
# CONFIGURATION
# =========================
TIMEOUT = 300       # seconds
MAX_RETRIES = 3

# Fallback raw JSON string returned on LLM failure
# (response_parser.parse_llm_response expects a raw string)
_FALLBACK_JSON = (
    '{"score": 50, "feedback": "LLM evaluation failed. Please try again.", '
    '"strengths": "", "improvements": "", "concepts": {'
    '"logic": "Unknown", "edge_cases": "Unknown", "completeness": "Unknown", '
    '"efficiency": "Unknown", "readability": "Unknown"}}'
)


# =========================
# CALL LLM (MAIN FUNCTION)
# =========================
def call_llm(prompt):
    """
    Sends prompt to Ollama LLM with retry + timeout handling.
    Returns the raw text string from LLM for downstream parsing by response_parser.
    """

    for attempt in range(MAX_RETRIES):
        try:
            print(f"[LLM] Sending request (attempt {attempt + 1})...")

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
                raise Exception("Invalid LLM response format")

            raw_text = data["response"]
            print("[LLM] Response received")
            return raw_text

        except Exception as e:
            print(f"[LLM] Error: {e}")

            if attempt < MAX_RETRIES - 1:
                print("[LLM] Retrying...")
                time.sleep(3)
            else:
                print("[LLM] Final failure — returning fallback response")
                return _FALLBACK_JSON
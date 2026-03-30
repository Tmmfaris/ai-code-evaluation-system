from concurrent.futures import ThreadPoolExecutor, as_completed
from evaluator.main_evaluator import evaluate_submission
import time


# ==============================
# ⚙️ CONFIGURATION
# ==============================
MAX_WORKERS = 3          # Safe limit for GGUF (CPU-based)
TASK_TIMEOUT = 60        # Max time per student (seconds)


# ==============================
# 🚀 BATCH EVALUATION FUNCTION
# ==============================
def evaluate_batch(submissions):
    """
    Evaluate multiple student submissions using controlled parallel execution.

    Args:
        submissions (list): List of student submission dictionaries

    Returns:
        list: List of evaluation results
    """

    results = []
    start_time = time.time()

    # Thread pool for controlled parallel execution
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        # Submit all tasks
        futures = {
            executor.submit(evaluate_submission, **sub): sub
            for sub in submissions
        }

        # Process results as they complete
        for future in as_completed(futures):

            submission = futures[future]

            try:
                # Get result with timeout protection
                result = future.result(timeout=TASK_TIMEOUT)

                results.append(result)

            except Exception as e:
                # Handle failure safely
                results.append({
                    "status": "error",
                    "student_id": submission.get("student_id", "unknown"),
                    "score": 0,
                    "feedback": f"Evaluation failed: {str(e)}",
                    "suggestions": "",
                    "concepts": {},
                    "rubric": {
                        "correctness": 0,
                        "efficiency": 0,
                        "readability": 0,
                        "structure": 0
                    }
                })

    total_time = round(time.time() - start_time, 2)

    print(f"[BATCH] Completed {len(submissions)} evaluations in {total_time}s")

    return results
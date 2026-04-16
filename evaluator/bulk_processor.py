import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from schemas import StudentEvaluationRequest, MultiStudentEvaluationResponse, MultiStudentEvaluationResponse
from utils.logger import log_info, log_error
from config import ALWAYS_LLM_REVIEW, LLM_REVIEW_HARD_MAX_ATTEMPTS

def process_bulk_evaluations(multi_req, evaluate_submission_func) -> dict:
    start_time = time.time()
    results = []
    
    # Flatten submissions for parallel processing
    tasks = []
    for student_req in multi_req.students:
        for sub in student_req.submissions:
            llm_review = student_req.llm_review if student_req.llm_review is not None else multi_req.llm_review
            if llm_review is None:
                llm_review = ALWAYS_LLM_REVIEW
            llm_review_max_attempts = (
                student_req.llm_review_max_attempts
                if student_req.llm_review_max_attempts is not None
                else multi_req.llm_review_max_attempts
            )
            if llm_review_max_attempts is None:
                llm_review_max_attempts = LLM_REVIEW_HARD_MAX_ATTEMPTS

            tasks.append({
                "student_id": student_req.student_id,
                "submission": sub,
                "llm_review": llm_review,
                "llm_review_max_attempts": llm_review_max_attempts,
            })

    evaluation_map = {} # (student_id, signature) -> result

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {
            executor.submit(
                evaluate_submission_func,
                task["student_id"],
                task["submission"],
                llm_review=task["llm_review"],
                llm_review_max_attempts=task["llm_review_max_attempts"]
            ): task for task in tasks
        }
        
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
                key = (
                    task["student_id"],
                    task["submission"].question_id,
                    task["submission"].question,
                    task["submission"].model_answer,
                    task["submission"].student_answer,
                    task["submission"].language,
                )
                evaluation_map[key] = result
            except Exception as e:
                log_error(f"Bulk evaluation failed for student {task['student_id']}: {str(e)}")
                key = (
                    task["student_id"],
                    task["submission"].question_id,
                    task["submission"].question,
                    task["submission"].model_answer,
                    task["submission"].student_answer,
                    task["submission"].language,
                )
                evaluation_map[key] = {"error": str(e)}

    # Reconstruct the response structure
    student_responses = []
    for student_req in multi_req.students:
        s_results = []
        s_total_score = 0
        for sub in student_req.submissions:
            res = evaluation_map.get((
                student_req.student_id,
                sub.question_id,
                sub.question,
                sub.model_answer,
                sub.student_answer,
                sub.language,
            ))
            if res and "error" not in res:
                # _evaluate_single_submission returns a wrapper dict where the actual
                # EvaluationResponse obj is in the 'data' key.
                eval_data = res.get("data")
                s_results.append({
                    "question_id": sub.question_id, # Echo back if provided
                    "data": eval_data
                })
                # if eval_data is an EvaluationResponse object, it uses .score; if dict, uses .get("score")
                score = getattr(eval_data, "score", None)
                if score is None and isinstance(eval_data, dict):
                    score = eval_data.get("score", 0)
                s_total_score += (score or 0)
            else:
                s_results.append({
                    "question_id": sub.question_id,
                    "error": res.get("error") if res else "Unknown error"
                })
        
        student_responses.append({
            "student_id": student_req.student_id,
            "question_count": len(student_req.submissions),
            "total_score": s_total_score,
            "questions": s_results
        })

    return {
        "execution_time": round(time.time() - start_time, 2),
        "students": student_responses
    }

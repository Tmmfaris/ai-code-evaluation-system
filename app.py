from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from schemas import (
    StudentEvaluationRequest,
    MultiStudentEvaluationRequest,
    StudentEvaluationResponse,
    MultiStudentEvaluationResponse,
    StudentQuestionResultItem,
    EvaluationResponse,
    ConceptEvaluation,
)

from evaluator.main_evaluator import evaluate_submission
from utils.logger import log_error


def build_evaluation_data(result):
    feedback = (result.get("feedback", "") or "").strip()
    suggestion = (result.get("suggestions") or result.get("improvements") or "").strip()

    if suggestion and suggestion.lower() != "none needed for this solution.":
        feedback = f"{feedback} {suggestion}".strip()

    return EvaluationResponse(
        score=result.get("score", 0),
        concepts=ConceptEvaluation(**result.get("concepts", {
            "logic": "Unknown",
            "edge_cases": "Unknown",
            "completeness": "Unknown",
            "efficiency": "Unknown",
            "readability": "Unknown",
        })),
        feedback=feedback,
    )


def build_zero_score_data(feedback):
    return EvaluationResponse(
        score=0,
        concepts=ConceptEvaluation(
            logic="Weak",
            edge_cases="Needs Improvement",
            completeness="Low",
            efficiency="Poor",
            readability="Needs Improvement",
        ),
        feedback=feedback,
    )


def build_student_evaluation_response(req: StudentEvaluationRequest):
    if not req.submissions:
        raise HTTPException(status_code=400, detail="No question submissions provided")

    if len(req.submissions) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 questions per student request")

    results = []
    total_score = 0

    for submission in req.submissions:
        if not submission.question.strip():
            results.append(StudentQuestionResultItem(question_id=submission.question_id, error="Question is empty"))
            continue

        if not submission.model_answer.strip():
            results.append(StudentQuestionResultItem(question_id=submission.question_id, error="Sample answer is empty"))
            continue

        if not submission.student_answer.strip():
            evaluation_data = build_zero_score_data("No answer provided.")
            results.append(StudentQuestionResultItem(question_id=submission.question_id, data=evaluation_data))
            continue

        result = evaluate_submission(
            student_id=req.student_id,
            question=submission.question,
            sample_answer=submission.model_answer,
            student_answer=submission.student_answer,
            language=submission.language,
        )

        if result.get("status") == "error":
            results.append(
                StudentQuestionResultItem(
                    question_id=submission.question_id,
                    error=result.get("feedback", "Evaluation failed"),
                )
            )
            continue

        evaluation_data = build_evaluation_data(result)
        results.append(StudentQuestionResultItem(question_id=submission.question_id, data=evaluation_data))
        total_score += evaluation_data.score

    return StudentEvaluationResponse(
        student_id=req.student_id,
        question_count=len(req.submissions),
        total_score=total_score,
        questions=results,
    )


def build_multi_student_evaluation_response(req: MultiStudentEvaluationRequest):
    if not req.students:
        raise HTTPException(status_code=400, detail="No students provided")

    if len(req.students) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 students per request")

    start_time = time.time()
    results = [None] * len(req.students)

    def _evaluate_one_student(index, student_req):
        try:
            return index, build_student_evaluation_response(student_req)
        except HTTPException as exc:
            return index, StudentEvaluationResponse(
                student_id=student_req.student_id,
                questions=[StudentQuestionResultItem(question_id=None, error=exc.detail)],
            )
        except Exception as exc:
            log_error(f"Multi-student evaluation error | Student: {student_req.student_id} | {str(exc)}")
            return index, StudentEvaluationResponse(
                student_id=student_req.student_id,
                questions=[StudentQuestionResultItem(question_id=None, error="Internal evaluation error")],
            )

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_evaluate_one_student, i, student_req): i
            for i, student_req in enumerate(req.students)
        }

        for future in as_completed(futures):
            index, item = future.result()
            results[index] = item

    execution_time = round(time.time() - start_time, 3)

    return MultiStudentEvaluationResponse(
        execution_time=execution_time,
        students=results,
    )


app = FastAPI(
    title="AI Intelligent Evaluation Model",
    description="LLM-based multi-language code evaluation system",
    version="1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"status": "running", "message": "AI Evaluation API is working"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/evaluate/students", response_model=MultiStudentEvaluationResponse, response_model_exclude_none=True)
def evaluate_students(req: MultiStudentEvaluationRequest):
    return build_multi_student_evaluation_response(req)

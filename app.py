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
    QuestionProfileRequest,
    QuestionProfileResponse,
    EvaluationHistoryItem,
)

from evaluator.main_evaluator import evaluate_submission
from evaluator.question_profile_store import (
    get_question_profile,
    list_question_profiles,
    upsert_question_profile,
)
from evaluator.evaluation_history_store import (
    list_recent_evaluation_records,
    list_student_evaluation_records,
    save_evaluation_record,
)
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


def persist_evaluation_event(
    student_id,
    question_id,
    question,
    model_answer,
    student_answer,
    language,
    data=None,
    error=None,
):
    payload = {
        "student_id": student_id,
        "question_id": question_id,
        "question": question,
        "model_answer": model_answer,
        "student_answer": student_answer,
        "language": language,
        "score": 0,
        "concepts": {},
        "feedback": "",
        "status": "error" if error else "success",
        "error": error,
    }

    if data is not None:
        payload["score"] = data.score
        payload["concepts"] = data.concepts.model_dump()
        payload["feedback"] = data.feedback

    save_evaluation_record(payload)


def build_student_evaluation_response(req: StudentEvaluationRequest):
    if not req.submissions:
        raise HTTPException(status_code=400, detail="No question submissions provided")

    if len(req.submissions) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 questions per student request")

    results = []
    total_score = 0

    for submission in req.submissions:
        profile = get_question_profile(submission.question_id) if submission.question_id else None
        question = (submission.question or (profile or {}).get("question") or "").strip()
        model_answer = (submission.model_answer or (profile or {}).get("model_answer") or "").strip()
        language = ((submission.language or (profile or {}).get("language") or "")).strip().lower()

        if not question:
            persist_evaluation_event(
                student_id=req.student_id,
                question_id=submission.question_id,
                question="",
                model_answer=model_answer,
                student_answer=submission.student_answer,
                language=language,
                error="Question is empty",
            )
            results.append(StudentQuestionResultItem(question_id=submission.question_id, error="Question is empty"))
            continue

        if not model_answer:
            persist_evaluation_event(
                student_id=req.student_id,
                question_id=submission.question_id,
                question=question,
                model_answer="",
                student_answer=submission.student_answer,
                language=language,
                error="Sample answer is empty",
            )
            results.append(StudentQuestionResultItem(question_id=submission.question_id, error="Sample answer is empty"))
            continue

        if not language:
            persist_evaluation_event(
                student_id=req.student_id,
                question_id=submission.question_id,
                question=question,
                model_answer=model_answer,
                student_answer=submission.student_answer,
                language="",
                error="Language is empty",
            )
            results.append(StudentQuestionResultItem(question_id=submission.question_id, error="Language is empty"))
            continue

        if not submission.student_answer.strip():
            evaluation_data = build_zero_score_data("No answer provided.")
            persist_evaluation_event(
                student_id=req.student_id,
                question_id=submission.question_id,
                question=question,
                model_answer=model_answer,
                student_answer=submission.student_answer,
                language=language,
                data=evaluation_data,
            )
            results.append(StudentQuestionResultItem(question_id=submission.question_id, data=evaluation_data))
            continue

        result = evaluate_submission(
            student_id=req.student_id,
            question=question,
            sample_answer=model_answer,
            student_answer=submission.student_answer,
            language=language,
        )

        if result.get("status") == "error":
            persist_evaluation_event(
                student_id=req.student_id,
                question_id=submission.question_id,
                question=question,
                model_answer=model_answer,
                student_answer=submission.student_answer,
                language=language,
                error=result.get("feedback", "Evaluation failed"),
            )
            results.append(
                StudentQuestionResultItem(
                    question_id=submission.question_id,
                    error=result.get("feedback", "Evaluation failed"),
                )
            )
            continue

        evaluation_data = build_evaluation_data(result)
        persist_evaluation_event(
            student_id=req.student_id,
            question_id=submission.question_id,
            question=question,
            model_answer=model_answer,
            student_answer=submission.student_answer,
            language=language,
            data=evaluation_data,
        )
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


@app.post("/questions/register", response_model=QuestionProfileResponse, response_model_exclude_none=True)
def register_question_profile(req: QuestionProfileRequest):
    return QuestionProfileResponse(**upsert_question_profile(req.model_dump()))


@app.get("/questions/{question_id}", response_model=QuestionProfileResponse, response_model_exclude_none=True)
def fetch_question_profile(question_id: str):
    profile = get_question_profile(question_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Question profile not found")
    return QuestionProfileResponse(**profile)


@app.get("/questions", response_model=list[QuestionProfileResponse], response_model_exclude_none=True)
def fetch_question_profiles():
    return [QuestionProfileResponse(**profile) for profile in list_question_profiles()]


@app.get("/evaluations", response_model=list[EvaluationHistoryItem], response_model_exclude_none=True)
def fetch_recent_evaluations(limit: int = 100):
    return [EvaluationHistoryItem(**item) for item in list_recent_evaluation_records(limit=limit)]


@app.get("/evaluations/students/{student_id}", response_model=list[EvaluationHistoryItem], response_model_exclude_none=True)
def fetch_student_evaluations(student_id: str, limit: int = 100):
    return [EvaluationHistoryItem(**item) for item in list_student_evaluation_records(student_id=student_id, limit=limit)]

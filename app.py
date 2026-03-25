from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import time

from schemas import (
    CodeRequest,
    APIResponse,
    EvaluationResponse,
    RubricScore,
    ConceptEvaluation
)

from evaluator.main_evaluator import evaluate_submission
from utils.logger import log_info, log_error


# =========================
# 🚀 CREATE FASTAPI APP
# =========================
app = FastAPI(
    title="AI Intelligent Evaluation Model",
    description="LLM-based multi-language code evaluation system",
    version="1.0"
)


# =========================
# 🌐 ENABLE CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Change in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# 🏠 ROOT ENDPOINT
# =========================
@app.get("/")
def home():
    return {
        "status": "running",
        "message": "AI Evaluation API is working"
    }


# =========================
# ❤️ HEALTH CHECK
# =========================
@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


# =========================
# 🧠 MAIN EVALUATION ENDPOINT
# =========================
@app.post("/evaluate", response_model=APIResponse)
def evaluate(req: CodeRequest):

    start_time = time.time()

    try:
        log_info(f"API Request received | Student ID: {req.student_id}")

        # =========================
        # ✅ INPUT VALIDATION
        # =========================
        if not req.question or not req.question.strip():
            raise HTTPException(status_code=400, detail="Question is empty")

        if not req.model_answer or not req.model_answer.strip():
            raise HTTPException(status_code=400, detail="Sample answer is empty")

        if not req.student_answer or not req.student_answer.strip():
            raise HTTPException(status_code=400, detail="Student answer is empty")

        # =========================
        # 🧠 CALL AI EVALUATOR
        # =========================
        result = evaluate_submission(
            student_id=req.student_id,
            question=req.question,
            sample_answer=req.model_answer,
            student_answer=req.student_answer,
            language=req.language
        )

        # =========================
        # 🚨 HANDLE MODEL ERROR
        # =========================
        if result.get("status") == "error":
            log_error(f"Evaluation failed | Student: {req.student_id}")

            raise HTTPException(
                status_code=500,
                detail=result.get("feedback", "Evaluation failed")
            )

        # =========================
        # 🔄 MAP TO RESPONSE SCHEMA
        # =========================
        evaluation_data = EvaluationResponse(
            score=result.get("score", 0),
            rubric=RubricScore(**result.get("rubric", {})),
            concepts=ConceptEvaluation(**result.get("concepts", {})),
            feedback=result.get("feedback", ""),
            suggestions=result.get("suggestions") or result.get("improvements", "")
        )

        end_time = time.time()

        log_info(f"API Success | Student ID: {req.student_id} | Score: {evaluation_data.score}")

        return APIResponse(
            status="success",
            execution_time=round(end_time - start_time, 3),
            data=evaluation_data
        )

    # =========================
    # 🚨 HANDLE KNOWN ERRORS
    # =========================
    except HTTPException as http_err:
        raise http_err

    # =========================
    # 🚨 HANDLE UNKNOWN ERRORS
    # =========================
    except Exception as e:
        log_error(f"API Error | Student: {req.student_id} | Error: {str(e)}")

        raise HTTPException(
            status_code=500,
            detail="Internal Server Error"
        )
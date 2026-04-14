import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional


class EvaluationHistoryRepository(ABC):
    @abstractmethod
    def save(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_recent(self, limit: int = 100) -> List[dict]:
        raise NotImplementedError

    @abstractmethod
    def list_for_student(self, student_id: str, limit: int = 100) -> List[dict]:
        raise NotImplementedError

    @abstractmethod
    def list_by_status(self, status: str, limit: int = 100) -> List[dict]:
        raise NotImplementedError


class SqliteEvaluationHistoryRepository(EvaluationHistoryRepository):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_parent_dir(self):
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _initialize(self) -> None:
        self._ensure_parent_dir()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS evaluation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id TEXT NOT NULL,
                        question_id TEXT,
                        question TEXT NOT NULL,
                        model_answer TEXT NOT NULL,
                        student_answer TEXT NOT NULL,
                        language TEXT NOT NULL,
                        score INTEGER NOT NULL,
                        concepts_json TEXT NOT NULL,
                        feedback TEXT NOT NULL,
                        status TEXT NOT NULL,
                        error TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                self._ensure_column(conn, "evaluation_history", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_evaluation_history_student ON evaluation_history(student_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_evaluation_history_question ON evaluation_history(question_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_evaluation_history_created_at ON evaluation_history(created_at)"
                )
                conn.commit()

    def _ensure_column(self, conn, table_name: str, column_name: str, column_definition: str) -> None:
        columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

    def _build_record(self, payload: dict) -> dict:
        return {
            "student_id": (payload.get("student_id") or "").strip(),
            "question_id": (payload.get("question_id") or "").strip() or None,
            "question": (payload.get("question") or "").strip(),
            "model_answer": (payload.get("model_answer") or "").strip(),
            "student_answer": (payload.get("student_answer") or "").strip(),
            "language": ((payload.get("language") or "").strip().lower()),
            "score": int(payload.get("score", 0) or 0),
            "concepts": payload.get("concepts") or {},
            "feedback": (payload.get("feedback") or "").strip(),
            "status": (payload.get("status") or "success").strip(),
            "error": (payload.get("error") or "").strip() or None,
            "metadata": payload.get("metadata") or {},
            "created_at": payload.get("created_at") or datetime.now(timezone.utc).isoformat(),
        }

    def _row_to_record(self, row) -> dict:
        return {
            "id": row[0],
            "student_id": row[1],
            "question_id": row[2],
            "question": row[3],
            "model_answer": row[4],
            "student_answer": row[5],
            "language": row[6],
            "score": row[7],
            "concepts": json.loads(row[8]) if row[8] else {},
            "feedback": row[9],
            "status": row[10],
            "error": row[11],
            "metadata": json.loads(row[12]) if row[12] else {},
            "created_at": row[13],
        }

    def save(self, payload: dict) -> dict:
        record = self._build_record(payload)
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO evaluation_history (
                        student_id, question_id, question, model_answer, student_answer,
                        language, score, concepts_json, feedback, status, error, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["student_id"],
                        record["question_id"],
                        record["question"],
                        record["model_answer"],
                        record["student_answer"],
                        record["language"],
                        record["score"],
                        json.dumps(record["concepts"], ensure_ascii=True),
                        record["feedback"],
                        record["status"],
                        record["error"],
                        json.dumps(record["metadata"], ensure_ascii=True),
                        record["created_at"],
                    ),
                )
                conn.commit()
                record["id"] = cursor.lastrowid
        return record

    def list_recent(self, limit: int = 100) -> List[dict]:
        limit = max(1, min(int(limit or 100), 500))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, student_id, question_id, question, model_answer, student_answer,
                           language, score, concepts_json, feedback, status, error, metadata_json, created_at
                    FROM evaluation_history
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_for_student(self, student_id: str, limit: int = 100) -> List[dict]:
        limit = max(1, min(int(limit or 100), 500))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, student_id, question_id, question, model_answer, student_answer,
                           language, score, concepts_json, feedback, status, error, metadata_json, created_at
                    FROM evaluation_history
                    WHERE student_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (student_id, limit),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_by_status(self, status: str, limit: int = 100) -> List[dict]:
        limit = max(1, min(int(limit or 100), 500))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, student_id, question_id, question, model_answer, student_answer,
                           language, score, concepts_json, feedback, status, error, metadata_json, created_at
                    FROM evaluation_history
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    ((status or "").strip(), limit),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

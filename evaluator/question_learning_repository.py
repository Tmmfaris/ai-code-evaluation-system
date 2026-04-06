import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List


class QuestionLearningRepository(ABC):
    @abstractmethod
    def save(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_recent(self, limit: int = 100) -> List[dict]:
        raise NotImplementedError


class SqliteQuestionLearningRepository(QuestionLearningRepository):
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
                    CREATE TABLE IF NOT EXISTS question_learning (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_id TEXT,
                        language TEXT NOT NULL,
                        package_status TEXT,
                        package_confidence REAL NOT NULL DEFAULT 0.0,
                        used_fallback INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL,
                        score INTEGER NOT NULL DEFAULT 0,
                        student_answer_text TEXT NOT NULL DEFAULT '',
                        normalized_student_answer TEXT NOT NULL,
                        feedback TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_question_learning_question ON question_learning(question_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_question_learning_language ON question_learning(language)"
                )
                self._ensure_column(conn, "question_learning", "student_answer_text", "TEXT NOT NULL DEFAULT ''")
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
            "question_id": (payload.get("question_id") or "").strip() or None,
            "language": ((payload.get("language") or "").strip().lower()),
            "package_status": (payload.get("package_status") or "").strip() or None,
            "package_confidence": float(payload.get("package_confidence", 0.0) or 0.0),
            "used_fallback": int(bool(payload.get("used_fallback", False))),
            "status": (payload.get("status") or "observed").strip(),
            "score": int(payload.get("score", 0) or 0),
            "student_answer_text": (payload.get("student_answer_text") or "").strip(),
            "normalized_student_answer": (payload.get("normalized_student_answer") or "").strip(),
            "feedback": (payload.get("feedback") or "").strip(),
            "metadata": payload.get("metadata") or {},
            "created_at": payload.get("created_at") or datetime.now(timezone.utc).isoformat(),
        }

    def _row_to_record(self, row) -> dict:
        return {
            "id": row[0],
            "question_id": row[1],
            "language": row[2],
            "package_status": row[3],
            "package_confidence": row[4],
            "used_fallback": bool(row[5]),
            "status": row[6],
            "score": row[7],
            "student_answer_text": row[8],
            "normalized_student_answer": row[9],
            "feedback": row[10],
            "metadata": json.loads(row[11]) if row[11] else {},
            "created_at": row[12],
        }

    def save(self, payload: dict) -> dict:
        record = self._build_record(payload)
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO question_learning (
                        question_id, language, package_status, package_confidence,
                        used_fallback, status, score, student_answer_text, normalized_student_answer,
                        feedback, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["question_id"],
                        record["language"],
                        record["package_status"],
                        record["package_confidence"],
                        record["used_fallback"],
                        record["status"],
                        record["score"],
                        record["student_answer_text"],
                        record["normalized_student_answer"],
                        record["feedback"],
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
                    SELECT id, question_id, language, package_status, package_confidence,
                           used_fallback, status, score, student_answer_text, normalized_student_answer,
                           feedback, metadata_json, created_at
                    FROM question_learning
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

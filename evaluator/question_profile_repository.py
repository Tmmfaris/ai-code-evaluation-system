import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from evaluator.question_classifier import classify_question


class QuestionProfileRepository(ABC):
    @abstractmethod
    def upsert(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get(self, question_id: str) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> List[dict]:
        raise NotImplementedError


class JsonQuestionProfileRepository(QuestionProfileRepository):
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def _ensure_store(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump({}, handle, indent=2)

    def _load_profiles(self) -> Dict[str, dict]:
        self._ensure_store()
        with open(self.path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}

    def _save_profiles(self, profiles: Dict[str, dict]) -> None:
        self._ensure_store()
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(profiles, handle, indent=2)

    def _build_profile(self, payload: dict) -> dict:
        question = payload["question"].strip()
        model_answer = payload["model_answer"].strip()
        language = payload["language"].strip().lower()
        question_id = payload["question_id"].strip()
        profile = classify_question(question, language)

        return {
            "question_id": question_id,
            "question": question,
            "model_answer": model_answer,
            "language": language,
            "course_id": (payload.get("course_id") or "").strip() or None,
            "faculty_id": (payload.get("faculty_id") or "").strip() or None,
            "topic": (payload.get("topic") or "").strip() or None,
            "profile": profile,
        }

    def upsert(self, payload: dict) -> dict:
        built = self._build_profile(payload)
        with self._lock:
            profiles = self._load_profiles()
            profiles[built["question_id"]] = built
            self._save_profiles(profiles)
        return built

    def get(self, question_id: str) -> Optional[dict]:
        if not question_id:
            return None
        with self._lock:
            profiles = self._load_profiles()
            return profiles.get(question_id)

    def list_all(self) -> List[dict]:
        with self._lock:
            profiles = self._load_profiles()
            return list(profiles.values())


class SqliteQuestionProfileRepository(QuestionProfileRepository):
    def __init__(self, db_path: str, legacy_json_path: Optional[str] = None):
        self.db_path = db_path
        self.legacy_json_path = legacy_json_path
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
                    CREATE TABLE IF NOT EXISTS question_profiles (
                        question_id TEXT PRIMARY KEY,
                        question TEXT NOT NULL,
                        model_answer TEXT NOT NULL,
                        language TEXT NOT NULL,
                        course_id TEXT,
                        faculty_id TEXT,
                        topic TEXT,
                        profile_json TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_question_profiles_language ON question_profiles(language)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_question_profiles_course ON question_profiles(course_id)"
                )
                conn.commit()
            self._migrate_legacy_json_if_needed()

    def _build_profile(self, payload: dict) -> dict:
        question = payload["question"].strip()
        model_answer = payload["model_answer"].strip()
        language = payload["language"].strip().lower()
        question_id = payload["question_id"].strip()
        profile = classify_question(question, language)

        return {
            "question_id": question_id,
            "question": question,
            "model_answer": model_answer,
            "language": language,
            "course_id": (payload.get("course_id") or "").strip() or None,
            "faculty_id": (payload.get("faculty_id") or "").strip() or None,
            "topic": (payload.get("topic") or "").strip() or None,
            "profile": profile,
        }

    def _row_to_profile(self, row) -> dict:
        return {
            "question_id": row[0],
            "question": row[1],
            "model_answer": row[2],
            "language": row[3],
            "course_id": row[4],
            "faculty_id": row[5],
            "topic": row[6],
            "profile": json.loads(row[7]) if row[7] else {},
        }

    def _migrate_legacy_json_if_needed(self) -> None:
        if not self.legacy_json_path or not os.path.exists(self.legacy_json_path):
            return

        try:
            with open(self.legacy_json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(data, dict) or not data:
            return

        with self._connect() as conn:
            existing_count = conn.execute("SELECT COUNT(*) FROM question_profiles").fetchone()[0]
            if existing_count:
                return

            rows = []
            for payload in data.values():
                if not isinstance(payload, dict):
                    continue
                built = self._build_profile(payload)
                rows.append(
                    (
                        built["question_id"],
                        built["question"],
                        built["model_answer"],
                        built["language"],
                        built["course_id"],
                        built["faculty_id"],
                        built["topic"],
                        json.dumps(built["profile"], ensure_ascii=True),
                    )
                )

            if rows:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO question_profiles (
                        question_id, question, model_answer, language,
                        course_id, faculty_id, topic, profile_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()

    def upsert(self, payload: dict) -> dict:
        built = self._build_profile(payload)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO question_profiles (
                        question_id, question, model_answer, language,
                        course_id, faculty_id, topic, profile_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        built["question_id"],
                        built["question"],
                        built["model_answer"],
                        built["language"],
                        built["course_id"],
                        built["faculty_id"],
                        built["topic"],
                        json.dumps(built["profile"], ensure_ascii=True),
                    ),
                )
                conn.commit()
        return built

    def get(self, question_id: str) -> Optional[dict]:
        if not question_id:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT question_id, question, model_answer, language,
                           course_id, faculty_id, topic, profile_json
                    FROM question_profiles
                    WHERE question_id = ?
                    """,
                    (question_id,),
                ).fetchone()
        return self._row_to_profile(row) if row else None

    def list_all(self) -> List[dict]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT question_id, question, model_answer, language,
                           course_id, faculty_id, topic, profile_json
                    FROM question_profiles
                    ORDER BY question_id
                    """
                ).fetchall()
        return [self._row_to_profile(row) for row in rows]

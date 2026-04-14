import json
import os
import sqlite3
import threading
import hashlib
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from evaluator.question_classifier import classify_question


def build_question_signature(question: str, language: str) -> str:
    normalized_question = " ".join((question or "").strip().lower().split())
    normalized_question = "".join(ch for ch in normalized_question if ch.isalnum() or ch.isspace()).strip()
    return f"{(language or '').strip().lower()}::{normalized_question}"


def _build_package_key(question_signature: str) -> str:
    digest = hashlib.sha1((question_signature or "").encode("utf-8")).hexdigest()[:12]
    return f"pkg_{digest}"


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
        question_signature = (payload.get("question_signature") or "").strip() or build_question_signature(question, language)
        # question_id is now purely optional metadata
        question_id = (payload.get("question_id") or "").strip() or None
        
        profile = classify_question(question, language)
        accepted_solutions = [
            answer.strip()
            for answer in (payload.get("accepted_solutions") or payload.get("alternative_answers") or [])
            if isinstance(answer, str) and answer.strip()
        ]
        test_sets = payload.get("test_sets") or {}
        positive_tests = [item for item in (test_sets.get("positive") or payload.get("hidden_tests") or []) if isinstance(item, dict)]
        negative_tests = [item for item in (test_sets.get("negative") or []) if isinstance(item, dict)]
        incorrect_patterns = [item for item in (payload.get("incorrect_patterns") or []) if isinstance(item, dict)]

        return {
            "question_signature": question_signature,
            "question_id": question_id,
            "question": question,
            "model_answer": model_answer,
            "language": language,
            "template_family": (payload.get("template_family") or "").strip() or None,
            "accepted_solutions": accepted_solutions,
            "test_sets": {
                "positive": positive_tests,
                "negative": negative_tests,
            },
            "incorrect_patterns": incorrect_patterns,
            "package_status": (payload.get("package_status") or "").strip() or None,
            "package_summary": (payload.get("package_summary") or "").strip() or None,
            "package_confidence": float(payload.get("package_confidence", 0.0) or 0.0),
            "review_required": bool(payload.get("review_required", False)),
            "approval_status": (payload.get("approval_status") or "").strip() or "pending",
            "approved_by": (payload.get("approved_by") or "").strip() or None,
            "exam_ready": bool(payload.get("exam_ready", False)),
            "positive_test_count": int(payload.get("positive_test_count", len(positive_tests)) or len(positive_tests)),
            "negative_test_count": int(payload.get("negative_test_count", len(negative_tests)) or len(negative_tests)),
            "reused_from_questions": [
                item.strip()
                for item in ((payload.get("reused_from_questions") or payload.get("reused_from_question_ids")) or [])
                if isinstance(item, str) and item.strip()
            ],
            "profile": profile,
        }

    def upsert(self, payload: dict) -> dict:
        built = self._build_profile(payload)
        with self._lock:
            profiles = self._load_profiles()
            # Signature is now the storage key
            profiles[built["question_signature"]] = built
            self._save_profiles(profiles)
        return built

    def get(self, question_signature: str) -> Optional[dict]:
        if not question_signature:
            return None
        with self._lock:
            profiles = self._load_profiles()
            return profiles.get(question_signature)

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
                # 🚀 Migration Logic: Remove question_id as PK if it exists
                columns = {row[1]: row for row in conn.execute("PRAGMA table_info(question_profiles)").fetchall()}
                if columns and "question_id" in columns and columns["question_id"][5] == 1:
                    log_info("Migrating question_profiles: Changing PK from question_id to question_signature")
                    # SQLite doesn't support DROP COLUMN or CHANGE PK well, so we do the 'rename and copy' dance
                    conn.execute("ALTER TABLE question_profiles RENAME TO question_profiles_old")
                    
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS question_profiles (
                        question_signature TEXT PRIMARY KEY,
                        question_id TEXT,
                        question TEXT NOT NULL,
                        model_answer TEXT NOT NULL,
                        language TEXT NOT NULL,
                        template_family TEXT,
                        accepted_solutions_json TEXT NOT NULL DEFAULT '[]',
                        test_sets_json TEXT NOT NULL DEFAULT '{}',
                        incorrect_patterns_json TEXT NOT NULL DEFAULT '[]',
                        package_status TEXT,
                        package_summary TEXT,
                        package_confidence REAL NOT NULL DEFAULT 0.0,
                        review_required INTEGER NOT NULL DEFAULT 0,
                        approval_status TEXT NOT NULL DEFAULT 'pending',
                        approved_by TEXT,
                        exam_ready INTEGER NOT NULL DEFAULT 0,
                        positive_test_count INTEGER NOT NULL DEFAULT 0,
                        negative_test_count INTEGER NOT NULL DEFAULT 0,
                        reused_from_question_ids_json TEXT NOT NULL DEFAULT '[]',
                        profile_json TEXT NOT NULL
                    )
                    """
                )
                
                # If we just renamed the old table, migrate data and drop it
                if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='question_profiles_old'").fetchone():
                    conn.execute(
                        """
                        INSERT INTO question_profiles (
                            question_signature, question_id, question, model_answer, language,
                            template_family, accepted_solutions_json, test_sets_json, incorrect_patterns_json,
                            package_status, package_summary, package_confidence, review_required,
                            approval_status, approved_by, exam_ready,
                            positive_test_count, negative_test_count, reused_from_question_ids_json, profile_json
                        )
                        SELECT 
                            COALESCE(question_signature, language || '::' || LOWER(TRIM(question))), 
                            question_id, question, model_answer, language,
                            template_family, 
                            COALESCE(accepted_solutions_json, '[]'), 
                            COALESCE(test_sets_json, '{}'), 
                            COALESCE(incorrect_patterns_json, '[]'),
                            package_status, package_summary, package_confidence, review_required,
                            approval_status, approved_by, exam_ready,
                            positive_test_count, negative_test_count, 
                            COALESCE(reused_from_question_ids_json, '[]'), 
                            profile_json
                        FROM question_profiles_old
                        """
                    )
                    conn.execute("DROP TABLE question_profiles_old")
                    log_info("Successfully migrated question_profiles to signature-based PK")

                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_question_profiles_language ON question_profiles(language)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_question_profiles_id ON question_profiles(question_id)"
                )
                conn.commit()
                self._ensure_column(conn, "question_profiles", "question_signature", "TEXT")
                self._ensure_column(conn, "question_profiles", "template_family", "TEXT")
                self._ensure_column(conn, "question_profiles", "accepted_solutions_json", "TEXT NOT NULL DEFAULT '[]'")
                self._ensure_column(conn, "question_profiles", "test_sets_json", "TEXT NOT NULL DEFAULT '{}'")
                self._ensure_column(conn, "question_profiles", "incorrect_patterns_json", "TEXT NOT NULL DEFAULT '[]'")
                self._ensure_column(conn, "question_profiles", "package_status", "TEXT")
                self._ensure_column(conn, "question_profiles", "package_summary", "TEXT")
                self._ensure_column(conn, "question_profiles", "package_confidence", "REAL NOT NULL DEFAULT 0.0")
                self._ensure_column(conn, "question_profiles", "review_required", "INTEGER NOT NULL DEFAULT 0")
                self._ensure_column(conn, "question_profiles", "approval_status", "TEXT NOT NULL DEFAULT 'pending'")
                self._ensure_column(conn, "question_profiles", "approved_by", "TEXT")
                self._ensure_column(conn, "question_profiles", "exam_ready", "INTEGER NOT NULL DEFAULT 0")
                self._ensure_column(conn, "question_profiles", "positive_test_count", "INTEGER NOT NULL DEFAULT 0")
                self._ensure_column(conn, "question_profiles", "negative_test_count", "INTEGER NOT NULL DEFAULT 0")
                self._ensure_column(conn, "question_profiles", "reused_from_question_ids_json", "TEXT NOT NULL DEFAULT '[]'")
            self._migrate_legacy_json_if_needed()

    def _ensure_column(self, conn, table_name: str, column_name: str, column_definition: str) -> None:
        columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

    def _build_profile(self, payload: dict) -> dict:
        question = payload["question"].strip()
        model_answer = payload["model_answer"].strip()
        language = payload["language"].strip().lower()
        question_signature = (payload.get("question_signature") or "").strip() or build_question_signature(question, language)
        # question_id is now purely optional metadata
        question_id = (payload.get("question_id") or "").strip() or None
        
        profile = classify_question(question, language)
        accepted_solutions = [
            answer.strip()
            for answer in (payload.get("accepted_solutions") or payload.get("alternative_answers") or [])
            if isinstance(answer, str) and answer.strip()
        ]
        test_sets = payload.get("test_sets") or {}
        positive_tests = [item for item in (test_sets.get("positive") or payload.get("hidden_tests") or []) if isinstance(item, dict)]
        negative_tests = [item for item in (test_sets.get("negative") or []) if isinstance(item, dict)]
        incorrect_patterns = [item for item in (payload.get("incorrect_patterns") or []) if isinstance(item, dict)]

        return {
            "question_signature": question_signature,
            "question_id": question_id,
            "question": question,
            "model_answer": model_answer,
            "language": language,
            "template_family": (payload.get("template_family") or "").strip() or None,
            "accepted_solutions": accepted_solutions,
            "test_sets": {
                "positive": positive_tests,
                "negative": negative_tests,
            },
            "incorrect_patterns": incorrect_patterns,
            "package_status": (payload.get("package_status") or "").strip() or None,
            "package_summary": (payload.get("package_summary") or "").strip() or None,
            "package_confidence": float(payload.get("package_confidence", 0.0) or 0.0),
            "review_required": bool(payload.get("review_required", False)),
            "approval_status": (payload.get("approval_status") or "").strip() or "pending",
            "approved_by": (payload.get("approved_by") or "").strip() or None,
            "exam_ready": bool(payload.get("exam_ready", False)),
            "positive_test_count": int(payload.get("positive_test_count", len(positive_tests)) or len(positive_tests)),
            "negative_test_count": int(payload.get("negative_test_count", len(negative_tests)) or len(negative_tests)),
            "reused_from_questions": [
                item.strip()
                for item in ((payload.get("reused_from_questions") or payload.get("reused_from_question_ids")) or [])
                if isinstance(item, str) and item.strip()
            ],
            "profile": profile,
        }

    def _row_to_profile(self, row) -> dict:
        return {
            "question_signature": row[0],
            "question_id": row[1],
            "question": row[2],
            "model_answer": row[3],
            "language": row[4],
            "template_family": row[5],
            "accepted_solutions": json.loads(row[6]) if row[6] else [],
            "test_sets": json.loads(row[7]) if row[7] else {"positive": [], "negative": []},
            "incorrect_patterns": json.loads(row[8]) if row[8] else [],
            "package_status": row[9],
            "package_summary": row[10],
            "package_confidence": row[11] or 0.0,
            "review_required": bool(row[12]),
            "approval_status": row[13] or "pending",
            "approved_by": row[14],
            "exam_ready": bool(row[15]),
            "positive_test_count": row[16] or 0,
            "negative_test_count": row[17] or 0,
            "reused_from_questions": json.loads(row[18]) if row[18] else [],
            "profile": json.loads(row[19]) if row[19] else {},
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
                        built["question_signature"],
                        built["template_family"],
                        json.dumps(built["accepted_solutions"], ensure_ascii=True),
                        json.dumps(built["test_sets"], ensure_ascii=True),
                        json.dumps(built["incorrect_patterns"], ensure_ascii=True),
                        built["package_status"],
                        built["package_summary"],
                        built["package_confidence"],
                        int(bool(built["review_required"])),
                        built["approval_status"],
                        built["approved_by"],
                        int(bool(built["exam_ready"])),
                        built["positive_test_count"],
                        built["negative_test_count"],
                        json.dumps(built["reused_from_questions"], ensure_ascii=True),
                        json.dumps(built["profile"], ensure_ascii=True),
                    )
                )

            if rows:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO question_profiles (
                        question_id, question, model_answer, language,
                        question_signature, template_family,
                        accepted_solutions_json, test_sets_json, incorrect_patterns_json,
                        package_status, package_summary, package_confidence, review_required,
                        approval_status, approved_by, exam_ready,
                        positive_test_count, negative_test_count, reused_from_question_ids_json, profile_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        question_signature, question_id, question, model_answer, language,
                        template_family,
                        accepted_solutions_json, test_sets_json, incorrect_patterns_json,
                        package_status, package_summary, package_confidence, review_required,
                        approval_status, approved_by, exam_ready,
                        positive_test_count, negative_test_count, reused_from_question_ids_json, profile_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        built["question_signature"],
                        built["question_id"],
                        built["question"],
                        built["model_answer"],
                        built["language"],
                        built["template_family"],
                        json.dumps(built["accepted_solutions"], ensure_ascii=True),
                        json.dumps(built["test_sets"], ensure_ascii=True),
                        json.dumps(built["incorrect_patterns"], ensure_ascii=True),
                        built["package_status"],
                        built["package_summary"],
                        built["package_confidence"],
                        int(bool(built["review_required"])),
                        built["approval_status"],
                        built["approved_by"],
                        int(bool(built["exam_ready"])),
                        built["positive_test_count"],
                        built["negative_test_count"],
                        json.dumps(built["reused_from_questions"], ensure_ascii=True),
                        json.dumps(built["profile"], ensure_ascii=True),
                    ),
                )
                conn.commit()
        return built

    def get(self, question_signature: str) -> Optional[dict]:
        if not question_signature:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT question_signature, question_id, question, model_answer, language,
                           template_family, accepted_solutions_json, test_sets_json, incorrect_patterns_json,
                           package_status, package_summary, package_confidence, review_required,
                           approval_status, approved_by, exam_ready,
                           positive_test_count, negative_test_count, reused_from_question_ids_json, profile_json
                    FROM question_profiles
                    WHERE question_signature = ?
                    """,
                    (question_signature,),
                ).fetchone()
        return self._row_to_profile(row) if row else None

    def list_all(self) -> List[dict]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT question_signature, question_id, question, model_answer, language,
                           template_family, accepted_solutions_json, test_sets_json, incorrect_patterns_json,
                           package_status, package_summary, package_confidence, review_required,
                           approval_status, approved_by, exam_ready,
                           positive_test_count, negative_test_count, reused_from_question_ids_json, profile_json
                    FROM question_profiles
                    ORDER BY question_signature
                    """
                ).fetchall()
        return [self._row_to_profile(row) for row in rows]

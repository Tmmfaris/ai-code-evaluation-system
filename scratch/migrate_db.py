import sqlite3
import os

DB_PATHS = {
    "profiles": "data/question_profiles.db",
    "learning": "data/question_learning.db"
}

def migrate_profiles():
    path = DB_PATHS["profiles"]
    if not os.path.exists(path):
        print(f"Skipping profiles migration: {path} not found.")
        return

    conn = sqlite3.connect(path)
    try:
        # Check current schema
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(question_profiles)").fetchall()}
        
        # If question_id is still the PK (index 0 is name, 5 is PK flag)
        if columns.get("question_id") and columns["question_id"][5] == 1:
            print("Migrating question_profiles to Signature-PK...")
            conn.execute("ALTER TABLE question_profiles RENAME TO qp_old")
            
            conn.execute("""
                CREATE TABLE question_profiles (
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
            """)
            
            conn.execute("""
                INSERT INTO question_profiles (
                    question_signature, question_id, question, model_answer, language,
                    template_family, accepted_solutions_json, test_sets_json, incorrect_patterns_json,
                    package_status, package_summary, package_confidence, review_required,
                    approval_status, approved_by, exam_ready,
                    positive_test_count, negative_test_count, reused_from_question_ids_json, profile_json
                )
                SELECT 
                    COALESCE(question_signature, language || '::' || LOWER(TRIM(question))) as sig, 
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
                FROM qp_old
                GROUP BY sig
                HAVING package_confidence = MAX(package_confidence)
            """)
            conn.execute("DROP TABLE qp_old")
            conn.execute("CREATE INDEX idx_question_profiles_language ON question_profiles(language)")
            conn.execute("CREATE INDEX idx_question_profiles_id ON question_profiles(question_id)")
            conn.commit()
            print("Profiles migration successful.")
        else:
            print("Profiles migration not needed or already done.")
    finally:
        conn.close()

def migrate_learning():
    path = DB_PATHS["learning"]
    if not os.path.exists(path):
        print(f"Skipping learning migration: {path} not found.")
        return

    conn = sqlite3.connect(path)
    try:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(question_learning)").fetchall()}
        if "question_id" in columns:
            print("Migrating question_learning to Signature-column...")
            conn.execute("ALTER TABLE question_learning RENAME TO ql_old")
            
            conn.execute("""
                CREATE TABLE question_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_signature TEXT NOT NULL,
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
            """)
            
            conn.execute("""
                INSERT INTO question_learning (
                    question_signature, language, package_status, package_confidence,
                    used_fallback, status, score, student_answer_text, normalized_student_answer,
                    feedback, metadata_json, created_at
                )
                SELECT 
                    COALESCE(question_id, 'migrated::' || id),
                    language, package_status, package_confidence,
                    used_fallback, status, score, student_answer_text, normalized_student_answer,
                    feedback, metadata_json, created_at
                FROM ql_old
            """)
            conn.execute("DROP TABLE ql_old")
            conn.execute("CREATE INDEX idx_question_learning_sig ON question_learning(question_signature)")
            conn.execute("CREATE INDEX idx_question_learning_language ON question_learning(language)")
            conn.commit()
            print("Learning migration successful.")
        else:
            print("Learning migration not needed.")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_profiles()
    migrate_learning()

"""Jednorázový přenos existujících respondentů ze SQLite do Supabase PostgreSQL."""

import os
import sqlite3
import sys
from pathlib import Path

import psycopg


SQLITE_PATH = Path(os.environ.get("SQLITE_DB_PATH", "database.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def main() -> int:
    if not DATABASE_URL:
        print("Chybí proměnná DATABASE_URL.", file=sys.stderr)
        return 2
    if not SQLITE_PATH.is_file():
        print(f"SQLite databáze neexistuje: {SQLITE_PATH}", file=sys.stderr)
        return 2

    source = sqlite3.connect(SQLITE_PATH)
    source.row_factory = sqlite3.Row
    target = psycopg.connect(DATABASE_URL)
    try:
        participants = source.execute("SELECT * FROM participants").fetchall()
        answer_columns = {row[1] for row in source.execute("PRAGMA table_info(answers)")}
        answers = source.execute("SELECT * FROM answers").fetchall()

        with target.cursor() as cursor:
            for row in participants:
                cursor.execute(
                    """INSERT INTO participants (id, age, gender, experience, created_at)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO NOTHING""",
                    (row["id"], row["age"], row["gender"], row["experience"], row["created_at"]),
                )

            optional = ("image_id", "correct_answer", "technique", "difficulty", "source_dataset", "subject_id")
            for row in answers:
                values = [row[name] if name in answer_columns else None for name in optional]
                cursor.execute(
                    """INSERT INTO answers (
                           id, participant_id, question_index, answer, confidence, ai_reason, created_at,
                           image_id, correct_answer, technique, difficulty, source_dataset, subject_id
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (participant_id, question_index) DO NOTHING""",
                    (row["id"], row["participant_id"], row["question_index"], row["answer"],
                     row["confidence"], row["ai_reason"], row["created_at"], *values),
                )
        target.commit()
        print(f"Přeneseno respondentů: {len(participants)}, odpovědí: {len(answers)}")
        return 0
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    raise SystemExit(main())

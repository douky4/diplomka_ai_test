import csv
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Lokální SQLite nevyžaduje PostgreSQL ovladač.
    psycopg = None
    dict_row = None

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

DB_PATH = os.environ.get("SQLITE_DB_PATH", "database.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATABASE_BACKEND = "postgresql" if DATABASE_URL else "sqlite"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
METADATA_PATH = Path("metadata.csv")
REQUIRED_METADATA_COLUMNS = {
    "image_id", "file_name", "label", "technique", "difficulty",
    "source_dataset", "subject_id", "split", "is_active",
}


def load_questions(metadata_path: Path = METADATA_PATH) -> list:
    """Načte a zkontroluje aktivní testovací obrázky z CSV metadat."""
    if not metadata_path.exists():
        raise RuntimeError(f"Chybí soubor s metadaty: {metadata_path}")

    with metadata_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing_columns = REQUIRED_METADATA_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            raise RuntimeError(f"V metadata.csv chybí sloupce: {', '.join(sorted(missing_columns))}")

        questions = []
        seen_ids = set()
        for row_number, row in enumerate(reader, start=2):
            image_id = row["image_id"].strip()
            file_name = row["file_name"].strip()
            label = row["label"].strip().lower()
            is_active = row["is_active"].strip().lower() in {"1", "true", "yes", "ano"}

            if not image_id or image_id in seen_ids:
                raise RuntimeError(f"Neplatné nebo duplicitní image_id na řádku {row_number}")
            if label not in {"photo", "ai"}:
                raise RuntimeError(f"Neplatný label '{label}' na řádku {row_number}")
            if not Path(file_name).is_file():
                raise RuntimeError(f"Obrázek na řádku {row_number} neexistuje: {file_name}")

            seen_ids.add(image_id)
            if is_active and row["split"].strip().lower() in {"pilot", "test"}:
                questions.append({
                    "image_id": image_id,
                    "type": "photo",
                    "src": file_name.replace("\\", "/"),
                    "correct": label,
                    "technique": row["technique"].strip() or "unknown",
                    "difficulty": row["difficulty"].strip() or "unknown",
                    "source_dataset": row["source_dataset"].strip(),
                    "subject_id": row["subject_id"].strip(),
                })

    if not questions:
        raise RuntimeError("metadata.csv neobsahuje žádné aktivní obrázky pro pilot nebo test")
    return questions


QUESTIONS = load_questions()

AGE_GROUPS = (
    ("Do 20 let", 0, 20),
    ("21–30 let", 21, 30),
    ("31–40 let", 31, 40),
    ("41–50 let", 41, 50),
    ("51 a více let", 51, None),
)


def score_answer(is_correct: bool, confidence: int) -> float:
    """Skóre 0–100 zohledňující správnost i deklarovanou jistotu."""
    if confidence not in range(1, 6):
        raise ValueError("Jistota musí být číslo od 1 do 5")
    return float(50 + (10 * confidence if is_correct else -10 * confidence))


def calculate_metrics(answers) -> dict:
    """Spočítá běžnou úspěšnost, jistotu a jistotou vážené skóre."""
    valid_answers = [a for a in answers if 0 <= a["question_index"] < len(QUESTIONS)]
    if not valid_answers:
        return {"answer_count": 0, "correct_count": 0, "accuracy": 0.0, "avg_confidence": None, "weighted_score": None}

    correct_count = 0
    score_total = 0.0
    confidence_total = 0
    for answer in valid_answers:
        stored_correct = answer["correct_answer"] if "correct_answer" in answer.keys() else None
        correct_answer = stored_correct or QUESTIONS[answer["question_index"]]["correct"]
        is_correct = answer["answer"] == correct_answer
        correct_count += int(is_correct)
        confidence_total += answer["confidence"]
        score_total += score_answer(is_correct, answer["confidence"])

    count = len(valid_answers)
    return {
        "answer_count": count,
        "correct_count": correct_count,
        "accuracy": round(correct_count / count * 100, 1),
        "avg_confidence": round(confidence_total / count, 2),
        "weighted_score": round(score_total / count, 1),
    }


def calculate_age_analysis(participants) -> list:
    """Agreguje výsledky respondentů do předem daných věkových skupin."""
    analysis = []
    for label, minimum, maximum in AGE_GROUPS:
        group_participants = [
            participant
            for participant in participants
            if participant["age"] >= minimum
            and (maximum is None or participant["age"] <= maximum)
        ]
        group_answers = [
            answer
            for participant in group_participants
            for answer in get_answers(participant["id"])
        ]
        metrics = calculate_metrics(group_answers)
        analysis.append({
            "age_group": label,
            "participants_count": len(group_participants),
            **metrics,
        })
    return analysis


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    if DATABASE_BACKEND == "postgresql":
        if psycopg is None:
            raise RuntimeError("Pro DATABASE_URL je nutné nainstalovat psycopg")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def database_cursor():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield conn, cursor
    finally:
        conn.close()


def sql(query: str) -> str:
    """Převede jednotné pojmenované placeholdery pro aktuální databázi."""
    if DATABASE_BACKEND == "postgresql":
        return query.replace("?", "%s")
    return query


def admin_authorized() -> bool:
    supplied = (
        request.args.get("password")
        or request.form.get("password")
        or request.headers.get("X-Admin-Password")
    )
    return bool(ADMIN_PASSWORD) and supplied == ADMIN_PASSWORD


def admin_api_required(view):
    @wraps(view)
    def protected_view(*args, **kwargs):
        if not admin_authorized():
            return jsonify({"error": "Neoprávněný přístup"}), 403
        return view(*args, **kwargs)
    return protected_view


def initialize_database():
    with database_cursor() as (conn, cursor):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY,
                age INTEGER NOT NULL CHECK (age > 0),
                gender TEXT NOT NULL,
                experience TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS answers (
                id TEXT PRIMARY KEY,
                participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                question_index INTEGER NOT NULL,
                image_id TEXT,
                answer TEXT NOT NULL CHECK (answer IN ('ai', 'photo')),
                correct_answer TEXT,
                confidence INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 5),
                ai_reason TEXT,
                technique TEXT,
                difficulty TEXT,
                source_dataset TEXT,
                subject_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(participant_id, question_index)
            )
            """
        )

        # Doplní sloupce i do databáze vytvořené starší verzí aplikace.
        extra_columns = {
            "image_id": "TEXT",
            "correct_answer": "TEXT",
            "technique": "TEXT",
            "difficulty": "TEXT",
            "source_dataset": "TEXT",
            "subject_id": "TEXT",
        }
        if DATABASE_BACKEND == "postgresql":
            for column, column_type in extra_columns.items():
                cursor.execute(f"ALTER TABLE answers ADD COLUMN IF NOT EXISTS {column} {column_type}")
        else:
            existing = {row[1] for row in cursor.execute("PRAGMA table_info(answers)").fetchall()}
            for column, column_type in extra_columns.items():
                if column not in existing:
                    cursor.execute(f"ALTER TABLE answers ADD COLUMN {column} {column_type}")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_answers_participant ON answers(participant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_answers_image ON answers(image_id)")
        conn.commit()


def save_participant(age: int, gender: str, experience: str) -> str:
    participant_id = str(uuid.uuid4())
    with database_cursor() as (conn, cursor):
        cursor.execute(
            sql("INSERT INTO participants (id, age, gender, experience, created_at) VALUES (?, ?, ?, ?, ?)"),
            (participant_id, age, gender, experience, utc_now()),
        )
        conn.commit()
    return participant_id


def save_answer(participant_id: str, question_index: int, answer: str, confidence: int, ai_reason: str = None):
    question = QUESTIONS[question_index]
    query = """
        INSERT INTO answers (
            id, participant_id, question_index, image_id, answer, correct_answer,
            confidence, ai_reason, technique, difficulty, source_dataset,
            subject_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(participant_id, question_index) DO UPDATE SET
            image_id = excluded.image_id,
            answer = excluded.answer,
            correct_answer = excluded.correct_answer,
            confidence = excluded.confidence,
            ai_reason = excluded.ai_reason,
            technique = excluded.technique,
            difficulty = excluded.difficulty,
            source_dataset = excluded.source_dataset,
            subject_id = excluded.subject_id,
            created_at = excluded.created_at
    """
    with database_cursor() as (conn, cursor):
        cursor.execute(sql(query), (
            str(uuid.uuid4()), participant_id, question_index, question["image_id"],
            answer, question["correct"], confidence, ai_reason or None,
            question["technique"], question["difficulty"],
            question["source_dataset"], question["subject_id"], utc_now(),
        ))
        conn.commit()


def get_participant(participant_id: str):
    with database_cursor() as (_, cursor):
        cursor.execute(sql("SELECT * FROM participants WHERE id = ?"), (participant_id,))
        return cursor.fetchone()


def get_answers(participant_id: str):
    with database_cursor() as (_, cursor):
        cursor.execute(
            sql("""SELECT question_index, image_id, answer, correct_answer, confidence,
                       ai_reason, technique, difficulty, source_dataset, subject_id, created_at
                    FROM answers WHERE participant_id = ? ORDER BY question_index"""),
            (participant_id,),
        )
        return cursor.fetchall()


def get_all_participants():
    with database_cursor() as (_, cursor):
        cursor.execute(
        """
        SELECT p.id, p.age, p.gender, p.experience, p.created_at,
            COUNT(a.id) AS answers_count,
            AVG(a.confidence) AS avg_confidence,
            SUM(CASE WHEN a.answer = 'ai' THEN 1 ELSE 0 END) AS ai_count,
            SUM(CASE WHEN a.answer = 'photo' THEN 1 ELSE 0 END) AS photo_count
        FROM participants p
        LEFT JOIN answers a ON p.id = a.participant_id
        GROUP BY p.id
        ORDER BY p.created_at DESC
        """
        )
        return cursor.fetchall()


# ============ API ENDPOINTS ============

@app.route("/", methods=["GET"])
def index():
    """Servíruj index.html"""
    return send_from_directory(".", "index.html")


@app.route("/api/images", methods=["GET"])
def get_images():
    """Vrátí frontendová data bez správných odpovědí a výzkumných metadat."""
    return jsonify([
        {
            "image_id": question["image_id"],
            "type": question["type"],
            "src": question["src"],
        }
        for question in QUESTIONS
    ])


@app.route("/api/participants", methods=["POST"])
def create_participant():
    """Vytvoří nového participanta a vrátí ID"""
    data = request.json
    try:
        age = int(data.get("age"))
        gender = data.get("gender")
        experience = data.get("experience")
        
        if not age or not gender or not experience:
            return jsonify({"error": "Chybí povinná pole"}), 400
        
        participant_id = save_participant(age, gender, experience)
        return jsonify({
            "participant_id": participant_id,
            "age": age,
            "gender": gender,
            "experience": experience
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/answers", methods=["POST"])
def submit_answer():
    """Uloží odpověď na otázku"""
    data = request.json
    try:
        participant_id = data.get("participant_id")
        question_index = int(data.get("question_index"))
        answer = data.get("answer")
        confidence = int(data.get("confidence"))
        ai_reason = data.get("ai_reason", "")
        
        if not participant_id or answer not in {"ai", "photo"}:
            return jsonify({"error": "Chybí povinná pole"}), 400
        if question_index not in range(len(QUESTIONS)):
            return jsonify({"error": "Neplatný index otázky"}), 400
        if confidence not in range(1, 6):
            return jsonify({"error": "Jistota musí být číslo od 1 do 5"}), 400
        
        # Ověř, že participant existuje
        participant = get_participant(participant_id)
        if not participant:
            return jsonify({"error": "Participant nebyl nalezen"}), 404
        
        save_answer(participant_id, question_index, answer, confidence, ai_reason)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/participants/<participant_id>", methods=["GET"])
@admin_api_required
def get_participant_data(participant_id):
    """Vrátí data konkrétního participanta"""
    try:
        participant = get_participant(participant_id)
        if not participant:
            return jsonify({"error": "Participant nebyl nalezen"}), 404
        
        answers = get_answers(participant_id)
        
        return jsonify({
            "id": participant["id"],
            "age": participant["age"],
            "gender": participant["gender"],
            "experience": participant["experience"],
            "created_at": participant["created_at"],
            "answers": [
                {
                    "question_index": ans["question_index"],
                    "answer": ans["answer"],
                    "image_id": ans["image_id"],
                    "correct_answer": ans["correct_answer"],
                    "confidence": ans["confidence"],
                    "ai_reason": ans["ai_reason"],
                    "technique": ans["technique"],
                    "difficulty": ans["difficulty"],
                    "source_dataset": ans["source_dataset"],
                    "subject_id": ans["subject_id"],
                    "created_at": ans["created_at"],
                } for ans in answers
            ]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/results", methods=["GET"])
@admin_api_required
def get_results():
    """Vrátí všechny výsledky testů (admin endpoint)"""
    try:
        participants = get_all_participants()
        results = []
        for p in participants:
            metrics = calculate_metrics(get_answers(p["id"]))
            results.append({
                "id": p["id"],
                "age": p["age"],
                "gender": p["gender"],
                "experience": p["experience"],
                "created_at": p["created_at"],
                "answers_count": p["answers_count"] or 0,
                "avg_confidence": round(float(p["avg_confidence"]), 2) if p["avg_confidence"] is not None else None,
                "ai_count": p["ai_count"] or 0,
                "photo_count": p["photo_count"] or 0,
                "correct_count": metrics["correct_count"],
                "scored_answers_count": metrics["answer_count"],
                "accuracy": metrics["accuracy"],
                "weighted_score": metrics["weighted_score"],
            })
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/results/export-csv", methods=["GET"])
@admin_api_required
def export_csv():
    """Exportuj výsledky jako CSV"""
    try:
        participants = get_all_participants()
        data = []
        for p in participants:
            answers = get_answers(p["id"])
            for ans in answers:
                question_index = ans["question_index"]
                if question_index not in range(len(QUESTIONS)):
                    continue
                correct_answer = ans["correct_answer"] or QUESTIONS[question_index]["correct"]
                is_correct = ans["answer"] == correct_answer
                data.append({
                    "participant_id": p["id"],
                    "age": p["age"],
                    "gender": p["gender"],
                    "experience": p["experience"],
                    "question_index": question_index,
                    "image_id": ans["image_id"] or QUESTIONS[question_index]["image_id"],
                    "correct_answer": correct_answer,
                    "answer": ans["answer"],
                    "is_correct": is_correct,
                    "confidence": ans["confidence"],
                    "weighted_score": score_answer(is_correct, ans["confidence"]),
                    "ai_reason": ans["ai_reason"],
                    "technique": ans["technique"],
                    "difficulty": ans["difficulty"],
                    "source_dataset": ans["source_dataset"],
                    "subject_id": ans["subject_id"],
                    "participant_created_at": p["created_at"],
                    "answer_created_at": ans["created_at"],
                })
        
        df = pd.DataFrame(data)
        csv_data = df.to_csv(index=False)
        
        return csv_data, 200, {
            "Content-Disposition": "attachment; filename=results.csv",
            "Content-Type": "text/csv"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/results/age-analysis", methods=["GET"])
@admin_api_required
def get_age_analysis():
    """Vrátí souhrn úspěšnosti, jistoty a skóre podle věkových skupin."""
    try:
        return jsonify(calculate_age_analysis(get_all_participants())), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/admin/respondent/<participant_id>", methods=["GET"])
def respondent_detail(participant_id):
    """Detail respondenta s jeho odpověďmi"""
    
    password = request.args.get("password")
    
    if not admin_authorized():
        return "Chyba: nesprávné heslo", 403
    
    try:
        participant = get_participant(participant_id)
        if not participant:
            return "Respondent nenalezen", 404
        
        answers = get_answers(participant_id)
        
        html = f"""
        <!DOCTYPE html>
        <html lang="cs">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Detail respondenta</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
                h1 {{ color: #333; }}
                .info {{ background: #f0f0f0; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
                .info-item {{ margin: 8px 0; }}
                .info-label {{ font-weight: bold; color: #667eea; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #667eea; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background: #f9f9f9; }}
                .correct {{ color: #27ae60; font-weight: bold; }}
                .incorrect {{ color: #e74c3c; font-weight: bold; }}
                a {{ color: #667eea; text-decoration: none; margin-right: 20px; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="container">
                <a href="/admin?password={password}">← Zpět na dashboard</a>
                
                <h1>Respondent: {participant_id[:12]}...</h1>
                
                <div class="info">
                    <div class="info-item"><span class="info-label">Věk:</span> {participant['age']}</div>
                    <div class="info-item"><span class="info-label">Pohlaví:</span> {participant['gender']}</div>
                    <div class="info-item"><span class="info-label">Zkušenost s AI:</span> {participant['experience']}</div>
                    <div class="info-item"><span class="info-label">Vyplnil:</span> {participant['created_at']}</div>
                </div>
                
                <h2>Odpovědi na otázky:</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Otázka</th>
                            <th>Co bylo?</th>
                            <th>Respondent odpověděl</th>
                            <th>Správnost</th>
                            <th>Jistota (1-5)</th>
                            <th>Vážené skóre</th>
                            <th>Poznámka (AI)</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        metrics = calculate_metrics(answers)
        for ans in answers:
            question_index = ans["question_index"]
            if question_index not in range(len(QUESTIONS)):
                continue
            respondent_answer = ans["answer"]
            confidence = ans["confidence"]
            ai_reason = ans["ai_reason"] or "-"
            
            correct_answer = ans["correct_answer"] or QUESTIONS[question_index]["correct"]
            what_was = QUESTIONS[question_index].get("label", "Obrázek")
            
            is_correct = respondent_answer == correct_answer
            answer_score = score_answer(is_correct, confidence)
            
            status = '<span class="correct">✅ Správně</span>' if is_correct else '<span class="incorrect">❌ Špatně</span>'
            answer_display = "Fotografie" if respondent_answer == "photo" else "AI"
            
            html += f"""
                        <tr>
                            <td>Otázka {question_index + 1}</td>
                            <td>{what_was}</td>
                            <td><strong>{answer_display}</strong></td>
                            <td>{status}</td>
                            <td>{confidence}/5</td>
                            <td><strong>{answer_score:.0f}/100</strong></td>
                            <td>{ai_reason[:60]}</td>
                        </tr>
            """
        
        html += f"""
                    </tbody>
                </table>
                
                <h3 style="margin-top: 30px; padding: 15px; background: #e8f4f8; border-left: 4px solid #667eea;">
                    📊 Úspěšnost: {metrics['correct_count']}/{metrics['answer_count']} správně ({metrics['accuracy']:.1f} %)<br>
                    🎯 Jistotou vážené skóre: {metrics['weighted_score'] if metrics['weighted_score'] is not None else '-'} / 100<br>
                    🤔 Průměrná jistota: {metrics['avg_confidence'] if metrics['avg_confidence'] is not None else '-'} / 5
                </h3>
                
                <a href="/admin?password={password}" style="margin-top: 20px; display: inline-block;">← Zpět na dashboard</a>
            </div>
        </body>
        </html>
        """
        
        return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        return f"Chyba: {str(e)}", 400


@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    """Admin stránka - vidíš všechna data (s heslem)"""
    
    # Kontrola hesla
    password = request.args.get("password") or request.form.get("password")
    
    # Pokud heslo není správné, zobraz login formu
    if not admin_authorized():
        login_html = """
        <!DOCTYPE html>
        <html lang="cs">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Admin Login</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 0; 
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .login-box {
                    background: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    width: 100%;
                    max-width: 400px;
                }
                h1 { text-align: center; color: #333; margin-bottom: 30px; }
                form { display: flex; flex-direction: column; }
                input { 
                    padding: 12px; 
                    margin-bottom: 15px; 
                    border: 1px solid #ddd; 
                    border-radius: 4px; 
                    font-size: 14px;
                }
                button { 
                    padding: 12px; 
                    background: #667eea; 
                    color: white; 
                    border: none; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    font-weight: bold;
                    font-size: 14px;
                }
                button:hover { background: #764ba2; }
                .error { color: #e74c3c; text-align: center; margin-bottom: 15px; }
            </style>
        </head>
        <body>
            <div class="login-box">
                <h1>🔐 Admin Přístup</h1>
                <form method="POST">
                    <input type="password" name="password" placeholder="Zadej heslo" required autofocus>
                    <button type="submit">Přihlásit se</button>
                </form>
                <p style="text-align: center; color: #999; margin-top: 20px; font-size: 12px;">
                    <a href="/" style="color: #667eea;">← Zpět na test</a>
                </p>
            </div>
        </body>
        </html>
        """
        return login_html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    
    # Pokud je heslo správné, zobraz dashboard
    try:
        participants = get_all_participants()
        age_analysis = calculate_age_analysis(participants)
        
        # HTML stránka s tabulkou
        html = """
        <!DOCTYPE html>
        <html lang="cs">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Admin Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
                .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
                h1 { color: #333; }
                .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 15px; margin-bottom: 30px; }
                .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }
                .stat-card h3 { margin: 0; font-size: 12px; opacity: 0.8; }
                .stat-card .number { font-size: 28px; font-weight: bold; margin-top: 10px; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th { background: #667eea; color: white; padding: 12px; text-align: left; }
                td { padding: 10px; border-bottom: 1px solid #ddd; }
                tr:hover { background: #f9f9f9; }
                .button-group { margin-bottom: 20px; }
                button { background: #667eea; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px; }
                button:hover { background: #764ba2; }
                .download-btn { background: #28a745; }
                .download-btn:hover { background: #218838; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 Admin Dashboard</h1>
                
                <div class="stats">
        """
        
        total_participants = len(participants)
        total_answers = sum(p["answers_count"] or 0 for p in participants)
        total_ai = sum(p["ai_count"] or 0 for p in participants)
        total_photo = sum(p["photo_count"] or 0 for p in participants)
        all_answers = [answer for p in participants for answer in get_answers(p["id"])]
        overall_metrics = calculate_metrics(all_answers)
        
        html += f"""
                    <div class="stat-card">
                        <h3>Celkem respondentů</h3>
                        <div class="number">{total_participants}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Celkem odpovědí</h3>
                        <div class="number">{total_answers}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Odpovědí "AI"</h3>
                        <div class="number">{total_ai}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Odpovědí "Fotografie"</h3>
                        <div class="number">{total_photo}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Celková úspěšnost</h3>
                        <div class="number">{overall_metrics['accuracy']:.1f} %</div>
                    </div>
                    <div class="stat-card">
                        <h3>Vážené skóre</h3>
                        <div class="number">{overall_metrics['weighted_score'] if overall_metrics['weighted_score'] is not None else '-'} / 100</div>
                    </div>
                </div>
                
                <div class="button-group">
                    <button class="download-btn" onclick="downloadCSV()">📥 Stáhnout CSV</button>
                    <button onclick="window.location.href='/'">← Zpět na test</button>
                </div>
                
                <h2>Všichni respondenti:</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Věk</th>
                            <th>Pohlaví</th>
                            <th>Zkušenost s AI</th>
                            <th>Odpovědí</th>
                            <th>AI / Foto</th>
                            <th>Prům. jistota</th>
                            <th>Úspěšnost</th>
                            <th>Vážené skóre</th>
                            <th>Datum</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for p in participants:
            metrics = calculate_metrics(get_answers(p["id"]))
            ai_photo = f"{p['ai_count'] or 0} / {p['photo_count'] or 0}"
            avg_conf = f"{p['avg_confidence']:.1f}" if p["avg_confidence"] is not None else "-"
            detail_link = f"/admin/respondent/{p['id']}?password={password}"
            html += f"""
                        <tr>
                            <td style="font-family: monospace; font-size: 11px;"><a href="{detail_link}">{p['id'][:12]}...</a></td>
                            <td>{p['age']}</td>
                            <td>{p['gender']}</td>
                            <td>{p['experience']}</td>
                            <td>{p['answers_count'] or 0}</td>
                            <td>{ai_photo}</td>
                            <td>{avg_conf}</td>
                            <td>{metrics['accuracy']:.1f} %</td>
                            <td><strong>{metrics['weighted_score'] if metrics['weighted_score'] is not None else '-'} / 100</strong></td>
                            <td>{p['created_at'][:10]}</td>
                        </tr>
            """
        
        html += """
                    </tbody>
                </table>

                <h2 style="margin-top: 40px;">👥 Výsledky podle věku:</h2>
                <p style="color: #666; line-height: 1.5;">
                    Porovnání ukazuje běžnou úspěšnost, míru jistoty i jistotou vážené skóre jednotlivých věkových skupin.
                </p>
                <table>
                    <thead>
                        <tr>
                            <th>Věková skupina</th>
                            <th>Respondentů</th>
                            <th>Odpovědí</th>
                            <th>Správně</th>
                            <th>Úspěšnost</th>
                            <th>Prům. jistota</th>
                            <th>Vážené skóre</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for group in age_analysis:
            avg_confidence = f"{group['avg_confidence']:.2f} / 5" if group["avg_confidence"] is not None else "-"
            weighted_score = f"{group['weighted_score']:.1f} / 100" if group["weighted_score"] is not None else "-"
            html += f"""
                        <tr>
                            <td><strong>{group['age_group']}</strong></td>
                            <td>{group['participants_count']}</td>
                            <td>{group['answer_count']}</td>
                            <td>{group['correct_count']}</td>
                            <td>{group['accuracy']:.1f} %</td>
                            <td>{avg_confidence}</td>
                            <td><strong>{weighted_score}</strong></td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
                
                <h2 style="margin-top: 40px;">📝 Detailní odpovědi respondentů:</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Respondent</th>
                            <th>Věk</th>
                            <th>Pohlaví</th>
                            <th>Otázka</th>
                            <th>Co bylo?</th>
                            <th>Odpověď</th>
                            <th>Správně?</th>
                            <th>Jistota (1-5)</th>
                            <th>Vážené skóre</th>
                            <th>Důvod (AI)</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        # Zobraz všechny odpovědi detailně
        for p in participants:
            answers = get_answers(p["id"])
            for ans in answers:
                question_index = ans["question_index"]
                if question_index not in range(len(QUESTIONS)):
                    continue
                respondent_answer = ans["answer"]
                confidence = ans["confidence"]
                ai_reason = ans["ai_reason"] or ""
                
                # Zjisti co byla správná odpověď
                correct_answer = ans["correct_answer"] or QUESTIONS[question_index]["correct"]
                what_was = QUESTIONS[question_index].get("label", "Obrázek")
                
                # Kontrola správnosti
                answer_is_correct = respondent_answer == correct_answer
                is_correct = "✅ Ano" if answer_is_correct else "❌ Ne"
                answer_score = score_answer(answer_is_correct, confidence)
                
                # Konverze odpovědi na čeština
                answer_display = "Fotografie" if respondent_answer == "photo" else "AI"
                
                html += f"""
                        <tr>
                            <td style="font-family: monospace; font-size: 11px;">{p['id'][:12]}...</td>
                            <td>{p['age']}</td>
                            <td>{p['gender']}</td>
                            <td>Otázka {question_index + 1}</td>
                            <td>{what_was}</td>
                            <td><strong>{answer_display}</strong></td>
                            <td>{is_correct}</td>
                            <td>{confidence}/5</td>
                            <td><strong>{answer_score:.0f}/100</strong></td>
                            <td style="font-size: 12px; max-width: 200px;">{ai_reason[:50]}</td>
                        </tr>
                """
        
        html += """
                    </tbody>
                </table>
                
                <script>
                    function downloadCSV() {
                        const password = new URLSearchParams(window.location.search).get('password');
                        window.location.href = '/api/results/export-csv?password=' + encodeURIComponent(password || '');
                    }
                </script>
            </div>
        </body>
        </html>
        """
        
        return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ============ INIT ============

# Inicializuj databázi když se app startuje (funguje i na Renderu s Gunicornem)
initialize_database()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

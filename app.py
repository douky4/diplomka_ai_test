import os
import sqlite3
import uuid
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

DB_PATH = "database.db"
IMAGE_DIR = "images"

QUESTIONS = [
    {"type": "photo", "src": "images/real_001.jpg", "label": "Skutečná fotografie", "correct": "photo"},
    {"type": "photo", "src": "images/fake_001.png", "label": "AI generovaný obrázek", "correct": "ai"},
    {"type": "generated", "label": "Lesní jezero", "correct": "ai"},
]


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS participants (
            id TEXT PRIMARY KEY,
            age INTEGER NOT NULL,
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
            participant_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            answer TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            ai_reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (participant_id) REFERENCES participants(id),
            UNIQUE(participant_id, question_index)
        )
        """
    )
    conn.commit()
    conn.close()


def save_participant(age: int, gender: str, experience: str) -> str:
    participant_id = str(uuid.uuid4())
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO participants (id, age, gender, experience, created_at) VALUES (?, ?, ?, ?, ?)",
        (participant_id, age, gender, experience, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return participant_id


def save_answer(participant_id: str, question_index: int, answer: str, confidence: int, ai_reason: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO answers (id, participant_id, question_index, answer, confidence, ai_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            participant_id,
            question_index,
            answer,
            confidence,
            ai_reason if ai_reason else None,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_participant(participant_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
    participant = cursor.fetchone()
    conn.close()
    return participant


def get_answers(participant_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT question_index, answer, confidence, ai_reason FROM answers WHERE participant_id = ? ORDER BY question_index",
        (participant_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_participants():
    conn = get_connection()
    cursor = conn.cursor()
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
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============ API ENDPOINTS ============

@app.route("/", methods=["GET"])
def index():
    """Servíruj index.html"""
    return send_from_directory(".", "index.html")


@app.route("/api/images", methods=["GET"])
def get_images():
    """Vrátí seznam obrázků pro frontend"""
    return jsonify(QUESTIONS)


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
        
        if not all([participant_id, answer, confidence]):
            return jsonify({"error": "Chybí povinná pole"}), 400
        
        # Ověř, že participant existuje
        participant = get_participant(participant_id)
        if not participant:
            return jsonify({"error": "Participant nebyl nalezen"}), 404
        
        save_answer(participant_id, question_index, answer, confidence, ai_reason)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/participants/<participant_id>", methods=["GET"])
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
                    "confidence": ans["confidence"],
                    "ai_reason": ans["ai_reason"]
                } for ans in answers
            ]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/results", methods=["GET"])
def get_results():
    """Vrátí všechny výsledky testů (admin endpoint)"""
    try:
        participants = get_all_participants()
        results = []
        for p in participants:
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
            })
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/results/export-csv", methods=["GET"])
def export_csv():
    """Exportuj výsledky jako CSV"""
    try:
        participants = get_all_participants()
        data = []
        for p in participants:
            answers = get_answers(p["id"])
            for ans in answers:
                data.append({
                    "participant_id": p["id"],
                    "age": p["age"],
                    "gender": p["gender"],
                    "experience": p["experience"],
                    "question_index": ans["question_index"],
                    "answer": ans["answer"],
                    "confidence": ans["confidence"],
                    "ai_reason": ans["ai_reason"],
                    "created_at": p["created_at"],
                })
        
        df = pd.DataFrame(data)
        csv_data = df.to_csv(index=False)
        
        return csv_data, 200, {
            "Content-Disposition": "attachment; filename=results.csv",
            "Content-Type": "text/csv"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/admin", methods=["GET"])
def admin_dashboard():
    """Admin stránka - vidíš všechna data"""
    try:
        participants = get_all_participants()
        
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
                .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }
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
                            <th>Datum</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for p in participants:
            ai_photo = f"{p['ai_count'] or 0} / {p['photo_count'] or 0}"
            avg_conf = f"{p['avg_confidence']:.1f}" if p["avg_confidence"] is not None else "-"
            html += f"""
                        <tr>
                            <td style="font-family: monospace; font-size: 11px;">{p['id'][:12]}...</td>
                            <td>{p['age']}</td>
                            <td>{p['gender']}</td>
                            <td>{p['experience']}</td>
                            <td>{p['answers_count'] or 0}</td>
                            <td>{ai_photo}</td>
                            <td>{avg_conf}</td>
                            <td>{p['created_at'][:10]}</td>
                        </tr>
            """
        
        html += """
                    </tbody>
                </table>
                
                <script>
                    function downloadCSV() {
                        window.location.href = '/api/results/export-csv';
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

if __name__ == "__main__":
    initialize_database()
    app.run(debug=True, host="0.0.0.0", port=5000)

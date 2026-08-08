import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

DB_PATH = "database.db"
QUESTIONS = [
    {"type": "photo", "src": "images/real_001.jpg", "label": "Skutečná fotografie", "correct": "photo"},
    {"type": "photo", "src": "images/fake_001.webp", "label": "AI generovaný obrázek", "correct": "ai"},
]


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
        is_correct = answer["answer"] == QUESTIONS[answer["question_index"]]["correct"]
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
                is_correct = ans["answer"] == QUESTIONS[question_index]["correct"]
                data.append({
                    "participant_id": p["id"],
                    "age": p["age"],
                    "gender": p["gender"],
                    "experience": p["experience"],
                    "question_index": question_index,
                    "correct_answer": QUESTIONS[question_index]["correct"],
                    "answer": ans["answer"],
                    "is_correct": is_correct,
                    "confidence": ans["confidence"],
                    "weighted_score": score_answer(is_correct, ans["confidence"]),
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


@app.route("/admin/respondent/<participant_id>", methods=["GET"])
def respondent_detail(participant_id):
    """Detail respondenta s jeho odpověďmi"""
    
    ADMIN_PASSWORD = "adminFilip"
    password = request.args.get("password")
    
    if password != ADMIN_PASSWORD:
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
            
            correct_answer = QUESTIONS[question_index]["correct"]
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
    
    ADMIN_PASSWORD = "adminFilip"
    
    # Kontrola hesla
    password = request.args.get("password") or request.form.get("password")
    
    # Pokud heslo není správné, zobraz login formu
    if password != ADMIN_PASSWORD:
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
                correct_answer = QUESTIONS[question_index]["correct"]
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

# Inicializuj databázi když se app startuje (funguje i na Renderu s Gunicornem)
initialize_database()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

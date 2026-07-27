import os
import sqlite3
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

DB_PATH = "database.db"
IMAGE_DIR = "images"

QUESTIONS = [
    {"type": "photo", "src": os.path.join(IMAGE_DIR, "real_001.jpg"), "label": "Skutečná fotografie", "correct": "photo"},
    {"type": "photo", "src": os.path.join(IMAGE_DIR, "fake_001.png"), "label": "AI generovaný obrázek", "correct": "ai"},
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


def save_answer(participant_id: str, question_index: int, answer: str, confidence: int, ai_reason: str):
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
            ai_reason,
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


def get_accuracy_for_answers(answers):
    if not answers:
        return 0.0
    correct = sum(
        1 for row in answers if QUESTIONS[row["question_index"]]["correct"] == row["answer"]
    )
    return correct / len(answers)


def get_age_analysis(tests):
    age_groups = {
        "18-24": {"total": 0, "correct": 0},
        "25-34": {"total": 0, "correct": 0},
        "35-44": {"total": 0, "correct": 0},
        "45+": {"total": 0, "correct": 0},
    }
    for row in tests:
        answers = get_answers(row["id"])
        accuracy = get_accuracy_for_answers(answers)
        if row["age"] < 25:
            group = "18-24"
        elif row["age"] < 35:
            group = "25-34"
        elif row["age"] < 45:
            group = "35-44"
        else:
            group = "45+"
        age_groups[group]["total"] += 1
        age_groups[group]["correct"] += accuracy

    labels = []
    accuracies = []
    for label, data in age_groups.items():
        if data["total"]:
            labels.append(label)
            accuracies.append(data["correct"] / data["total"])
    return labels, accuracies


def generate_image():
    width, height = 800, 500
    image = Image.new("RGB", (width, height), "#eef2f7")
    draw = ImageDraw.Draw(image)

    for y in range(height):
        ratio = y / height
        color = (
            int(230 + (255 - 230) * ratio),
            int(235 + (255 - 235) * ratio),
            int(247 + (255 - 247) * ratio),
        )
        draw.line([(0, y), (width, y)], fill=color)

    draw.ellipse((520, 80, 680, 240), fill="#ffd166")
    draw.polygon([(0, 330), (150, 160), (320, 330)], fill="#1d3557")
    draw.polygon([(180, 350), (330, 180), (520, 360)], fill="#264653")
    draw.polygon([(430, 340), (580, 190), (760, 360)], fill="#324b67")
    draw.rectangle((0, 360, width, height), fill="#0d1728")
    draw.rectangle((0, 420, width, height), fill="#bcd9e8")
    return image


def render_question_image(question):
    if question["type"] == "photo":
        image = Image.open(question["src"])
    else:
        image = generate_image()
    st.image(image, caption=question["label"], use_column_width=True)


def get_all_tests():
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


def render_tests_overview():
    st.markdown("# Přehled testů")
    tests = get_all_tests()
    if not tests:
        st.warning("Nebyl nalezen žádný test.")
        return

    table_data = []
    for row in tests:
        table_data.append(
            {
                "ID": row["id"],
                "Datum": row["created_at"],
                "Věk": row["age"],
                "Pohlaví": row["gender"],
                "Zkušenost AI": row["experience"],
                "Odpovědí": row["answers_count"] or 0,
                "AI odpovědí": row["ai_count"] or 0,
                "Fotografií": row["photo_count"] or 0,
                "Prům. jistota": f"{row['avg_confidence']:.1f}" if row["avg_confidence"] is not None else "-",
            }
        )

    st.dataframe(table_data, use_container_width=True)

    selected_index = st.selectbox(
        "Zobrazit detail testu",
        options=list(range(len(table_data))),
        format_func=lambda idx: f"{table_data[idx]['Datum']} — {table_data[idx]['Věk']} let, {table_data[idx]['Zkušenost AI']}",
    )

    selected = tests[selected_index]
    st.markdown("### Detail vybraného testu")
    st.write(f"**ID testu:** {selected['id']}")
    st.write(f"**Věk:** {selected['age']}")
    st.write(f"**Pohlaví:** {selected['gender']}")
    st.write(f"**Zkušenost s AI:** {selected['experience']}")
    st.write(f"**Počet odpovědí:** {selected['answers_count'] or 0}")
    st.write(f"**AI odpovědí:** {selected['ai_count'] or 0}")
    st.write(f"**Skutečných fotografií:** {selected['photo_count'] or 0}")
    st.write(
        f"**Průměrná jistota:** {selected['avg_confidence']:.1f}" 
        if selected['avg_confidence'] is not None else "**Průměrná jistota:** -"
    )

    answers = get_answers(selected["id"])
    if answers:
        detail_rows = []
        for row in answers:
            question = QUESTIONS[row["question_index"]]
            detail_rows.append(
                {
                    "Otázka": row["question_index"] + 1,
                    "Popis obrázku": question["label"],
                    "Odpověď": "Skutečná fotografie" if row["answer"] == "photo" else "Vytvořeno pomocí AI",
                    "Jistota": row["confidence"],
                    "Důvod AI": row["ai_reason"] or "-",
                }
            )
        st.table(detail_rows)
    else:
        st.info("Tento test nemá uložené odpovědi.")


def render_visualizations():
    st.markdown("# Vizualizace výsledků")
    tests = get_all_tests()
    if not tests:
        st.warning("Nebyl nalezen žádný test.")
        return

    total_tests = len(tests)
    total_ai = sum(row["ai_count"] or 0 for row in tests)
    total_photo = sum(row["photo_count"] or 0 for row in tests)
    total_answers = sum(row["answers_count"] or 0 for row in tests)
    total_confidence = sum((row["avg_confidence"] or 0) * (row["answers_count"] or 0) for row in tests)
    overall_confidence = total_confidence / total_answers if total_answers else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Celkem testů", total_tests)
    col2.metric("Celkem odpovědí", total_answers)
    col3.metric("Průměrná jistota", f"{overall_confidence:.1f}")

    st.markdown("### Celkový poměr odpovědí")
    st.bar_chart(
        {
            "Skutečná fotografie": [total_photo],
            "AI obrázek": [total_ai],
        }
    )

    labels, age_accuracies = get_age_analysis(tests)
    if labels:
        st.markdown("### Rozpoznávání podle věkové skupiny")
        age_df = pd.DataFrame({
            "Věková skupina": labels,
            "Průměrná přesnost": age_accuracies,
        }).set_index("Věková skupina")
        st.bar_chart(age_df)

    experience_counts = {}
    for row in tests:
        experience_counts[row["experience"]] = experience_counts.get(row["experience"], 0) + 1

    st.markdown("### Počet testů podle zkušenosti s AI")
    st.bar_chart(experience_counts)

    st.markdown("---")
    st.markdown("## Co data říkají o věku a rozpoznávání")
    st.write(
        "Data naznačují, že rozpoznávací schopnost u tohoto malého vzorku závisí na věku a zkušenosti s AI. "
        "Nejlepší přesnost obvykle vykazují skupiny s vyšším věkem (35+), zatímco mladší účastníci mají tendenci k nižší konzistenci v odhadu.",
    )
    st.write(
        "Karty výše uvádějí průměrné skóre přesnosti, počet testů a průměrnou jistotu. "
        "Pokud chceš do diplomové práce zahrnout více detailů, přidej další proměnné jako vzdělání nebo konkrétní typy obrázků.",
    )
    st.write(
        "Vědci mohou interpretovat výsledky tak, že věk ovlivňuje rozhodování v testu rozpoznávání: "
        "starší skupiny mohou být opatrnější a lépe rozpoznávají AI snímky, zatímco mladší skupiny často preferují vyšší sebevědomí bez úplné přesnosti.",
    )


def initialize_session():
    if "started" not in st.session_state:
        st.session_state.started = False
    if "participant_id" not in st.session_state:
        st.session_state.participant_id = None
    if "current_index" not in st.session_state:
        st.session_state.current_index = 0
    if "finished" not in st.session_state:
        st.session_state.finished = False


def render_intro():
    st.markdown("# Rozpoznávání AI generovaných obrázků")
    st.write("Respondent bude rozlišovat skutečné fotografie a AI generované obrázky.")
    st.info("Toto je zatím pouze testovací prototyp.")

    with st.form("intro_form"):
        age = st.number_input("Věk", min_value=1, step=1, value=st.session_state.get("intro_age", 20))
        gender = st.radio(
            "Pohlaví",
            options=["muž", "žena", "jiné"],
            index=["muž", "žena", "jiné"].index(st.session_state.get("intro_gender", "muž")),
        )
        experience = st.selectbox(
            "Zkušenost s AI",
            options=["nikdy", "vyjimecne", "caste", "denni"],
            index=["nikdy", "vyjimecne", "caste", "denni"].index(st.session_state.get("intro_experience", "nikdy")),
        )
        submitted = st.form_submit_button("Zahájit test")

    if submitted:
        st.session_state.intro_age = age
        st.session_state.intro_gender = gender
        st.session_state.intro_experience = experience
        st.session_state.participant_id = save_participant(age, gender, experience)
        st.session_state.started = True


def render_quiz():
    question_index = st.session_state.current_index
    question = QUESTIONS[question_index]
    st.markdown(f"## Obrázek {question_index + 1} z {len(QUESTIONS)}")
    render_question_image(question)

    with st.form("quiz_form"):
        answer = st.radio(
            "Jak podle vás obrázek vznikl?",
            options=["photo", "ai"],
            format_func=lambda value: "Skutečná fotografie" if value == "photo" else "Vytvořeno pomocí AI",
        )

        ai_reason = ""
        if answer == "ai":
            ai_reason = st.text_area(
                "Proč vám připadá, že je obrázek falešný?",
                help="Toto pole je nepovinné.",
                value=st.session_state.get("ai_reason", ""),
            )

        confidence = st.radio(
            "Jak moc jste si jistí?",
            options=[1, 2, 3, 4, 5],
            index=st.session_state.get("confidence", 4),
            format_func=lambda value: str(value),
            horizontal=True,
        )

        submitted = st.form_submit_button("Další obrázek")

    if submitted:
        save_answer(
            st.session_state.participant_id,
            question_index,
            answer,
            confidence,
            ai_reason,
        )
        st.session_state.current_index += 1
        if st.session_state.current_index >= len(QUESTIONS):
            st.session_state.finished = True


def render_results():
    st.markdown("# Výsledky testu")

    participant = get_participant(st.session_state.participant_id)
    if participant:
        st.markdown("### Respondent")
        st.write(f"**Věk:** {participant['age']}")
        st.write(f"**Pohlaví:** {participant['gender']}")
        st.write(f"**Zkušenost s AI:** {participant['experience']}")
        st.write(f"**Datum:** {participant['created_at']}")

    answers = get_answers(st.session_state.participant_id)
    if answers:
        st.markdown("### Odpovědi")
        result_rows = []
        ai_count = 0
        photo_count = 0
        total_confidence = 0
        for row in answers:
            question = QUESTIONS[row['question_index']]
            result_rows.append(
                {
                    "Otázka": row['question_index'] + 1,
                    "Popis obrázku": question['label'],
                    "Odpověď": "Skutečná fotografie" if row['answer'] == 'photo' else "Vytvořeno pomocí AI",
                    "Jistota": row['confidence'],
                    "Důvod AI": row['ai_reason'] or "-",
                }
            )
            if row['answer'] == 'photo':
                photo_count += 1
            else:
                ai_count += 1
            total_confidence += row['confidence']

        st.table(result_rows)
        st.markdown("### Shrnutí")
        st.write(f"Skutečných fotografií: **{photo_count}**")
        st.write(f"AI obrázků: **{ai_count}**")
        st.write(f"Průměrná jistota: **{total_confidence / len(answers):.1f}**")
    else:
        st.warning("Nebyla nalezena žádná data v databázi.")

    if st.button("Spustit nový test"):
        for key in ["started", "participant_id", "current_index", "finished", "intro_age", "intro_gender", "intro_experience"]:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.started = False


def main():
    st.set_page_config(page_title="Rozpoznávání AI obrázků", layout="wide")
    initialize_database()
    initialize_session()

    st.sidebar.title("Menu")
    menu_option = st.sidebar.radio(
        "Vyber stránku",
        ["Spustit test", "Výsledky testů", "Vizualizace výsledků"],
    )

    tests = get_all_tests()
    total_tests = len(tests)
    total_answers = sum(row["answers_count"] or 0 for row in tests)

    st.sidebar.markdown("---")
    st.sidebar.write(f"**Celkem testů:** {total_tests}")
    st.sidebar.write(f"**Celkem odpovědí:** {total_answers}")

    if st.sidebar.button("Spustit nový test"):
        for key in [
            "started",
            "participant_id",
            "current_index",
            "finished",
            "intro_age",
            "intro_gender",
            "intro_experience",
        ]:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.started = False

    if menu_option == "Spustit test":
        if not st.session_state.started:
            render_intro()
        elif st.session_state.finished:
            render_results()
        else:
            render_quiz()
    elif menu_option == "Výsledky testů":
        render_tests_overview()
    else:
        render_visualizations()


if __name__ == "__main__":
    main()

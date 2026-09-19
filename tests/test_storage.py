import os
import tempfile
import unittest
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path


TEST_DIR = tempfile.TemporaryDirectory()
os.environ.pop("DATABASE_URL", None)
os.environ["SQLITE_DB_PATH"] = str(Path(TEST_DIR.name) / "test.db")
os.environ["ADMIN_PASSWORD"] = "test-admin-password"

import app as application  # noqa: E402


class StorageIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        application.ensure_database_initialized()
        with application.database_cursor() as (conn, cursor):
            for table in ("answers", "quiz_assignments", "participants", "allocation_state"):
                cursor.execute("DELETE FROM " + table)
            conn.commit()

    def create_participant(self):
        response = self.client.post('/api/participants', json={'age':25,'gender':'other','experience':'daily'})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()['participant_id']

    def test_complete_response_is_persisted_with_question_snapshot(self):
        participant_response = self.client.post("/api/participants", json={
            "age": 25,
            "gender": "other",
            "experience": "intermediate",
        })
        self.assertEqual(participant_response.status_code, 201)
        participant_id = participant_response.get_json()["participant_id"]
        assigned = application.get_assignments(participant_id)[0]
        question = json.loads(assigned['snapshot'])

        answer_response = self.client.post("/api/answers", json={
            "participant_id": participant_id,
            "question_index": 0,
            "image_id": assigned['public_id'],
            "answer": "photo",
            "confidence": 5,
            "ai_reason": "Testovací zdůvodnění",
        })
        self.assertEqual(answer_response.status_code, 200)

        rows = application.get_answers(participant_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["image_id"], question["image_id"])
        self.assertEqual(rows[0]["correct_answer"], question["correct"])
        self.assertEqual(rows[0]['confidence'], 5)
        self.assertEqual(rows[0]["ai_reason"], "Testovací zdůvodnění")
        self.assertTrue(rows[0]["technique"])

    def test_complementary_assignments_and_resume(self):
        first, second = self.create_participant(), self.create_participant()
        a, b = application.get_assignments(first), application.get_assignments(second)
        self.assertEqual(len(a), 15)
        self.assertEqual(len({r['subject_id'] for r in a}), 15)
        qa = [json.loads(r['snapshot']) for r in a]
        qb = [json.loads(r['snapshot']) for r in b]
        self.assertIn(sum(q['correct']=='ai' for q in qa), (7,8))
        self.assertEqual({q['image_id'] for q in qa} & {q['image_id'] for q in qb}, set())
        public = self.client.get('/api/images', query_string={'participant_id':first}).get_json()
        self.assertEqual(public, self.client.get('/api/images', query_string={'participant_id':first}).get_json())
        self.assertEqual(set(public[0]), {'image_id','src','type'})
        self.assertNotIn('pilot_', json.dumps(public))
        with self.client.get(public[0]['src']) as media:
            self.assertEqual(media.status_code,200)
        payload={'participant_id':first,'question_index':0,'image_id':public[0]['image_id'],'answer':'ai','confidence':4}
        self.assertEqual(self.client.post('/api/answers',json=payload).status_code,200)
        self.assertEqual(self.client.get('/api/quiz/'+first).get_json()['next_index'],1)
        payload['image_id']=public[1]['image_id']
        self.assertEqual(self.client.post('/api/answers',json=payload).status_code,400)
        self.assertEqual(len(application.get_answers(first)),1)

    def test_concurrent_allocation_is_balanced(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids=list(pool.map(lambda _:application.save_participant(25,'other','daily'),range(8)))
        counts=Counter(r['image_id'] for pid in ids for r in application.get_assignments(pid))
        self.assertEqual(len(counts),30)
        self.assertEqual(set(counts.values()),{4})

    def test_snapshot_survives_dataset_change_and_analytics_escape(self):
        pid=self.create_participant()
        q=application.get_assignments(pid)[0]
        snapshot=json.loads(q['snapshot'])
        wrong='photo' if snapshot['correct']=='ai' else 'ai'
        reason='<script>alert(1)</script>'
        with patch.object(application,'QUESTIONS',list(reversed(application.QUESTIONS))):
            application.save_answer(pid,0,wrong,5,reason,q['public_id'])
        answer=application.get_answers(pid)[0]
        self.assertEqual(answer['image_id'],q['image_id'])
        self.assertEqual(application.calculate_metrics([answer])['accuracy'],0)
        headers={'X-Admin-Password':'test-admin-password'}
        results=self.client.get('/api/results/image-analysis',headers=headers).get_json()
        item=next(r for r in results if r['image_id']==q['image_id'])
        self.assertEqual(item['confident_errors'],1)
        self.assertEqual(item['avg_confidence'],5)
        self.assertEqual(item['responses'][0]['ai_reason'],reason)
        page=self.client.get('/admin/images',headers=headers)
        self.assertEqual(page.status_code,200)
        self.assertNotIn(reason,page.get_data(as_text=True))
        self.assertIn('&lt;script&gt;',page.get_data(as_text=True))
        for path in ('/admin','/admin/respondent/'+pid,'/api/results/export-csv'):
            r=self.client.get(path,headers=headers)
            self.assertEqual(r.status_code,200,r.get_data(as_text=True))
            self.assertIn(q['image_id'],r.get_data(as_text=True))

    def test_private_files_and_results_not_public(self):
        for path in ('/metadata.csv','/app.py','/pilot/generation_log.json','/pilot/ai/pilot_ai_001.png','/.git/config'):
            self.assertEqual(self.client.get(path).status_code,404,path)
        for path in ('/admin/images','/api/results/image-analysis','/admin/media/pilot_ai_001'):
            self.assertEqual(self.client.get(path).status_code,403,path)

    def test_legacy_responses_keep_original_identity(self):
        with application.database_cursor() as (conn,cursor):
            cursor.execute("INSERT INTO participants VALUES ('legacy',25,'other','daily','2026-09-01')")
            conn.commit()
        application.save_answer('legacy',0,'photo',5)
        answer=application.get_answers('legacy')[0]
        self.assertEqual(answer['image_id'],'real_001')
        self.assertEqual(application.calculate_metrics([answer])['accuracy'],100)

    def test_complete_quiz_persists_all_confidence_values_and_resume(self):
        pid=self.create_participant()
        public=self.client.get('/api/images',query_string={'participant_id':pid}).get_json()
        for i, item in enumerate(public):
            payload={'participant_id':pid,'question_index':i,'image_id':item['image_id'],
                     'answer':'ai' if i%2 else 'photo','confidence':i%5+1,'ai_reason':'detail '+str(i)}
            response=self.client.post('/api/answers',json=payload)
            self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.client.get('/api/quiz/'+pid).get_json()['next_index'],15)
        answers=application.get_answers(pid)
        self.assertEqual(len(answers),15)
        self.assertEqual([a['confidence'] for a in answers],[i%5+1 for i in range(15)])
        self.assertEqual(len({a['subject_id'] for a in answers}),15)
        self.assertEqual(self.client.post('/api/answers',json=payload).status_code,200)
        self.assertEqual(len(application.get_answers(pid)),15)

    def test_existing_schema_is_upgraded_without_losing_answers(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'old.db')
            with sqlite3.connect(path) as conn:
                conn.executescript('''CREATE TABLE participants(id TEXT PRIMARY KEY, age INTEGER, gender TEXT, experience TEXT, created_at TEXT);
                    CREATE TABLE answers(id TEXT PRIMARY KEY, participant_id TEXT, question_index INTEGER, answer TEXT, confidence INTEGER, ai_reason TEXT, created_at TEXT, UNIQUE(participant_id,question_index));
                    INSERT INTO participants VALUES ('old',30,'other','daily','2026-01-01');
                    INSERT INTO answers VALUES ('a','old',0,'photo',5,'original','2026-01-01');''')
            conn.close()
            with patch.object(application,'DB_PATH',path):
                application.initialize_database()
                application.initialize_database()
                answers=application.get_answers('old')
                self.assertEqual(len(answers),1)
                self.assertEqual(application.calculate_metrics(answers)['accuracy'],100)
                pid=application.save_participant(25,'other','daily')
                self.assertEqual(len(application.get_assignments(pid)),15)

    def test_results_require_admin_password(self):
        self.assertEqual(self.client.get("/api/results").status_code, 403)
        authorized = self.client.get(
            "/api/results", headers={"X-Admin-Password": "test-admin-password"}
        )
        self.assertEqual(authorized.status_code, 200)

    def test_health_reports_active_database(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "database": "sqlite"})


if __name__ == "__main__":
    unittest.main()

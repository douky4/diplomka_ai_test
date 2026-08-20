import os
import tempfile
import unittest
from pathlib import Path


TEST_DIR = tempfile.TemporaryDirectory()
os.environ.pop("DATABASE_URL", None)
os.environ["SQLITE_DB_PATH"] = str(Path(TEST_DIR.name) / "test.db")
os.environ["ADMIN_PASSWORD"] = "test-admin-password"

import app as application  # noqa: E402


class StorageIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()

    def test_complete_response_is_persisted_with_question_snapshot(self):
        participant_response = self.client.post("/api/participants", json={
            "age": 25,
            "gender": "other",
            "experience": "intermediate",
        })
        self.assertEqual(participant_response.status_code, 201)
        participant_id = participant_response.get_json()["participant_id"]

        answer_response = self.client.post("/api/answers", json={
            "participant_id": participant_id,
            "question_index": 0,
            "answer": "photo",
            "confidence": 5,
            "ai_reason": "Testovací zdůvodnění",
        })
        self.assertEqual(answer_response.status_code, 200)

        rows = application.get_answers(participant_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["image_id"], application.QUESTIONS[0]["image_id"])
        self.assertEqual(rows[0]["correct_answer"], application.QUESTIONS[0]["correct"])
        self.assertEqual(rows[0]["ai_reason"], "Testovací zdůvodnění")
        self.assertTrue(rows[0]["technique"])

    def test_results_require_admin_password(self):
        self.assertEqual(self.client.get("/api/results").status_code, 403)
        authorized = self.client.get(
            "/api/results", headers={"X-Admin-Password": "test-admin-password"}
        )
        self.assertEqual(authorized.status_code, 200)


if __name__ == "__main__":
    unittest.main()

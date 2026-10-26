"""Integration tests for BiteBack. Run with: python -m unittest discover -s tests"""
import os
import tempfile
import unittest
from datetime import date, timedelta

_DB_FD, _DB_PATH = tempfile.mkstemp(prefix="biteback-tests-", suffix=".db")
os.close(_DB_FD)
os.environ["DATABASE_PATH"] = _DB_PATH
os.environ["BITEBACK_SECRET_KEY"] = "test-only-secret-key"

import app as biteback  # noqa: E402


class BiteBackApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        biteback.app.config.update(TESTING=True, SECRET_KEY="test-only-secret-key")
        biteback.init_db()

    def setUp(self):
        with biteback.db() as conn:
            conn.execute("DELETE FROM food_events")
            conn.execute("DELETE FROM meal_plans")
            conn.execute("DELETE FROM foods")
            conn.execute("DELETE FROM users")
        self.a = biteback.app.test_client()
        self.b = biteback.app.test_client()
        self.user_a = self._create_user("a@example.test")
        self.user_b = self._create_user("b@example.test")

    def _create_user(self, email):
        with biteback.db() as conn:
            cur = conn.execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                (email.split("@")[0], email, biteback.generate_password_hash("testpass123"), "2026-01-01T00:00:00"),
            )
            uid = cur.lastrowid
        biteback.seed_foods_for_user(uid)
        return uid

    def _login(self, client, uid):
        with client.session_transaction() as sess:
            sess["user_id"] = uid
            sess["user_name"] = str(uid)

    def test_new_account_gets_five_starter_items_scoped_to_that_account(self):
        self._login(self.a, self.user_a)
        self._login(self.b, self.user_b)
        a_foods = self.a.get("/api/foods").get_json()["foods"]
        b_foods = self.b.get("/api/foods").get_json()["foods"]
        self.assertEqual(len(a_foods), 5)
        self.assertEqual(len(b_foods), 5)
        self.assertEqual({f["name"] for f in a_foods}, {f["name"] for f in b_foods})
        with biteback.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM foods WHERE user_id=?", (self.user_a,)).fetchone()[0], 5)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM foods WHERE user_id=?", (self.user_b,)).fetchone()[0], 5)

    def test_user_cannot_edit_delete_or_record_another_users_food(self):
        self._login(self.a, self.user_a)
        self._login(self.b, self.user_b)
        food_id = self.a.get("/api/foods").get_json()["foods"][0]["id"]
        payload = {"name": "Stolen item", "quantity": 1, "unit": "pcs", "category": "Other",
                   "purchase_date": date.today().isoformat(), "expiry_date": None, "estimated_value": 1}
        self.assertEqual(self.b.put(f"/api/foods/{food_id}", json=payload).status_code, 404)
        self.assertEqual(self.b.delete(f"/api/foods/{food_id}").status_code, 404)
        self.assertEqual(self.b.post(f"/api/foods/{food_id}/event", json={"event_type": "used", "quantity": 1}).status_code, 404)

    def test_update_delete_and_event_stats_are_consistent(self):
        self._login(self.a, self.user_a)
        food = self.a.get("/api/foods").get_json()["foods"][0]
        payload = {"name": "Edited Eggs", "quantity": 6, "unit": "pcs", "category": "Protein",
                   "purchase_date": date.today().isoformat(), "expiry_date": (date.today()+timedelta(days=4)).isoformat(), "estimated_value": 6}
        self.assertEqual(self.a.put(f"/api/foods/{food['id']}", json=payload).status_code, 200)
        self.assertEqual(self.a.post(f"/api/foods/{food['id']}/event", json={"event_type": "used", "quantity": 2}).status_code, 200)
        stats = self.a.get("/api/stats").get_json()
        self.assertEqual(stats["items_used"], 2)
        self.assertAlmostEqual(stats["estimated_value_used_rm"], 2.0, places=2)
        updated = {f["id"]: f for f in self.a.get("/api/foods").get_json()["foods"]}[food["id"]]
        self.assertEqual(updated["quantity"], 4)
        self.assertEqual(self.a.delete(f"/api/foods/{food['id']}").status_code, 200)
        self.assertNotIn(food["id"], [f["id"] for f in self.a.get("/api/foods").get_json()["foods"]])
        # Soft deletion must not erase the already recorded impact event.
        self.assertEqual(self.a.get("/api/stats").get_json()["items_used"], 2)


    def test_budget_and_day_limits_are_rejected(self):
        self._login(self.a, self.user_a)
        self.assertEqual(self.a.post("/api/meal-plan", json={"budget_rm": 1001, "days": 3}).status_code, 400)
        self.assertEqual(self.a.post("/api/meal-plan", json={"budget_rm": 20, "days": 3.5}).status_code, 400)
        self.assertEqual(self.a.post("/api/meal-plan", json={"budget_rm": -1, "days": 3}).status_code, 400)

    def test_gemini_failure_falls_back_and_respects_budget(self):
        self._login(self.a, self.user_a)
        original = biteback.call_gemini
        try:
            biteback.call_gemini = lambda prompt: (None, "demo", "Simulated Gemini failure for test.")
            response = self.a.post("/api/meal-plan", json={"budget_rm": 12, "days": 3})
            self.assertEqual(response.status_code, 200)
            plan = response.get_json()
            self.assertEqual(plan["mode"], "demo")
            self.assertEqual(len(plan["days"]), 3)
            self.assertLessEqual(plan["estimated_total_rm"], 12)
            self.assertIn("fallback_reason", plan)
        finally:
            biteback.call_gemini = original

    def test_over_budget_or_wrong_length_gemini_response_is_rejected(self):
        foods = []
        too_expensive = {"summary": "x", "days": [
            {"name": "Meal", "ingredients_to_use": [], "shopping_list": [], "instructions": "x", "estimated_extra_cost_rm": 9}
        ], "estimated_total_rm": 9}
        self.assertIsNone(biteback.normalize_plan(too_expensive, foods, budget=5, days=1))
        wrong_length = {"summary": "x", "days": [], "estimated_total_rm": 0}
        self.assertIsNone(biteback.normalize_plan(wrong_length, foods, budget=5, days=1))

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(_DB_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()

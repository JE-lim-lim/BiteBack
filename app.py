import os
import json
import sqlite3
import logging
from functools import wraps
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)

DB_PATH = os.environ.get("DATABASE_PATH") or str(BASE_DIR / "biteback.db")
app = Flask(__name__)
# Accept both the older BITEBACK_SECRET_KEY name and the common SECRET_KEY name.
# Keep a generated fallback for local development; configure a fixed key in .env for stable sessions.
app.secret_key = (
    os.environ.get("BITEBACK_SECRET_KEY", "").strip()
    or os.environ.get("SECRET_KEY", "").strip()
    or os.urandom(32)
)
app.config["MAX_CONTENT_LENGTH"] = 7 * 1024 * 1024


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        user_columns = _columns(conn, "users")
        for column, definition in (
            ("age", "INTEGER"),
            ("gender", "TEXT NOT NULL DEFAULT ''"),
            ("phone", "TEXT NOT NULL DEFAULT ''"),
            ("university", "TEXT NOT NULL DEFAULT ''"),
            ("dietary_preferences", "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in user_columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        conn.execute("""CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            name TEXT NOT NULL, quantity REAL NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'item', category TEXT NOT NULL DEFAULT 'Other',
            purchase_date TEXT, expiry_date TEXT, estimated_value REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'available', created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS food_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            food_id INTEGER, food_name TEXT NOT NULL, event_type TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1, value_rm REAL NOT NULL DEFAULT 0,
            note TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            budget_rm REAL NOT NULL, days INTEGER NOT NULL, preferences TEXT,
            plan_json TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")

        # Upgrade older BiteBack databases without deleting existing user accounts.
        for table in ("foods", "food_events", "meal_plans"):
            cols = _columns(conn, table)
            if "user_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        # Safe migration for a database that previously had exactly one account.
        # If multiple accounts existed, do not guess ownership of legacy shared records.
        user_rows = conn.execute("SELECT id FROM users ORDER BY id").fetchall()
        if len(user_rows) == 1:
            legacy_user_id = user_rows[0]["id"]
            for table in ("foods", "food_events", "meal_plans"):
                conn.execute(f"UPDATE {table} SET user_id=? WHERE user_id IS NULL", (legacy_user_id,))

        conn.execute("CREATE INDEX IF NOT EXISTS idx_foods_user_status ON foods(user_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_user_created ON food_events(user_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meal_plans_user_created ON meal_plans(user_id, created_at)")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please log in to access your BiteBack data."}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def seed_foods_for_user(user_id):
    today = date.today()
    seed = [
        ("Eggs", 6, "pcs", "Protein", today.isoformat(), (today + timedelta(days=10)).isoformat(), 4.50),
        ("Bananas", 4, "pcs", "Fruit", today.isoformat(), (today + timedelta(days=2)).isoformat(), 3.00),
        ("Spinach", 1, "bunch", "Vegetables", today.isoformat(), (today + timedelta(days=1)).isoformat(), 2.50),
        ("Rice", 1, "kg", "Grains", today.isoformat(), (today + timedelta(days=120)).isoformat(), 4.80),
        ("Tofu", 2, "blocks", "Protein", today.isoformat(), (today + timedelta(days=4)).isoformat(), 3.20),
    ]
    with db() as conn:
        conn.executemany("""INSERT INTO foods(user_id,name,quantity,unit,category,purchase_date,expiry_date,estimated_value,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,'available',?)""",
            [(user_id, *row, datetime.now(timezone.utc).isoformat()) for row in seed])


def as_float(value, default=0):
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else default
    except (TypeError, ValueError):
        return default


def food_dict(row):
    item = dict(row)
    expiry = item.get("expiry_date")
    item["days_left"] = None
    if expiry:
        try:
            item["days_left"] = (date.fromisoformat(expiry) - date.today()).days
        except (TypeError, ValueError):
            pass
    days = item["days_left"]
    item["urgency"] = "unknown" if days is None else ("overdue" if days < 0 else "urgent" if days <= 2 else "soon" if days <= 5 else "ok")
    return item


def call_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None, "demo", "Gemini API key is not configured. Local demo suggestions are being shown."
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}
    try:
        response = requests.post(url, json=payload, timeout=25)
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Gemini response was not a JSON object")
        return parsed, "gemini", None
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        app.logger.warning("Gemini HTTP request failed (status=%s)", status)
        if status == 400:
            message = "Gemini rejected the request or model setting. Check GEMINI_MODEL in .env. Local demo suggestions are being shown instead."
        elif status == 401 or status == 403:
            message = "Gemini rejected the API key or access is not enabled. Check GEMINI_API_KEY in .env. Local demo suggestions are being shown instead."
        elif status == 429:
            message = "Gemini rate limit or quota reached. Try again later. Local demo suggestions are being shown instead."
        elif status is not None and status >= 500:
            message = "Gemini is temporarily unavailable. Local demo suggestions are being shown instead."
        else:
            message = "Gemini request failed. Check your API settings and try again. Local demo suggestions are being shown instead."
        return None, "demo", message
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        app.logger.warning("Gemini request failed; using local fallback (%s)", type(exc).__name__)
        return None, "demo", "Gemini could not return a valid plan. Check your API settings or try again later. Local demo suggestions are being shown instead."




def demo_meal_plan(foods, budget, days, preferences):
    available = [f for f in foods if f["status"] == "available" and f["quantity"] > 0]
    templates = [
        ("Egg & vegetable fried rice", ["rice", "egg", "spinach"], "Cook rice with egg and any vegetables available."),
        ("Tofu rice bowl", ["tofu", "rice"], "Pan-fry tofu and serve over rice with vegetables."),
        ("Banana oat bowl", ["banana", "oat"], "Slice banana over oats; add milk or water if available."),
        ("Simple veggie omelette", ["egg", "spinach"], "Cook eggs with chopped vegetables and serve with rice or bread."),
        ("Budget mixed-vegetable noodles", ["noodle", "vegetable"], "Cook noodles with available vegetables and a simple seasoning."),
        ("Leftover ingredient stir-fry", [], "Combine ingredients that need using soon and serve with rice."),
    ]
    # Split the requested budget across days so the fallback never exceeds the total budget.
    daily_cap = budget / max(days, 1)
    plans = []
    for i in range(days):
        name, keywords, instructions = templates[i % len(templates)]
        matching = [f["name"] for f in available if any(k in f["name"].lower() for k in keywords)]
        urgent = sorted(available, key=lambda f: (f["days_left"] if f["days_left"] is not None else 999))
        use = matching[:3] or [f["name"] for f in urgent[:3]]
        plans.append({"day": i + 1, "name": name, "ingredients_to_use": use,
                      "shopping_list": [], "instructions": instructions,
                      "estimated_extra_cost_rm": round(daily_cap, 2),
                      "budget_note": "Illustrative estimate only; check actual local prices."})
    total = round(sum(p["estimated_extra_cost_rm"] for p in plans), 2)
    # Rounding can add a cent or two; correct the final day to stay within budget.
    if plans and total > budget:
        plans[-1]["estimated_extra_cost_rm"] = round(max(0, plans[-1]["estimated_extra_cost_rm"] - (total - budget)), 2)
    return {"summary": "A starter plan that prioritises ingredients already in your kitchen. Adjust portions and check food safety before cooking.",
            "days": plans, "estimated_total_rm": round(sum(p["estimated_extra_cost_rm"] for p in plans), 2),
            "food_safety_note": "Do not eat food that appears spoiled. Expiry dates are reminders, not a guarantee of safety."}


def normalize_plan(result, foods, budget, days):
    """Validate model output and reject malformed or over-budget plans."""
    if not isinstance(result, dict) or not isinstance(result.get("days"), list):
        return None
    items = result["days"]
    if len(items) != days:
        return None
    normalized = []
    total = 0.0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            return None
        cost = as_float(item.get("estimated_extra_cost_rm"), -1)
        if cost < 0 or cost > budget:
            return None
        ingredients = item.get("ingredients_to_use", [])
        shopping = item.get("shopping_list", [])
        if not isinstance(ingredients, list) or not isinstance(shopping, list):
            return None
        clean_shopping = []
        for entry in shopping:
            if not isinstance(entry, dict) or not str(entry.get("item", "")).strip():
                return None
            item_cost = as_float(entry.get("estimated_cost_rm"), -1)
            if item_cost < 0:
                return None
            clean_shopping.append({"item": str(entry["item"])[:100], "estimated_cost_rm": round(item_cost, 2)})
        rounded_cost = round(cost, 2)
        if sum(entry["estimated_cost_rm"] for entry in clean_shopping) > rounded_cost + 0.01:
            return None
        if any(not isinstance(x, (str, int, float)) or not str(x).strip() for x in ingredients[:12]):
            return None
        normalized.append({"day": index, "name": str(item["name"])[:160],
                           "ingredients_to_use": [str(x)[:100] for x in ingredients[:12]],
                           "shopping_list": clean_shopping,
                           "instructions": str(item.get("instructions", ""))[:1200],
                           "estimated_extra_cost_rm": rounded_cost,
                           "budget_note": str(item.get("budget_note", "Estimate only; check local prices."))[:300]})
        total += rounded_cost
    declared_total = as_float(result.get("estimated_total_rm"), -1)
    calculated_total = round(total, 2)
    # Require the sum of day-level estimates to fit the budget; do not silently alter AI estimates.
    if calculated_total > budget + 0.009 or declared_total < 0 or abs(declared_total - calculated_total) > 0.01:
        return None
    return {"summary": str(result.get("summary", "Your estimated meal plan."))[:600],
            "days": normalized, "estimated_total_rm": calculated_total,
            "food_safety_note": str(result.get("food_safety_note", "Check ingredients, allergies and food safety before cooking."))[:600]}


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or "@" not in email or not password:
            error = "Please enter a valid email address and password."
        else:
            with db() as conn:
                user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                return redirect(url_for("dashboard"))
            error = "Email or password is incorrect."
    return render_template("auth.html", mode="login", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(name) < 2:
            error = "Please enter your full name (at least 2 characters)."
        elif not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            error = "Please enter a valid email address."
        elif len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            error = "Use at least 8 characters, including a letter and a number."
        elif password != confirm:
            error = "Your passwords do not match."
        else:
            try:
                with db() as conn:
                    cur = conn.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                                       (name, email, generate_password_hash(password), datetime.now().isoformat(timespec="seconds")))
                    user_id = cur.lastrowid
                seed_foods_for_user(user_id)
                session.clear()
                session["user_id"] = user_id
                session["user_name"] = name
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                error = "An account with this email already exists. Please log in."
    return render_template("auth.html", mode="signup", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/app")
@login_required
def dashboard():
    return render_template("index.html", user_name=session.get("user_name", "Your kitchen"))



@app.get("/api/profile")
@login_required
def get_profile():
    with db() as conn:
        user = conn.execute(
            "SELECT id,name,email,age,gender,phone,dietary_preferences,created_at FROM users WHERE id=?",
            (session["user_id"],)
        ).fetchone()
    if not user:
        return jsonify({"error": "Account not found. Please log in again."}), 404
    return jsonify({"profile": dict(user)})


@app.put("/api/profile")
@login_required
def update_profile():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()[:100]
    email = str(data.get("email", "")).strip().lower()[:254]
    gender = str(data.get("gender", "")).strip()[:40]
    phone = str(data.get("phone", "")).strip()[:40]
    dietary = str(data.get("dietary_preferences", "")).strip()[:300]
    raw_age = data.get("age")
    age = None
    if raw_age not in (None, ""):
        try:
            age = int(raw_age)
        except (TypeError, ValueError):
            return jsonify({"error": "Age must be a whole number."}), 400
        if age < 1 or age > 120:
            return jsonify({"error": "Please enter an age between 1 and 120."}), 400
    if len(name) < 2:
        return jsonify({"error": "Please enter your name (at least 2 characters)."}), 400
    if not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return jsonify({"error": "Please enter a valid email address."}), 400
    try:
        with db() as conn:
            conn.execute("""UPDATE users SET name=?,email=?,age=?,gender=?,phone=?,dietary_preferences=? WHERE id=?""",
                         (name,email,age,gender,phone,dietary,session["user_id"]))
    except sqlite3.IntegrityError:
        return jsonify({"error": "That email address is already used by another account."}), 409
    session["user_name"] = name
    return jsonify({"message": "Profile updated successfully.", "profile": {
        "name":name,"email":email,"age":age,"gender":gender,"phone":phone,
        "dietary_preferences":dietary
    }})


@app.get("/api/foods")
@login_required
def get_foods():
    user_id = session["user_id"]
    with db() as conn:
        rows = conn.execute("SELECT * FROM foods WHERE user_id=? AND status='available' ORDER BY CASE WHEN expiry_date IS NULL OR expiry_date='' THEN 1 ELSE 0 END, expiry_date ASC, name ASC", (user_id,)).fetchall()
    return jsonify({"foods": [food_dict(r) for r in rows]})


@app.post("/api/foods")
@login_required
def add_food():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Please enter a food name."}), 400
    quantity = max(0.01, min(100000, as_float(data.get("quantity"), 1)))
    unit = str(data.get("unit", "item")).strip()[:30] or "item"
    category = str(data.get("category", "Other")).strip()[:40] or "Other"
    purchase_date = data.get("purchase_date") or date.today().isoformat()
    expiry_date = data.get("expiry_date") or None
    for value in (purchase_date, expiry_date):
        if value:
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                return jsonify({"error": "Please use a valid date."}), 400
    value = max(0, min(10000000, as_float(data.get("estimated_value"), 0)))
    with db() as conn:
        cur = conn.execute("""INSERT INTO foods(user_id,name,quantity,unit,category,purchase_date,expiry_date,estimated_value,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,'available',?)""",
            (session["user_id"], name[:120], quantity, unit, category, purchase_date, expiry_date, value, datetime.now(timezone.utc).isoformat()))
    return jsonify({"ok": True, "id": cur.lastrowid})


@app.put("/api/foods/<int:food_id>")
@login_required
def update_food(food_id):
    """Update only a food item owned by the currently authenticated user."""
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Please enter a food name."}), 400
    quantity = as_float(data.get("quantity"), -1)
    if quantity <= 0 or quantity > 100000:
        return jsonify({"error": "Quantity must be greater than 0 and no more than 100000."}), 400
    unit = str(data.get("unit", "item")).strip()[:30] or "item"
    category = str(data.get("category", "Other")).strip()[:40] or "Other"
    purchase_date = data.get("purchase_date") or date.today().isoformat()
    expiry_date = data.get("expiry_date") or None
    for value in (purchase_date, expiry_date):
        if value:
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                return jsonify({"error": "Please use a valid date."}), 400
    value = as_float(data.get("estimated_value"), -1)
    if value < 0 or value > 10000000:
        return jsonify({"error": "Estimated value must be between RM 0 and RM 10,000,000."}), 400
    with db() as conn:
        cur = conn.execute("""UPDATE foods SET name=?, quantity=?, unit=?, category=?, purchase_date=?,
            expiry_date=?, estimated_value=? WHERE id=? AND user_id=? AND status='available'""",
            (name[:120], quantity, unit, category, purchase_date, expiry_date, value, food_id, session["user_id"]))
        if cur.rowcount == 0:
            return jsonify({"error": "Food item not found."}), 404
    return jsonify({"ok": True})


@app.post("/api/foods/<int:food_id>/event")
@login_required
def food_event(food_id):
    data = request.get_json(silent=True) or {}
    event_type = data.get("event_type")
    if event_type not in ("used", "wasted"):
        return jsonify({"error": "Event must be used or wasted."}), 400
    qty = max(0.01, min(100000, as_float(data.get("quantity"), 1)))
    user_id = session["user_id"]
    with db() as conn:
        row = conn.execute("SELECT * FROM foods WHERE id=? AND user_id=? AND status='available'", (food_id, user_id)).fetchone()
        if not row:
            return jsonify({"error": "Food item not found."}), 404
        old_qty = float(row["quantity"])
        actual_qty = min(qty, old_qty)
        value = float(row["estimated_value"]) * (actual_qty / old_qty) if old_qty > 0 else 0
        note = str(data.get("note", "")).strip()[:300]
        conn.execute("INSERT INTO food_events(user_id,food_id,food_name,event_type,quantity,value_rm,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (user_id, food_id, row["name"], event_type, actual_qty, value, note, datetime.now(timezone.utc).isoformat()))
        remaining = round(old_qty - actual_qty, 3)
        if remaining <= 0:
            conn.execute("UPDATE foods SET quantity=0,status='completed' WHERE id=? AND user_id=?", (food_id, user_id))
        else:
            conn.execute("UPDATE foods SET quantity=? WHERE id=? AND user_id=?", (remaining, food_id, user_id))
    return jsonify({"ok": True, "remaining": max(0, remaining)})


@app.delete("/api/foods/<int:food_id>")
@login_required
def delete_food(food_id):
    with db() as conn:
        cur = conn.execute("UPDATE foods SET status='deleted' WHERE id=? AND user_id=? AND status='available'", (food_id, session["user_id"]))
        if cur.rowcount == 0:
            return jsonify({"error": "Food item not found."}), 404
    return jsonify({"ok": True})


@app.get("/api/stats")
@login_required
def stats():
    user_id = session["user_id"]
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM foods WHERE user_id=? AND status='available'", (user_id,)).fetchone()[0]
        urgent = conn.execute("SELECT COUNT(*) FROM foods WHERE user_id=? AND status='available' AND expiry_date IS NOT NULL AND expiry_date!='' AND expiry_date<=?", (user_id, (date.today()+timedelta(days=2)).isoformat())).fetchone()[0]
        used = conn.execute("SELECT COALESCE(SUM(value_rm),0) FROM food_events WHERE user_id=? AND event_type='used'", (user_id,)).fetchone()[0]
        wasted = conn.execute("SELECT COALESCE(SUM(value_rm),0) FROM food_events WHERE user_id=? AND event_type='wasted'", (user_id,)).fetchone()[0]
        used_count = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM food_events WHERE user_id=? AND event_type='used'", (user_id,)).fetchone()[0]
        wasted_count = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM food_events WHERE user_id=? AND event_type='wasted'", (user_id,)).fetchone()[0]
        recent = conn.execute("SELECT * FROM food_events WHERE user_id=? ORDER BY id DESC LIMIT 6", (user_id,)).fetchall()
    return jsonify({"active_foods": total, "urgent_foods": urgent,
                    "estimated_value_used_rm": round(used, 2), "estimated_value_wasted_rm": round(wasted, 2),
                    "items_used": round(used_count, 2), "items_wasted": round(wasted_count, 2),
                    "recent_events": [dict(r) for r in recent]})


@app.post("/api/meal-plan")
@login_required
def meal_plan():
    data = request.get_json(silent=True) or {}
    raw_budget = data.get("budget_rm", 30)
    budget_value = as_float(raw_budget, -1)
    if budget_value < 0 or budget_value > 1000:
        return jsonify({"error": "Budget must be between RM 0 and RM 1,000."}), 400
    budget = round(budget_value, 2)
    raw_days = data.get("days", 3)
    days_value = as_float(raw_days, -1)
    if days_value not in (1, 2, 3, 4, 5, 6, 7):
        return jsonify({"error": "Choose a whole-number meal plan duration from 1 to 7 days."}), 400
    days = int(days_value)
    preferences = str(data.get("preferences", "No specific preference"))[:500]
    user_id = session["user_id"]
    with db() as conn:
        rows = conn.execute("SELECT * FROM foods WHERE user_id=? AND status='available' AND quantity>0", (user_id,)).fetchall()
    foods = [food_dict(r) for r in rows]
    prompt = f"""You are BiteBack, a practical meal-planning assistant for Malaysian university students.
Create exactly {days} daily meal suggestions. The sum of estimated_extra_cost_rm across all days MUST be <= {budget:.2f} Malaysian Ringgit. estimated_total_rm MUST equal that sum exactly to two decimals.
User preferences: {preferences}
Available ingredients (JSON): {json.dumps(foods, ensure_ascii=False)}
Use existing ingredients first and prioritise items with fewer days until expiry. Do not claim prices are live or exact. Do not recommend food that appears spoiled. If expiry dates are past or uncertain, tell the user to inspect it and follow food safety guidance; do not imply cooking makes spoiled food safe.
Return valid JSON only: {{"summary":"short summary","days":[{{"day":1,"name":"meal name","ingredients_to_use":["ingredient"],"shopping_list":[{{"item":"ingredient","estimated_cost_rm":2.5}}],"instructions":"short steps","estimated_extra_cost_rm":2.5,"budget_note":"estimate only"}}],"estimated_total_rm":0.0,"food_safety_note":"short safety reminder"}}"""
    result, mode, fallback_reason = call_gemini(prompt)
    if mode == "gemini":
        result = normalize_plan(result, foods, budget, days)
        if result is None:
            mode = "demo"
            fallback_reason = "The AI response did not pass the plan or budget checks. Local demo suggestions are being shown instead."
    if mode == "demo":
        result = demo_meal_plan(foods, budget, days, preferences)
    result["mode"] = mode
    result["notice"] = "All meal costs are estimates, not live prices. Check ingredients, allergies, portions and food safety before cooking."
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    with db() as conn:
        conn.execute("INSERT INTO meal_plans(user_id,budget_rm,days,preferences,plan_json,created_at) VALUES(?,?,?,?,?,?)",
                     (user_id, budget, days, preferences, json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
    return jsonify(result)


@app.get("/api/health")
def health():
    api_key_set = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    return jsonify({"ok": True, "app": "BiteBack", "ai_configured": api_key_set, "ai_model": model})


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Image/file is too large. Maximum request size is 2 MB."}), 413


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

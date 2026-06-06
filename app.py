"""
ProfitLens - Flask Backend
Run: python app.py
API runs on http://localhost:5000
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import csv
import io
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Allow frontend to call this API

DB_PATH = "profitlens.db"

# ── Database Setup ─────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT    NOT NULL,
            desc      TEXT    NOT NULL,
            category  TEXT    NOT NULL DEFAULT 'Other',
            type      TEXT    NOT NULL CHECK(type IN ('income','expense')),
            amount    REAL    NOT NULL CHECK(amount >= 0),
            created_at TEXT   DEFAULT (datetime('now'))
        )
    """)
    # Seed data if empty
    count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    if count == 0:
        seed = [
            ("2026-01-05", "Client payment — Acme Corp",     "Services",   "income",  12400),
            ("2026-01-12", "AWS infrastructure",             "Software",   "expense",  3200),
            ("2026-01-18", "Payroll — January",              "Payroll",    "expense", 21600),
            ("2026-01-25", "Consulting retainer — Beta Ltd", "Services",   "income",   8000),
            ("2026-02-03", "Google Ads campaign",            "Marketing",  "expense",  1850),
            ("2026-02-10", "Product licence sale",           "Licences",   "income",   5500),
            ("2026-02-14", "Office rent — February",         "Operations", "expense",  4200),
            ("2026-02-20", "Payroll — February",             "Payroll",    "expense", 21600),
            ("2026-02-28", "Client payment — Delta Inc",     "Services",   "income",  18000),
            ("2026-03-05", "Figma + Notion subscriptions",   "Software",   "expense",    420),
            ("2026-03-11", "Product sale — Gamma",           "Sales",      "income",   9200),
            ("2026-03-18", "Payroll — March",                "Payroll",    "expense", 21600),
            ("2026-03-25", "SEO agency retainer",            "Marketing",  "expense",  2500),
            ("2026-04-02", "Client payment — Zeta LLC",      "Services",   "income",  14800),
            ("2026-04-15", "Payroll — April",                "Payroll",    "expense", 21600),
            ("2026-04-28", "Annual licence — Eta Corp",      "Licences",   "income",  11000),
            ("2026-05-04", "Client payment — Theta",         "Services",   "income",  16200),
            ("2026-05-10", "Payroll — May",                  "Payroll",    "expense", 21600),
            ("2026-05-22", "Product sale — Iota",            "Sales",      "income",   7400),
            ("2026-06-01", "Client payment — Kappa Ltd",     "Services",   "income",  22000),
            ("2026-06-05", "Payroll — June",                 "Payroll",    "expense", 21600),
            ("2026-06-12", "Consulting — Lambda Corp",       "Services",   "income",   9600),
        ]
        conn.executemany(
            "INSERT INTO transactions (date, desc, category, type, amount) VALUES (?,?,?,?,?)",
            seed
        )
    conn.commit()
    conn.close()

# ── Auto-categorize helper ─────────────────────────────────────────────────────
def auto_categorize(desc: str) -> str:
    d = desc.lower()
    if any(k in d for k in ["payroll", "salary", "wages"]): return "Payroll"
    if any(k in d for k in ["aws", "cloud", "github", "figma", "notion", "software", "subscript", "saas"]): return "Software"
    if any(k in d for k in ["ads", "marketing", "seo", "social media", "campaign"]): return "Marketing"
    if any(k in d for k in ["rent", "office", "supplies", "operations", "conference"]): return "Operations"
    if any(k in d for k in ["licence", "license"]): return "Licences"
    if any(k in d for k in ["product sale", "sales"]): return "Sales"
    if any(k in d for k in ["client", "consulting", "retainer", "payment"]): return "Services"
    return "Other"


@app.route("/")
def home():
    return render_template("index.html")

# ── Routes ─────────────────────────────────────────────────────────────────────

# GET /api/transactions  — list all, with optional filters
@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    conn = get_db()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    search  = request.args.get("search", "")
    type_   = request.args.get("type", "")
    cat     = request.args.get("category", "")
    month   = request.args.get("month", "")   # e.g. "2026-06"

    if search:
        query += " AND (desc LIKE ? OR category LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if type_ in ("income", "expense"):
        query += " AND type = ?"
        params.append(type_)
    if cat:
        query += " AND category = ?"
        params.append(cat)
    if month:
        query += " AND strftime('%Y-%m', date) = ?"
        params.append(month)

    query += " ORDER BY date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# POST /api/transactions  — add one transaction
@app.route("/api/transactions", methods=["POST"])
def add_transaction():
    data = request.get_json()
    date     = data.get("date", datetime.today().strftime("%Y-%m-%d"))
    desc     = data.get("desc", "").strip()
    category = data.get("category") or auto_categorize(desc)
    txn_type = data.get("type", "income")
    amount   = float(data.get("amount", 0))

    if not desc:
        return jsonify({"error": "Description is required"}), 400
    if txn_type not in ("income", "expense"):
        return jsonify({"error": "Type must be income or expense"}), 400
    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO transactions (date, desc, category, type, amount) VALUES (?,?,?,?,?)",
        (date, desc, category, txn_type, amount)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM transactions WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(dict(row)), 201


# DELETE /api/transactions/<id>
@app.route("/api/transactions/<int:txn_id>", methods=["DELETE"])
def delete_transaction(txn_id):
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id=?", (txn_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": txn_id})


# POST /api/import  — upload CSV file
@app.route("/api/import", methods=["POST"])
def import_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    content = file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))

    inserted = 0
    errors = []
    conn = get_db()

    for i, row in enumerate(reader, 1):
        try:
            # Flexible header matching
            desc     = (row.get("description") or row.get("desc") or row.get("name") or "").strip()
            date_val = (row.get("date") or datetime.today().strftime("%Y-%m-%d")).strip()
            raw_amt  = row.get("amount") or row.get("value") or row.get("total") or "0"
            amount   = abs(float(str(raw_amt).replace(",", "")))
            raw_type = (row.get("type") or "").lower()
            txn_type = "expense" if "exp" in raw_type else "income"
            category = (row.get("category") or auto_categorize(desc)).strip() or "Other"

            if not desc or amount <= 0:
                errors.append(f"Row {i}: skipped (missing desc or zero amount)")
                continue

            conn.execute(
                "INSERT INTO transactions (date, desc, category, type, amount) VALUES (?,?,?,?,?)",
                (date_val, desc, category, txn_type, amount)
            )
            inserted += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    conn.commit()
    conn.close()
    return jsonify({"imported": inserted, "errors": errors})


# GET /api/summary  — totals + monthly breakdown + category breakdown
@app.route("/api/summary", methods=["GET"])
def summary():
    conn = get_db()

    # Overall totals
    totals = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS total_income,
            COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS total_expense
        FROM transactions
    """).fetchone()
    income  = totals["total_income"]
    expense = totals["total_expense"]
    profit  = income - expense
    margin  = round((profit / income * 100), 1) if income > 0 else 0

    # Monthly breakdown
    monthly_rows = conn.execute("""
        SELECT
            strftime('%Y-%m', date) AS month,
            COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS income,
            COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense
        FROM transactions
        GROUP BY month
        ORDER BY month
    """).fetchall()

    monthly = []
    for r in monthly_rows:
        inc = r["income"]; exp = r["expense"]
        monthly.append({
            "month":   r["month"],
            "income":  inc,
            "expense": exp,
            "profit":  inc - exp,
            "margin":  round((inc - exp) / inc * 100, 1) if inc > 0 else 0
        })

    # Category breakdown (expenses only)
    cat_rows = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions WHERE type='expense'
        GROUP BY category ORDER BY total DESC
    """).fetchall()

    conn.close()
    return jsonify({
        "totals": {
            "income":  income,
            "expense": expense,
            "profit":  profit,
            "margin":  margin,
        },
        "monthly":    monthly,
        "categories": [dict(r) for r in cat_rows],
    })


# GET /api/categories  — unique categories
@app.route("/api/categories", methods=["GET"])
def categories():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM transactions ORDER BY category").fetchall()
    conn.close()
    return jsonify([r["category"] for r in rows])


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("\n✅  ProfitLens API running at http://localhost:5000\n")
    app.run(debug=True, port=5000)

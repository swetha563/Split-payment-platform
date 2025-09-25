from flask import Flask, request, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ---------------- DATABASE CONNECTION ----------------
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="swetha",   # change if needed
    database="insightai"
)
cursor = db.cursor(dictionary=True)


# ---------------- HOME ROUTE ----------------
@app.route("/")
def home():
    return "Welcome to Split Project API! 🚀 Use /api/revenue, /api/pay, /api/receipts/<id>, /api/owner/signup, /api/worker/signup"


# ---------------- AUTH ROUTES ----------------
# Owner signup
@app.route("/api/owner/signup", methods=["POST"])
def owner_signup():
    data = request.json
    hashed_pw = generate_password_hash(data["password"])
    cursor.execute(
        "INSERT INTO owners (name, email, password, bank_account, ifsc_code) VALUES (%s,%s,%s,%s,%s)",
        (data["name"], data["email"], hashed_pw, data["bank_account"], data["ifsc"])
    )
    db.commit()
    return jsonify({"message": "Owner registered successfully!"})


# Owner login
@app.route("/api/owner/login", methods=["POST"])
def owner_login():
    data = request.json
    cursor.execute("SELECT * FROM owners WHERE email=%s", (data["email"],))
    owner = cursor.fetchone()
    if owner and check_password_hash(owner["password"], data["password"]):
        return jsonify({"message": "Login successful", "owner_id": owner["id"]})
    return jsonify({"error": "Invalid credentials"}), 401


# Worker signup
@app.route("/api/worker/signup", methods=["POST"])
def worker_signup():
    data = request.json
    hashed_pw = generate_password_hash(data["password"])
    cursor.execute(
        "INSERT INTO workers (owner_id, name, email, password, bank_account, ifsc_code, base_salary) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (data["owner_id"], data["name"], data["email"], hashed_pw, data["bank_account"], data["ifsc"], data["base_salary"])
    )
    db.commit()
    return jsonify({"message": "Worker registered successfully!"})


# Worker login
@app.route("/api/worker/login", methods=["POST"])
def worker_login():
    data = request.json
    cursor.execute("SELECT * FROM workers WHERE email=%s", (data["email"],))
    worker = cursor.fetchone()
    if worker and check_password_hash(worker["password"], data["password"]):
        return jsonify({"message": "Login successful", "worker_id": worker["id"]})
    return jsonify({"error": "Invalid credentials"}), 401


# ---------------- BUSINESS LOGIC ROUTES ----------------
# Step 1: Owner enters revenue and expenses
@app.route("/api/revenue", methods=["POST"])
def add_revenue():
    data = request.json
    owner_id = data.get("owner_id")
    revenue = data.get("revenue", 0)
    expenses = data.get("expenses", 0)

    profit = revenue - expenses
    profit_margin = (profit / revenue) * 100 if revenue > 0 else 0

    cursor.execute("""
        INSERT INTO profits (owner_id, month, revenue, expenses, profit, profit_margin) 
        VALUES (%s, CURDATE(), %s, %s, %s, %s)
    """, (owner_id, revenue, expenses, profit, profit_margin))
    db.commit()

    return jsonify({"profit": profit, "profit_margin": profit_margin})


# Step 2: Calculate payouts (workers get bonus, expenses stay fixed)
@app.route("/api/pay", methods=["POST"])
def pay_employees():
    data = request.json
    owner_id = data.get("owner_id")

    # Get latest profit margin
    cursor.execute("SELECT profit_margin FROM profits WHERE owner_id=%s ORDER BY id DESC LIMIT 1", (owner_id,))
    result = cursor.fetchone()
    if not result:
        return jsonify({"error": "No profits found for this owner"}), 400

    profit_margin = result["profit_margin"]

    results = []

    # Handle workers
    cursor.execute("SELECT * FROM workers WHERE owner_id=%s", (owner_id,))
    workers = cursor.fetchall()

    for w in workers:
        bonus_percent = 0
        if profit_margin > 20:
            bonus_percent = 0.10
        elif profit_margin >= 10:
            bonus_percent = 0.05

        bonus_amount = float(w["base_salary"]) * bonus_percent
        final_amount = float(w["base_salary"]) + bonus_amount

        cursor.execute("""
            INSERT INTO payouts (owner_id, payee_id, base_amount, bonus_amount, final_amount) 
            VALUES (%s, %s, %s, %s, %s)
        """, (owner_id, w["id"], w["base_salary"], bonus_amount, final_amount))
        db.commit()

        results.append({
            "payee": w["name"],
            "type": "worker",
            "base": float(w["base_salary"]),
            "bonus": bonus_amount,
            "final": final_amount
        })

    # Handle fixed expenses
    cursor.execute("SELECT * FROM fixed_payees WHERE owner_id=%s", (owner_id,))
    expenses = cursor.fetchall()

    for e in expenses:
        cursor.execute("""
            INSERT INTO payouts (owner_id, payee_id, base_amount, bonus_amount, final_amount) 
            VALUES (%s, %s, %s, %s, %s)
        """, (owner_id, e["id"], e["fixed_amount"], 0, e["fixed_amount"]))
        db.commit()

        results.append({
            "payee": e["name"],
            "type": "expense",
            "base": float(e["fixed_amount"]),
            "bonus": 0,
            "final": float(e["fixed_amount"])
        })

    return jsonify(results)


# Step 3: Worker checks their receipts
@app.route("/api/receipts/<int:payee_id>", methods=["GET"])
def get_receipts(payee_id):
    cursor.execute("SELECT * FROM payouts WHERE payee_id=%s", (payee_id,))
    payouts = cursor.fetchall()
    return jsonify(payouts)


# ---------------- PROFIT GRAPH ----------------
@app.route("/api/owner/profits/<int:owner_id>", methods=["GET"])
def get_owner_profits(owner_id):
    cursor.execute("""
        SELECT DATE_FORMAT(month, '%Y-%m') AS month, 
               SUM(revenue) AS revenue, 
               SUM(expenses) AS expenses, 
               SUM(profit) AS profit
        FROM profits
        WHERE owner_id = %s
        GROUP BY DATE_FORMAT(month, '%Y-%m')
        ORDER BY month DESC
        LIMIT 3
    """, (owner_id,))
    data = cursor.fetchall()
    return jsonify(data)


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)



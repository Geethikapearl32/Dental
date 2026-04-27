from flask import Flask, render_template, request, redirect, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ================= LOGIN CONFIGURATION =================
import os
app.secret_key = os.environ.get("SECRET_KEY", "fallback_key")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, password, role):
        self.id = id
        self.username = username
        self.password = password
        self.role = role


@login_manager.user_loader
def load_user(user_id):
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    if user:
        return User(user['id'], user['username'], user['password'], user['role'])
    return None

# ================= CONFIGURATION =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "dental.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ================= DB CONNECTION =================
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row 
    return conn

# ================= INIT DATABASE =================
def init_db():
    conn = db()
    cur = conn.cursor()
    
    # USERS TABLE
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         username TEXT UNIQUE,
         password TEXT,
         role TEXT
    )
    """)

    # DEFAULT USERS
    cur.execute("INSERT OR IGNORE INTO users VALUES (1,'admin',?, 'admin')",
                 (generate_password_hash("1234"),))
    cur.execute("INSERT OR IGNORE INTO users VALUES (2,'staff',?, 'general')",
                 (generate_password_hash("1234"),)) 
   
    # Inventory Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        unit TEXT,
        quantity INTEGER DEFAULT 0,
        min_level INTEGER DEFAULT 5,
        notes TEXT
    )
    """)

    # Record daily or periodic doctor cuts
    cur.execute("""
    CREATE TABLE IF NOT EXISTS doctor_settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER,
        amount INTEGER,
        date TEXT,
        note TEXT
    )
    """)

    # Patients
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        patient_id TEXT PRIMARY KEY,
        name TEXT,
        age TEXT,
        gender TEXT,
        phone TEXT,
        place TEXT,
        date TEXT
    )
    """)

    # Doctors
    cur.execute("CREATE TABLE IF NOT EXISTS doctors (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    try:
        cur.execute("ALTER TABLE doctors ADD COLUMN specialization TEXT")
    except:
        pass

    # Appointments
    cur.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        patient_name TEXT,
        date TEXT,
        time TEXT,
        phone TEXT,
        status TEXT
    )
    """)

    # Treatments
    cur.execute("""
    CREATE TABLE IF NOT EXISTS treatments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        doctor_id TEXT,
        treatment TEXT,
        cost TEXT,
        paid TEXT,
        date TEXT,
        mode TEXT,
        attachment TEXT
    )
    """)

    # Payments
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        treatment_id INTEGER,
        amount TEXT,
        date TEXT,
        mode TEXT
    )
    """)

    # ✅ EXPENSES (IMPORTANT)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        amount INTEGER,
        date TEXT,
        mode TEXT
    )
    """)

    conn.commit()
    conn.close()
@app.route("/change_password")
def change_password():
    from werkzeug.security import generate_password_hash
    conn = db()
    cur = conn.cursor()

    # Change admin password
    cur.execute("UPDATE users SET password=? WHERE username=?",
                (generate_password_hash("Geethsm9295"), "admin"))

    # Change staff password
    cur.execute("UPDATE users SET password=? WHERE username=?",
                (generate_password_hash("Pearl9295"), "staff"))

    conn.commit()
    conn.close()

    return "Passwords updated successfully!"


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

@app.route("/expense_analysis")
def expense_analysis():
    conn = db()
    cur = conn.cursor()
    
    start = request.args.get('start_date') or datetime.now().strftime("%Y-01-01")
    end = request.args.get('end_date') or datetime.now().strftime("%Y-%m-%d")
    selected_type = request.args.get('type')  # 🔥 NEW

    # 🔥 Get all unique expense types for dropdown
    types_raw = cur.execute("SELECT DISTINCT type FROM expenses").fetchall()
    types = [t["type"] for t in types_raw]

    # 🔥 Main query
    query = """
        SELECT type, SUM(amount) AS total, COUNT(id) AS count 
        FROM expenses 
        WHERE date BETWEEN ? AND ?
    """
    
    params = [start, end]

    # 🔥 Filter by selected category
    if selected_type and selected_type != "All":
        query += " AND type = ?"
        params.append(selected_type)

    query += " GROUP BY type ORDER BY total DESC"

    rows_raw = cur.execute(query, params).fetchall()
    rows = [dict(r) for r in rows_raw]

    grand_total = sum(r['total'] for r in rows) if rows else 0

    conn.close()

    return render_template(
        "expense_analysis.html",
        rows=rows,
        start=start,
        end=end,
        total=grand_total,
        types=types,
        selected_type=selected_type
    )

# ================= EXPENSE ROUTES =================

@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    conn = db()
    cur = conn.cursor() # Defining 'cur' here prevents the NameError
    
    if request.method == "POST":
        etype = request.form.get("type")
        amount = request.form.get("amount")
        date = request.form.get("date")
        mode = request.form.get("mode")
        
        if etype and amount:
            cur.execute("INSERT INTO expenses (type, amount, date, mode) VALUES (?,?,?,?)",
                        (etype, amount, date, mode))
            conn.commit()
            conn.close()
            return redirect("/expenses")

    # Handle Date Filtering
    start = request.args.get("start_date")
    end = request.args.get("end_date")
    
    if start and end:
        rows_raw = cur.execute("SELECT * FROM expenses WHERE date BETWEEN ? AND ? ORDER BY date DESC", (start, end)).fetchall()
    else:
        rows_raw = cur.execute("SELECT * FROM expenses ORDER BY date DESC").fetchall()
    
    rows = [dict(r) for r in rows_raw]
    conn.close()
    return render_template("expenses.html", rows=rows, start_date=start, end_date=end)

@app.route("/delete_expense/<int:id>")
def delete_expense(id):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/expenses")
    
# ================= INVENTORY ROUTES =================

@@app.route("/inventory")
def inventory():
    return render_template("inventory.html", items=[], low_stock=[])
    conn = db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("item_name")
        unit = request.form.get("unit")
        qty = int(request.form.get("quantity") or 0)
        min_lvl = int(request.form.get("min_level") or 0)
        notes = request.form.get("notes")

        if name:
            cur.execute(
                "INSERT INTO inventory (item_name, unit, quantity, min_level, notes) VALUES (?,?,?,?,?)",
                (name, unit, qty, min_lvl, notes)
            )
            conn.commit()
            conn.close()
            return redirect("/inventory")

    rows_raw = cur.execute("SELECT * FROM inventory ORDER BY item_name ASC").fetchall()
    items = [dict(r) for r in rows_raw]

    # ✅ SAFE conversion (VERY IMPORTANT)
    for i in items:
        try:
            i['quantity'] = int(i['quantity']) if i['quantity'] else 0
            i['min_level'] = int(i['min_level']) if i['min_level'] else 0
        except:
            i['quantity'] = 0
            i['min_level'] = 0

    low_stock = [i for i in items if i['quantity'] <= i['min_level']]

    conn.close()
    return render_template("inventory.html", items=items, low_stock=low_stock)
@app.route("/update_stock/<int:id>", methods=["POST"])
def update_stock(id):
    new_qty = request.form.get("quantity")
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, id))
    conn.commit()
    conn.close()
    return redirect("/inventory")

@app.route("/delete_inventory/<int:id>")
def delete_inventory(id):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM inventory WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/inventory")
# Run Initialization
init_db()

# ================= DASHBOARD =================
@app.route("/")
@login_required
def dashboard():
    conn = db()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        p = cur.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        a = cur.execute("SELECT COUNT(*) FROM appointments WHERE date=?", (today,)).fetchone()[0]
        
        # Fixed Revenue calculation
        payments = cur.execute("SELECT amount FROM payments WHERE date=?", (today,)).fetchall()
        revenue = sum(int(x['amount']) for x in payments if str(x['amount']).isdigit())

        # NEW: Check for low stock items for Pearl32 inventory
        low_stock_count = cur.execute(
            "SELECT COUNT(*) FROM inventory WHERE CAST(quantity AS INTEGER) <= CAST(min_level AS INTEGER)"
        ).fetchone()[0]

    except Exception as e:
        print(f"Dashboard Error: {e}")
        p = a = revenue = 0
        low_stock_count = 0
    finally:
        conn.close()
    
    return render_template("dashboard.html", p=p, a=a, r=revenue, low_stock_alert=low_stock_count)

# ================= PATIENTS =================
@app.route("/patients", methods=["GET", "POST"])
def patients():
    conn = db()
    cur = conn.cursor()

    if request.method == "POST":
        pid = request.form.get("pid")
        name = request.form.get("name")
        reg_date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")

        if not name:
            return "Enter patient name", 400

        if not pid:
            last = cur.execute("SELECT patient_id FROM patients ORDER BY rowid DESC LIMIT 1").fetchone()
            if last and last[0].startswith('P'):
                try:
                    num = int(last[0].replace("P", "")) + 1
                except:
                    num = 1
            else:
                num = 1
            pid = f"P{num:03d}"

        cur.execute(
            "INSERT INTO patients (patient_id, name, age, gender, phone, place, date) VALUES (?,?,?,?,?,?,?)",
            (pid, name, request.form.get("age"), request.form.get("gender"), request.form.get("phone"), request.form.get("place"), reg_date)
        )
        conn.commit()
        conn.close()
        return redirect("/patients")

    rows_raw = cur.execute("SELECT * FROM patients ORDER BY rowid DESC").fetchall()
    rows = [dict(r) for r in rows_raw] 
    conn.close()
    return render_template("patients.html", rows=rows)

@app.route("/edit_patient", methods=["POST"])
def edit_patient():
    old_pid = request.form.get("old_pid")
    new_pid = request.form.get("pid")
    name = request.form.get("name")
    age = request.form.get("age")
    gender = request.form.get("gender")
    phone = request.form.get("phone")
    place = request.form.get("place")
    reg_date = request.form.get("date")

    conn = db()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE patients 
        SET patient_id=?, name=?, age=?, gender=?, phone=?, place=?, date=? 
        WHERE patient_id=?
    """, (new_pid, name, age, gender, phone, place, reg_date, old_pid))
    
    if old_pid != new_pid:
        cur.execute("UPDATE appointments SET patient_id=? WHERE patient_id=?", (new_pid, old_pid))
        cur.execute("UPDATE treatments SET patient_id=? WHERE patient_id=?", (new_pid, old_pid))
        
    conn.commit()
    conn.close()
    return redirect("/patients")

# ================= PATIENT HISTORY API =================
@app.route("/get_patient_history/<pid>")
def get_patient_history(pid):
    conn = db()
    cur = conn.cursor()
    
    history_raw = cur.execute("""
        SELECT t.date, d.name as doc_name, t.treatment, t.cost, t.paid 
        FROM treatments t
        LEFT JOIN doctors d ON t.doctor_id = d.id
        WHERE t.patient_id=? ORDER BY t.date DESC
    """, (pid,)).fetchall()
    history = [dict(row) for row in history_raw]

    summary = cur.execute("""
        SELECT 
            SUM(CASE WHEN cost = '' OR cost IS NULL THEN 0 ELSE CAST(cost AS INTEGER) END),
            SUM(CASE WHEN paid = '' OR paid IS NULL THEN 0 ELSE CAST(paid AS INTEGER) END)
        FROM treatments WHERE patient_id=?
    """, (pid,)).fetchone()

    total_cost = summary[0] if summary[0] else 0
    total_paid = summary[1] if summary[1] else 0
    balance = total_cost - total_paid

    doc_summary_raw = cur.execute("""
        SELECT 
            d.name as doc_name, 
            COUNT(*) as visit_count,
            SUM(CASE WHEN t.cost = '' OR t.cost IS NULL THEN 0 ELSE CAST(t.cost AS INTEGER) END) as total_val,
            SUM(CASE WHEN t.paid = '' OR t.paid IS NULL THEN 0 ELSE CAST(t.paid AS INTEGER) END) as total_paid
        FROM treatments t
        JOIN doctors d ON t.doctor_id = d.id
        WHERE t.patient_id=? 
        GROUP BY d.name
    """, (pid,)).fetchall()
    
    doc_summary = []
    for row in doc_summary_raw:
        d = dict(row)
        d['balance'] = d['total_val'] - d['total_paid']
        doc_summary.append(d)

    conn.close()
    return jsonify({
        "history": history,
        "total_cost": total_cost,
        "total_paid": total_paid,
        "balance": balance,
        "doc_summary": doc_summary
    })

# ================= UPLOAD =================
@app.route("/upload_document", methods=["POST"])
def upload_document():
    file = request.files.get('file')
    pid = request.form.get("pid")
    
    if file and pid:
        filename = secure_filename(f"PID_{pid}_{datetime.now().strftime('%H%M%S')}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        conn = db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE treatments SET attachment = ? 
            WHERE id = (SELECT MAX(id) FROM treatments WHERE patient_id = ?)
        """, (filename, pid))
        conn.commit()
        conn.close()
        
    return redirect("/patients")

# ================= DOCTORS =================
@app.route("/doctors", methods=["GET", "POST"])
def doctors():
    conn = db()
    cur = conn.cursor()
    
    if request.method == "POST":
        name = request.form.get("name")
        specialization = request.form.get("specialization")
        if name:
            cur.execute("INSERT INTO doctors (name, specialization) VALUES (?, ?)", (name, specialization))
            conn.commit()
            conn.close() 
            return redirect("/doctors")

    rows_raw = cur.execute("SELECT * FROM doctors").fetchall()
    rows = [dict(r) for r in rows_raw]
    conn.close()
    return render_template("doctors.html", rows=rows)

# ================= APPOINTMENTS (FIXED) =================
@app.route("/appointments", methods=["GET", "POST"])
def appointments():
    conn = db()
    cur = conn.cursor()
    patients_list = cur.execute("SELECT patient_id, name FROM patients").fetchall()
    doctors_list = cur.execute("SELECT id, name FROM doctors").fetchall()

    if request.method == "POST":
        # Capture the three dropdowns from the HTML form
        h = request.form.get("h12")
        m = request.form.get("m12")
        ap = request.form.get("ampm")
        
        # Combine them into a single string (e.g., "10:30 AM")
        time_str = f"{h}:{m} {ap}" if h and m else "Not Set"

        cur.execute("""
            INSERT INTO appointments (patient_id, patient_name, date, time, phone, status) 
            VALUES (?,?,?,?,?,?)""",
            (request.form.get("pid"), request.form.get("name"), request.form.get("date"), 
             time_str, request.form.get("phone"), request.form.get("status")))
        
        conn.commit()
        conn.close()
        return redirect("/appointments")

    # For display, we simply fetch the rows as they are saved
    rows_raw = cur.execute("SELECT * FROM appointments").fetchall()
    rows = []
    for r in rows_raw:
        # We use r['time'] directly because it is now saved in the correct format
        rows.append((r['id'], r['patient_id'], r['patient_name'], r['date'], r['time'], r['phone'], r['status']))
    
    conn.close()
    return render_template("appointments.html", rows=rows, doctors=doctors_list, patients=patients_list)

# ================= TREATMENTS =================
@app.route("/treatments", methods=["GET", "POST"])
def treatments():
    conn = db()
    cur = conn.cursor()
    doctors_list = cur.execute("SELECT id, name FROM doctors").fetchall()

    if request.method == "POST":
        doc_data = request.form.get("doctor")
        doc_id = doc_data.split(" - ")[0] if doc_data else ""
        cost = request.form.get("cost") or "0"
        paid = request.form.get("paid") or "0"
        date = request.form.get("date")
        mode = request.form.get("mode") or "cash"

        cur.execute("INSERT INTO treatments (patient_id, doctor_id, treatment, cost, paid, date, mode) VALUES (?,?,?,?,?,?,?)",
            (request.form.get("pid"), doc_id, request.form.get("desc"), cost, paid, date, mode))
        
        tid = cur.lastrowid
        if int(paid) > 0:
            cur.execute("INSERT INTO payments (treatment_id, amount, date, mode) VALUES (?,?,?,?)", (tid, paid, date, mode))
        conn.commit()
        conn.close()
        return redirect("/treatments")

    rows = cur.execute("""
        SELECT t.id, t.patient_id, p.name, p.gender, d.name as doc_name, t.treatment, t.cost, t.paid, t.mode, t.date
        FROM treatments t
        LEFT JOIN patients p ON t.patient_id = p.patient_id
        LEFT JOIN doctors d ON t.doctor_id = d.id
    """).fetchall()
    conn.close()
    return render_template("treatments.html", rows=rows, doctors=doctors_list)



# ================= BILLING (FIXED) =================

@app.route("/billing")
def billing():
    conn = db()
    cur = conn.cursor()
    
    search_date = request.args.get("search_date")
    
    # Query logic: Joining Payments -> Treatments -> Patients to get the Name
    query = """
        SELECT p.date, p.amount, p.mode, pat.name as patient_name
        FROM payments p
        JOIN treatments t ON p.treatment_id = t.id
        JOIN patients pat ON t.patient_id = pat.patient_id
    """
    
    if search_date:
        query += " WHERE p.date = ? ORDER BY p.date DESC"
        rows_raw = cur.execute(query, (search_date,)).fetchall()
    else:
        query += " ORDER BY p.date DESC"
        rows_raw = cur.execute(query).fetchall()
    
    rows = [dict(r) for r in rows_raw]

    # Helper function for financial sums
    def get_sum(table, date_filter=None, mode=None):
        sql = f"SELECT SUM(CAST(amount AS INTEGER)) FROM {table} WHERE 1=1"
        params = []
        if date_filter:
            sql += " AND date >= ?"
            params.append(date_filter)
        if mode:
            sql += " AND mode = ?"
            params.append(mode)
        res = cur.execute(sql, params).fetchone()[0]
        return res if res else 0

    # Calculate Summaries
    today_dt = datetime.now()
    week_ago = (today_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    month_start = today_dt.strftime("%Y-%m-01")

    stats = {
        "total_cash": get_sum("payments", mode="cash"),
        "total_online": get_sum("payments", mode="online"),
        "week_cash": get_sum("payments", week_ago, "cash"),
        "week_online": get_sum("payments", week_ago, "online"),
        "month_cash": get_sum("payments", month_start, "cash"),
        "month_online": get_sum("payments", month_start, "online"),
        "exp_cash": get_sum("expenses", mode="cash"),
        "exp_online": get_sum("expenses", mode="online")
    }
    
    stats["total_rev"] = stats["total_cash"] + stats["total_online"]
    stats["total_exp"] = stats["exp_cash"] + stats["exp_online"]
    stats["net_profit"] = stats["total_rev"] - stats["total_exp"]

    conn.close()
    return render_template("billing.html", rows=rows, s=stats, search_date=search_date)

@app.route("/income")
def income():
    conn = db()
    cur = conn.cursor()
    
    # 1. Calculate Revenue per doctor from treatments and payments
    revenue_rows = cur.execute("""
        SELECT d.id, d.name, d.specialization,
        SUM(CASE WHEN p.amount IS NOT NULL AND p.amount != '' THEN CAST(p.amount AS INTEGER) ELSE 0 END) as total_rev
        FROM doctors d
        LEFT JOIN treatments t ON d.id = t.doctor_id
        LEFT JOIN payments p ON t.id = p.treatment_id
        GROUP BY d.id
    """).fetchall()

    # 2. Calculate Settlements (Cuts) per doctor from the new table
    settlement_rows = cur.execute("""
        SELECT doctor_id, SUM(amount) as total_cut 
        FROM doctor_settlements GROUP BY doctor_id
    """).fetchall()
    
    cuts_map = {row['doctor_id']: row['total_cut'] for row in settlement_rows}
    
    processed_rows = []
    for rev in revenue_rows:
        d_id = rev['id']
        cut = cuts_map.get(d_id, 0)
        processed_rows.append({
            "name": rev['name'],
            "specialization": rev['specialization'],
            "revenue": rev['total_rev'],
            "cut": cut,
            "net": rev['total_rev'] - cut
        })

    doctors = cur.execute("SELECT id, name FROM doctors").fetchall()
    today_date = datetime.now().strftime("%Y-%m-%d")
    conn.close()
    return render_template("income.html", rows=processed_rows, doctors=doctors, today_date=today_date)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = db()
        cur = conn.cursor()
        user = cur.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            user_obj = User(user["id"], user["username"], user["password"], user["role"])
            login_user(user_obj)
            return redirect("/")
        else:
            return "Invalid username or password"

    return render_template("login.html")

# ================= ACTION ROUTES =================
@app.route("/delete_patient/<pid>", methods=["GET", "POST"])
@login_required
def delete_patient(pid):
    conn = db()
    cur = conn.cursor()
    try:
        # Delete patient and their treatment history to keep the DB clean
        cur.execute("DELETE FROM patients WHERE patient_id=?", (pid,))
        cur.execute("DELETE FROM treatments WHERE patient_id=?", (pid,))
        conn.commit()
        
        # If it's a standard link click, redirect back to the list
        if request.method == "GET":
            return redirect("/patients")
        # If it's a JavaScript fetch, return a success code
        return "Success", 200
    except Exception as e:
        print(f"Delete Error: {e}")
        return "Error", 500
    finally:
        conn.close()
@app.route("/delete_doctor/<int:id>")
def delete_doctor(id):
    conn = db(); cur = conn.cursor()
    cur.execute("DELETE FROM doctors WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect("/doctors")

@app.route("/delete_appointment/<int:id>")
def delete_appointment(id):
    conn = db(); cur = conn.cursor()
    cur.execute("DELETE FROM appointments WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect("/appointments")

@app.route("/cancel_appointment/<int:id>")
def cancel_appointment(id):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE appointments SET status='Cancelled' WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect("/appointments")

@app.route("/reschedule_appointment/<int:id>")
def reschedule_appointment(id):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE appointments SET status='Rescheduled' WHERE id=?", (id,))
    conn.commit(); conn.close()
    return redirect("/appointments")

@app.route("/delete_treatment/<int:id>")
def delete_treatment(id):
    conn = db()
    cur = conn.cursor()
    # Also delete associated payments to keep the balance correct
    cur.execute("DELETE FROM payments WHERE treatment_id=?", (id,))
    cur.execute("DELETE FROM treatments WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/treatments")

@app.route("/get_patient_full/<value>")
def get_patient_full(value):
    conn = db(); cur = conn.cursor()
    row = cur.execute("SELECT patient_id, name, age, gender, phone FROM patients WHERE patient_id=? OR name LIKE ? LIMIT 1", (value, f"%{value}%")).fetchone()
    conn.close()
    if row: return jsonify(dict(row))
    return jsonify({"id": "", "name": "", "age": "", "gender": "", "phone": ""})
@app.route("/add_settlement", methods=["POST"])
def add_settlement():
    conn = db()
    cur = conn.cursor()
    doc_id = request.form.get("doctor_id")
    amount = request.form.get("amount")
    date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
    note = request.form.get("note")

    if doc_id and amount:
        cur.execute("INSERT INTO doctor_settlements (doctor_id, amount, date, note) VALUES (?,?,?,?)",
                    (doc_id, amount, date, note))
        conn.commit()
    conn.close()
    return redirect("/income")


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
   

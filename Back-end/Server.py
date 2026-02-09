from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)  # allow frontend to call backend

# --- ALWAYS use the same DB file (no more .db.db mistakes) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "luxury_lanes.db")

def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- Create tables if they don't exist (stops "no such table" errors) ---
def init_db():
    conn = connect_db()
    c = conn.cursor()

    c.execute("PRAGMA foreign_keys = ON;")

    c.execute("""
    CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        surname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        role TEXT CHECK(role IN ('Guest','Staff','Manager','Subcontractor')) NOT NULL,
        password_hash TEXT NOT NULL,
        date_registered DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'Active'
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS Rooms (
        room_id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT UNIQUE NOT NULL,
        floor INTEGER,
        status TEXT DEFAULT 'Available'
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS MaintenanceRequests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        priority TEXT CHECK(priority IN ('High','Medium','Low')) NOT NULL,
        report_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT CHECK(status IN ('Reported','In Progress','Completed')) DEFAULT 'Reported',
        photo_url TEXT,
        FOREIGN KEY(room_id) REFERENCES Rooms(room_id),
        FOREIGN KEY(customer_id) REFERENCES Users(user_id)
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS Notifications (
        notice_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        request_id INTEGER,
        sent_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        delivery_method TEXT DEFAULT 'System',
        type TEXT,
        FOREIGN KEY(user_id) REFERENCES Users(user_id)
    );
    """)

    conn.commit()
    conn.close()

init_db()

# ---------- OPTIONAL: serve your html files (avoids file:// issues) ----------
@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "Login.html")

@app.route("/Register.html")
def register_page():
    return send_from_directory(BASE_DIR, "Register.html")

@app.route("/Dashboard.html")
def dash_page():
    return send_from_directory(BASE_DIR, "Dashboard.html")


# ---------- REGISTER ----------
@app.route("/register", methods=["POST"])
def register():
    data = request.json

    first_name = (data.get("first_name") or "").strip()
    surname = (data.get("surname") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    role = (data.get("role") or "").strip()

    if not first_name or not surname or not email or not password or not role:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    conn = connect_db()
    c = conn.cursor()

    try:
        c.execute("""
        INSERT INTO Users(first_name, surname, email, role, password_hash)
        VALUES (?,?,?,?,?)
        """, (first_name, surname, email, role, password))
        conn.commit()

        # find user id
        c.execute("SELECT user_id FROM Users WHERE email=?", (email,))
        user_id = c.fetchone()["user_id"]

        conn.close()
        return jsonify({"success": True, "user_id": user_id})

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "Email already exists"}), 409


# ---------- LOGIN ----------
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    conn = connect_db()
    c = conn.cursor()

    c.execute("""
    SELECT user_id, first_name, surname, role
    FROM Users
    WHERE email=? AND password_hash=?
    """, (email, password))

    user = c.fetchone()
    conn.close()

    if user:
        return jsonify({
            "success": True,
            "user_id": user["user_id"],
            "name": f"{user['first_name']} {user['surname']}",
            "role": user["role"]
        })
    else:
        return jsonify({"success": False})


# ---------- REPORT FAULT ----------
@app.route("/report-fault", methods=["POST"])
def report_fault():
    data = request.json

    room = (data.get("room") or "").strip()
    issue = (data.get("issue") or "").strip()
    description = (data.get("description") or "").strip()
    priority = (data.get("priority") or "").strip()
    user_id = data.get("user_id")

    if not room or not issue or not description or not priority or not user_id:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    conn = connect_db()
    c = conn.cursor()

    # room exists?
    c.execute("INSERT OR IGNORE INTO Rooms(room_number) VALUES (?)", (room,))
    c.execute("SELECT room_id FROM Rooms WHERE room_number=?", (room,))
    room_id = c.fetchone()["room_id"]

    # insert request
    c.execute("""
    INSERT INTO MaintenanceRequests(room_id, customer_id, title, description, priority)
    VALUES (?,?,?,?,?)
    """, (room_id, user_id, issue, description, priority))

    request_id = c.lastrowid

    # add a notification to the user (confirmation)
    c.execute("""
    INSERT INTO Notifications(user_id, request_id, type)
    VALUES (?,?,?)
    """, (user_id, request_id, "Fault logged successfully"))

    conn.commit()
    conn.close()

    return jsonify({"success": True})


# ---------- DASHBOARD DATA ----------
@app.route("/dashboard-data")
def dashboard_data():
    user_id = request.args.get("user_id", type=int)
    role = request.args.get("role", type=str)

    conn = connect_db()
    c = conn.cursor()

    # Guest sees only their own requests; others see everything (simple rule)
    if role == "Guest" and user_id:
        c.execute("SELECT COUNT(*) AS n FROM MaintenanceRequests WHERE customer_id=?", (user_id,))
        total = c.fetchone()["n"]

        c.execute("SELECT COUNT(*) AS n FROM MaintenanceRequests WHERE customer_id=? AND status!='Completed'", (user_id,))
        open_faults = c.fetchone()["n"]

        c.execute("SELECT COUNT(*) AS n FROM MaintenanceRequests WHERE customer_id=? AND status='Completed'", (user_id,))
        completed = c.fetchone()["n"]

        c.execute("""
        SELECT Rooms.room_number, title, priority, status
        FROM MaintenanceRequests
        JOIN Rooms ON MaintenanceRequests.room_id = Rooms.room_id
        WHERE customer_id=?
        ORDER BY report_time DESC
        LIMIT 6
        """, (user_id,))
    else:
        c.execute("SELECT COUNT(*) AS n FROM MaintenanceRequests")
        total = c.fetchone()["n"]

        c.execute("SELECT COUNT(*) AS n FROM MaintenanceRequests WHERE status!='Completed'")
        open_faults = c.fetchone()["n"]

        c.execute("SELECT COUNT(*) AS n FROM MaintenanceRequests WHERE status='Completed'")
        completed = c.fetchone()["n"]

        c.execute("""
        SELECT Rooms.room_number, title, priority, status
        FROM MaintenanceRequests
        JOIN Rooms ON MaintenanceRequests.room_id = Rooms.room_id
        ORDER BY report_time DESC
        LIMIT 6
        """)

    recent_rows = c.fetchall()
    recent = []
    for r in recent_rows:
        recent.append({
            "room": r["room_number"],
            "issue": r["title"],
            "priority": r["priority"],
            "status": r["status"]
        })

    conn.close()

    return jsonify({
        "db_used": DB_PATH,
        "total": total,
        "open": open_faults,
        "completed": completed,
        "recent": recent
    })


# ---------- NOTIFICATIONS ----------
@app.route("/notifications")
def notifications():
    user_id = request.args.get("user_id", type=int)

    conn = connect_db()
    c = conn.cursor()

    if user_id:
        c.execute("""
        SELECT type, sent_time
        FROM Notifications
        WHERE user_id=?
        ORDER BY sent_time DESC
        LIMIT 20
        """, (user_id,))
    else:
        c.execute("""
        SELECT type, sent_time
        FROM Notifications
        ORDER BY sent_time DESC
        LIMIT 20
        """)

    rows = c.fetchall()
    conn.close()

    return jsonify([{"type": r["type"], "time": r["sent_time"]} for r in rows])


# IMPORTANT: ALWAYS LAST
if __name__ == "__main__":
    print("Using DB:", DB_PATH)
    app.run(debug=True)

from flask import Flask, request, jsonify, session
from flask_cors import CORS
import sqlite3
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = "luxury_lanes_secret_2024"
CORS(app, supports_credentials=True, origins=[
    "null",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:5000",
    "http://localhost:5000"
])

DB_PATH = "luxury_lanes.db"


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password):
    salt   = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed + ":" + salt


def check_password(password, stored):
    parts = stored.split(":")
    if len(parts) != 2:
        # Legacy plain hash (sha256 with no salt) — used by old all-in-one app
        return stored == hashlib.sha256(password.encode()).hexdigest()
    hashed = hashlib.sha256((password + parts[1]).encode()).hexdigest()
    return hashed == parts[0]


def notify(user_id, request_id, message, ntype="Update"):
    conn = connect_db()
    conn.execute(
        "INSERT INTO Notifications(user_id, request_id, message, type) VALUES(?,?,?,?)",
        (user_id, request_id, message, ntype)
    )
    conn.commit()
    conn.close()


def audit(user_id, action, details=""):
    conn = connect_db()
    conn.execute(
        "INSERT INTO AuditLog(user_id, action, details) VALUES(?,?,?)",
        (user_id, action, details)
    )
    conn.commit()
    conn.close()


def init_db():
    conn = connect_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS Users (
        user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name    TEXT NOT NULL,
        surname       TEXT NOT NULL,
        email         TEXT UNIQUE NOT NULL,
        role          TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS Rooms (
        room_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT UNIQUE NOT NULL,
        floor       INTEGER DEFAULT 1,
        status      TEXT DEFAULT 'Available'
    )""")

    # requests uses room TEXT (room number directly) and NOT a FK to Rooms
    c.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        room        TEXT NOT NULL,
        title       TEXT NOT NULL,
        description TEXT NOT NULL,
        priority    TEXT NOT NULL,
        status      TEXT DEFAULT 'Reported',
        user_id     INTEGER,
        assigned_to INTEGER,
        report_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id)     REFERENCES Users(user_id),
        FOREIGN KEY(assigned_to) REFERENCES Users(user_id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS Feedback (
        feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id  INTEGER,
        user_id     INTEGER,
        rating      INTEGER CHECK(rating BETWEEN 1 AND 5),
        comments    TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(request_id) REFERENCES requests(id),
        FOREIGN KEY(user_id)    REFERENCES Users(user_id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS Notifications (
        notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER,
        request_id      INTEGER,
        message         TEXT NOT NULL,
        type            TEXT DEFAULT 'Update',
        is_read         INTEGER DEFAULT 0,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id)    REFERENCES Users(user_id),
        FOREIGN KEY(request_id) REFERENCES requests(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS PerformanceAnalytics (
        analytics_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             INTEGER UNIQUE,
        total_requests      INTEGER DEFAULT 0,
        completed_requests  INTEGER DEFAULT 0,
        avg_completion_time REAL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES Users(user_id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS RoomStatus (
        room_status_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id             INTEGER UNIQUE,
        total_issues        INTEGER DEFAULT 0,
        last_reported_issue DATETIME,
        FOREIGN KEY(room_id) REFERENCES Rooms(room_id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS AuditLog (
        log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER,
        action        TEXT NOT NULL,
        details       TEXT,
        time_recorded DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES Users(user_id)
    )""")

    # Seed rooms 101–130 if empty
    if conn.execute("SELECT COUNT(*) FROM Rooms").fetchone()[0] == 0:
        rooms = []
        for i in range(1, 31):
            floor = ((i - 1) // 10) + 1
            rooms.append((str(100 + i), floor))
        c.executemany("INSERT INTO Rooms(room_number, floor) VALUES(?,?)", rooms)

    # Seed a default manager account if no users exist
    if conn.execute("SELECT COUNT(*) FROM Users").fetchone()[0] == 0:
        pw = hash_password("manager123")
        c.execute(
            "INSERT INTO Users(first_name, surname, email, role, password_hash) VALUES(?,?,?,?,?)",
            ("Hotel", "Manager", "manager@luxurylanes.com", "Manager", pw)
        )
        print("\n  Default manager account created:")
        print("  Email:    manager@luxurylanes.com")
        print("  Password: manager123\n")

    conn.commit()
    conn.close()


init_db()


# ──────────────────────────────────────────────
#  AUTH
# ──────────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    d          = request.json
    first_name = d.get("first_name", "").strip()
    surname    = d.get("surname",    "").strip()
    email      = d.get("email",      "").strip().lower()
    role       = d.get("role",       "").strip()
    password   = d.get("password",   "")

    if not all([first_name, surname, email, role, password]):
        return jsonify({"success": False, "message": "All fields are required."}), 400

    if role not in ("Guest", "Staff", "Manager", "Subcontractor"):
        return jsonify({"success": False, "message": "Invalid role selected."}), 400

    conn = connect_db()
    try:
        conn.execute(
            "INSERT INTO Users(first_name, surname, email, role, password_hash) VALUES(?,?,?,?,?)",
            (first_name, surname, email, role, hash_password(password))
        )
        conn.commit()
        user = conn.execute("SELECT user_id FROM Users WHERE email=?", (email,)).fetchone()
        return jsonify({
            "success": True,
            "user_id": user["user_id"],
            "name":    first_name + " " + surname,
            "role":    role
        })
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "An account with that email already exists."}), 409
    finally:
        conn.close()


@app.route("/login", methods=["POST"])
def login():
    d        = request.json
    email    = d.get("email",    "").strip().lower()
    password = d.get("password", "")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    conn = connect_db()
    user = conn.execute("SELECT * FROM Users WHERE email=?", (email,)).fetchone()
    conn.close()

    if not user or not check_password(password, user["password_hash"]):
        return jsonify({"success": False, "message": "Incorrect email or password."}), 401

    session["user_id"] = user["user_id"]
    session["role"]    = user["role"]
    audit(user["user_id"], "LOGIN", f"{email} logged in")

    return jsonify({
        "success":    True,
        "user_id":    user["user_id"],
        "first_name": user["first_name"],
        "surname":    user["surname"],
        "name":       user["first_name"] + " " + user["surname"],
        "email":      user["email"],
        "role":       user["role"]
    })


@app.route("/logout", methods=["POST"])
def logout():
    uid = session.get("user_id")
    session.clear()
    if uid:
        audit(uid, "LOGOUT")
    return jsonify({"success": True})


@app.route("/me", methods=["GET"])
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    user = conn.execute(
        "SELECT user_id, first_name, surname, email, role FROM Users WHERE user_id=?", (uid,)
    ).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "User not found"}), 404
    row       = dict(user)
    row["name"] = row["first_name"] + " " + row["surname"]
    return jsonify(row)


# ──────────────────────────────────────────────
#  ROOMS
# ──────────────────────────────────────────────

@app.route("/rooms", methods=["GET"])
def get_rooms():
    conn  = connect_db()
    rooms = conn.execute(
        "SELECT * FROM Rooms ORDER BY CAST(room_number AS INTEGER)"
    ).fetchall()
    conn.close()
    return jsonify({"rooms": [dict(r) for r in rooms]})


@app.route("/rooms/search", methods=["GET"])
def search_rooms():
    q    = request.args.get("q", "").strip()
    conn = connect_db()
    rows = conn.execute(
        "SELECT * FROM Rooms WHERE room_number LIKE ? ORDER BY CAST(room_number AS INTEGER) LIMIT 10",
        (f"%{q}%",)
    ).fetchall()
    conn.close()
    return jsonify({"rooms": [dict(r) for r in rows]})


@app.route("/rooms", methods=["POST"])
def add_room():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    role = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()["role"]
    if role != "Manager":
        conn.close()
        return jsonify({"error": "Manager access required"}), 403
    d  = request.json
    rn = d.get("room_number", "").strip()
    fl = d.get("floor", 1)
    if not rn:
        conn.close()
        return jsonify({"error": "Room number is required"}), 400
    try:
        conn.execute("INSERT INTO Rooms(room_number, floor) VALUES(?,?)", (rn, fl))
        conn.commit()
        return jsonify({"success": True}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Room number already exists"}), 409
    finally:
        conn.close()


@app.route("/rooms/<int:rid>", methods=["PUT"])
def update_room(rid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    role = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()["role"]
    if role != "Manager":
        conn.close()
        return jsonify({"error": "Manager access required"}), 403
    st = request.json.get("status", "").strip()
    if st not in ("Available", "Occupied", "Maintenance"):
        conn.close()
        return jsonify({"error": "Invalid status"}), 400
    conn.execute("UPDATE Rooms SET status=? WHERE room_id=?", (st, rid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/rooms/<int:rid>", methods=["DELETE"])
def delete_room(rid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    role = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()["role"]
    if role != "Manager":
        conn.close()
        return jsonify({"error": "Manager access required"}), 403
    conn.execute("DELETE FROM Rooms WHERE room_id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────
#  FAULT REPORTING  (Guests AND Staff can submit)
# ──────────────────────────────────────────────

@app.route("/report-fault", methods=["POST"])
def report_fault():
    d   = request.json
    uid = session.get("user_id") or d.get("user_id")
    if not uid:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    # Accept room number (text) directly — no FK to Rooms needed
    room        = str(d.get("room", d.get("room_number", ""))).strip()
    title       = d.get("title",       "").strip()
    description = d.get("description", "").strip()
    priority    = d.get("priority",    "").strip()

    if not all([room, title, description, priority]):
        return jsonify({"success": False, "message": "All fields are required."}), 400

    if priority not in ("High", "Medium", "Low"):
        return jsonify({"success": False, "message": "Invalid priority."}), 400

    conn = connect_db()
    # Make sure the room exists in the Rooms table (insert if not)
    conn.execute("INSERT OR IGNORE INTO Rooms(room_number) VALUES(?)", (room,))
    conn.commit()

    conn.execute(
        "INSERT INTO requests(room, title, description, priority, user_id, status) VALUES(?,?,?,?,?,'Reported')",
        (room, title, description, priority, uid)
    )
    conn.commit()
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Update RoomStatus
    room_row = conn.execute("SELECT room_id FROM Rooms WHERE room_number=?", (room,)).fetchone()
    if room_row:
        existing = conn.execute(
            "SELECT room_status_id FROM RoomStatus WHERE room_id=?", (room_row["room_id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE RoomStatus SET total_issues=total_issues+1, last_reported_issue=CURRENT_TIMESTAMP WHERE room_id=?",
                (room_row["room_id"],)
            )
        else:
            conn.execute(
                "INSERT INTO RoomStatus(room_id, total_issues, last_reported_issue) VALUES(?,1,CURRENT_TIMESTAMP)",
                (room_row["room_id"],)
            )
        conn.commit()

    # Notify reporter
    notify(uid, req_id, f"Your fault report for Room {room} has been received. Reference: #{req_id}", "Confirmation")

    # Notify all managers of high-priority faults
    if priority == "High":
        managers = conn.execute("SELECT user_id FROM Users WHERE role='Manager'").fetchall()
        for m in managers:
            notify(m["user_id"], req_id, f"High priority fault in Room {room}: {title}", "New Request")

    conn.close()
    audit(uid, "SUBMIT_FAULT", f"Room {room} - {title} ({priority})")
    return jsonify({"success": True, "request_id": req_id})


# ──────────────────────────────────────────────
#  REQUESTS
# ──────────────────────────────────────────────

@app.route("/requests", methods=["GET"])
def get_requests():
    uid = session.get("user_id")
    if not uid:
        uid = request.args.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401

    conn = connect_db()
    role_row = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()
    if not role_row:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    role = role_row["role"]

    if role == "Manager":
        rows = conn.execute("""
            SELECT req.*,
                   u.first_name||' '||u.surname AS reporter_name,
                   a.first_name||' '||a.surname AS assigned_name
            FROM requests req
            LEFT JOIN Users u ON u.user_id = req.user_id
            LEFT JOIN Users a ON a.user_id = req.assigned_to
            ORDER BY req.id DESC
        """).fetchall()
    elif role in ("Staff", "Subcontractor"):
        rows = conn.execute("""
            SELECT req.*,
                   u.first_name||' '||u.surname AS reporter_name,
                   a.first_name||' '||a.surname AS assigned_name
            FROM requests req
            LEFT JOIN Users u ON u.user_id = req.user_id
            LEFT JOIN Users a ON a.user_id = req.assigned_to
            WHERE req.assigned_to=? OR req.status='Reported'
            ORDER BY req.id DESC
        """, (uid,)).fetchall()
    else:
        # Guest — own requests only
        rows = conn.execute("""
            SELECT req.*,
                   u.first_name||' '||u.surname AS reporter_name,
                   a.first_name||' '||a.surname AS assigned_name
            FROM requests req
            LEFT JOIN Users u ON u.user_id = req.user_id
            LEFT JOIN Users a ON a.user_id = req.assigned_to
            WHERE req.user_id=?
            ORDER BY req.id DESC
        """, (uid,)).fetchall()

    conn.close()
    result = []
    for r in rows:
        row = dict(r)
        row["request_id"]  = row["id"]
        row["room_number"] = row["room"]
        result.append(row)
    return jsonify(result)


# ──────────────────────────────────────────────
#  ASSIGN  (Manager AND Staff only)
# ──────────────────────────────────────────────

@app.route("/requests/<int:rid>/assign", methods=["PUT"])
def assign_request(rid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    role = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()["role"]
    if role not in ("Manager", "Staff"):
        conn.close()
        return jsonify({"error": "Manager or Staff access required"}), 403

    assigned_to = request.json.get("assigned_to")
    if not assigned_to:
        conn.close()
        return jsonify({"error": "Please select a person to assign to"}), 400

    conn.execute(
        "UPDATE requests SET assigned_to=?, status='In Progress' WHERE id=?",
        (assigned_to, rid)
    )
    conn.commit()

    req = conn.execute("SELECT title, room, user_id FROM requests WHERE id=?", (rid,)).fetchone()
    if req:
        notify(assigned_to, rid, f"You have been assigned: '{req['title']}' in Room {req['room']}.", "Assignment")
        notify(req["user_id"], rid, f"Your request for Room {req['room']} is now In Progress.", "Update")

    conn.close()
    audit(uid, "ASSIGN", f"Request #{rid} assigned to user {assigned_to}")
    return jsonify({"success": True})


# ──────────────────────────────────────────────
#  STATUS UPDATE  (Staff and Subcontractor)
# ──────────────────────────────────────────────

@app.route("/requests/<int:rid>/status", methods=["PUT"])
def update_status(rid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401

    new_status = request.json.get("status", "").strip()
    if new_status not in ("In Progress", "Completed"):
        return jsonify({"error": "Invalid status. Use 'In Progress' or 'Completed'."}), 400

    conn = connect_db()
    conn.execute("UPDATE requests SET status=? WHERE id=?", (new_status, rid))
    conn.commit()

    if new_status == "Completed":
        req = conn.execute(
            "SELECT title, room, user_id FROM requests WHERE id=?", (rid,)
        ).fetchone()
        if req:
            notify(req["user_id"], rid,
                   f"Your maintenance request for Room {req['room']} ({req['title']}) has been completed.",
                   "Completed")
            # Mark room as Available again
            room_row = conn.execute(
                "SELECT room_id FROM Rooms WHERE room_number=?", (req["room"],)
            ).fetchone()
            if room_row:
                conn.execute(
                    "UPDATE Rooms SET status='Available' WHERE room_id=?", (room_row["room_id"],)
                )
                conn.commit()

    conn.close()
    audit(uid, "UPDATE_STATUS", f"Request #{rid} set to {new_status}")
    return jsonify({"success": True})


# ──────────────────────────────────────────────
#  STAFF / SUBCONTRACTOR LIST  (for assign dropdowns)
# ──────────────────────────────────────────────

@app.route("/staff", methods=["GET"])
def get_staff():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn   = connect_db()
    role   = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()["role"]
    if role not in ("Manager", "Staff"):
        conn.close()
        return jsonify({"error": "Access denied"}), 403
    rows = conn.execute(
        "SELECT user_id, first_name, surname, role FROM Users WHERE role IN ('Staff','Subcontractor') ORDER BY role, first_name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ──────────────────────────────────────────────
#  FEEDBACK
# ──────────────────────────────────────────────

@app.route("/feedback", methods=["POST"])
def submit_feedback():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    d          = request.json
    request_id = d.get("request_id")
    rating     = d.get("rating")
    comments   = d.get("comments", "").strip()

    if not request_id or not rating:
        return jsonify({"error": "Request and rating are required"}), 400
    if not (1 <= int(rating) <= 5):
        return jsonify({"error": "Rating must be between 1 and 5"}), 400

    conn = connect_db()
    req  = conn.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
    if not req or req["status"] != "Completed":
        conn.close()
        return jsonify({"error": "Feedback can only be submitted for completed requests"}), 400

    existing = conn.execute(
        "SELECT feedback_id FROM Feedback WHERE request_id=? AND user_id=?", (request_id, uid)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "You have already submitted feedback for this request"}), 409

    conn.execute(
        "INSERT INTO Feedback(request_id, user_id, rating, comments) VALUES(?,?,?,?)",
        (request_id, uid, rating, comments)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True}), 201


@app.route("/feedback", methods=["GET"])
def get_feedback():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    role = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()["role"]

    if role in ("Manager", "Staff"):
        rows = conn.execute("""
            SELECT f.*, u.first_name||' '||u.surname AS guest_name,
                   req.title, req.room AS room_number
            FROM Feedback f
            JOIN Users    u   ON u.user_id   = f.user_id
            JOIN requests req ON req.id       = f.request_id
            ORDER BY f.created_at DESC
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT f.*, req.title, req.room AS room_number
            FROM Feedback f
            JOIN requests req ON req.id = f.request_id
            WHERE f.user_id=?
            ORDER BY f.created_at DESC
        """, (uid,)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


# ──────────────────────────────────────────────
#  NOTIFICATIONS
# ──────────────────────────────────────────────

@app.route("/notifications", methods=["GET"])
def get_notifications():
    uid = session.get("user_id")
    if not uid:
        uid = request.args.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    rows = conn.execute(
        "SELECT * FROM Notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 30",
        (uid,)
    ).fetchall()
    conn.close()
    return jsonify({"notifications": [dict(r) for r in rows]})


@app.route("/notifications/read", methods=["PUT"])
def mark_read():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    conn.execute("UPDATE Notifications SET is_read=1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────
#  ANALYTICS  (Manager only)
# ──────────────────────────────────────────────

@app.route("/analytics", methods=["GET"])
def analytics():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Not logged in"}), 401
    conn = connect_db()
    role = conn.execute("SELECT role FROM Users WHERE user_id=?", (uid,)).fetchone()["role"]
    if role != "Manager":
        conn.close()
        return jsonify({"error": "Manager access required"}), 403

    total     = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    reported  = conn.execute("SELECT COUNT(*) FROM requests WHERE status='Reported'").fetchone()[0]
    in_prog   = conn.execute("SELECT COUNT(*) FROM requests WHERE status='In Progress'").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM requests WHERE status='Completed'").fetchone()[0]
    high      = conn.execute("SELECT COUNT(*) FROM requests WHERE priority='High'").fetchone()[0]
    medium    = conn.execute("SELECT COUNT(*) FROM requests WHERE priority='Medium'").fetchone()[0]
    low       = conn.execute("SELECT COUNT(*) FROM requests WHERE priority='Low'").fetchone()[0]

    avg_row    = conn.execute("SELECT ROUND(AVG(rating),1) AS avg_r FROM Feedback").fetchone()
    avg_rating = avg_row["avg_r"] if avg_row["avg_r"] else None

    top_rooms = conn.execute("""
        SELECT room AS room_number, COUNT(*) AS issue_count
        FROM requests
        GROUP BY room
        ORDER BY issue_count DESC
        LIMIT 5
    """).fetchall()

    unresolved = conn.execute("""
        SELECT id AS request_id, room AS room_number, title, priority, status, report_time
        FROM requests
        WHERE status != 'Completed'
        ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, report_time ASC
        LIMIT 10
    """).fetchall()

    monthly = conn.execute("""
        SELECT strftime('%Y-%m', report_time) AS month, COUNT(*) AS count
        FROM requests
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6
    """).fetchall()

    staff_perf = conn.execute("""
        SELECT u.user_id, u.first_name||' '||u.surname AS name, u.role,
               COUNT(r.id) AS total,
               SUM(CASE WHEN r.status='Completed'   THEN 1 ELSE 0 END) AS done,
               SUM(CASE WHEN r.status='In Progress' THEN 1 ELSE 0 END) AS active
        FROM Users u
        LEFT JOIN requests r ON r.assigned_to = u.user_id
        WHERE u.role IN ('Staff','Subcontractor')
        GROUP BY u.user_id
        ORDER BY done DESC
    """).fetchall()

    avg_feedback = conn.execute("""
        SELECT u.first_name||' '||u.surname AS name,
               ROUND(AVG(f.rating),1)       AS avg_rating,
               COUNT(*)                     AS review_count
        FROM Feedback f
        JOIN requests req ON req.id       = f.request_id
        JOIN Users    u   ON u.user_id    = req.assigned_to
        WHERE req.assigned_to IS NOT NULL
        GROUP BY req.assigned_to
    """).fetchall()

    conn.close()
    return jsonify({
        "total":             total,
        "reported":          reported,
        "in_progress":       in_prog,
        "completed":         completed,
        "high":              high,
        "medium":            medium,
        "low":               low,
        "avg_rating":        avg_rating,
        "top_rooms":         [dict(r) for r in top_rooms],
        "unresolved":        [dict(r) for r in unresolved],
        "monthly":           [dict(r) for r in monthly],
        "staff_performance": [dict(r) for r in staff_perf],
        "avg_feedback":      [dict(r) for r in avg_feedback]
    })


if __name__ == "__main__":
    print("\n  Luxury Lanes server starting...")
    print("  Open your browser and use Live Server (port 5500)")
    print("  or open the HTML files directly.\n")
    app.run(debug=True, port=5000)
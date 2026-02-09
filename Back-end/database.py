from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

DB_NAME = "Luxury Lanes.db"

# ------------------------
# CONNECT TO DATABASE
# ------------------------

def connect_db():
    return sqlite3.connect(DB_NAME)

# ------------------------
# LOGIN
# ------------------------

@app.route("/login", methods=["POST"])
def login():
    data = request.json

    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT * FROM Users 
        WHERE email=? AND password_hash=?
    """, (data["email"], data["password"]))

    user = cursor.fetchone()
    db.close()

    if user:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False})


# ------------------------
# REGISTER USER
# ------------------------

@app.route("/register", methods=["POST"])
def register():
    data = request.json

    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO Users (first_name, surname, email, role, password_hash)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data["first_name"],
        data["surname"],
        data["email"],
        data["role"],
        data["password"]
    ))

    db.commit()
    db.close()

    return jsonify({"message": "User registered"})


# ------------------------
# REPORT FAULT
# ------------------------

@app.route("/report", methods=["POST"])
def report_fault():
    data = request.json

    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO MaintenanceRequests
        (room_id, customer_id, title, description, priority, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data["room"],
        data["user"],
        data["title"],
        data["description"],
        data["priority"],
        "Reported"
    ))

    db.commit()
    db.close()

    return jsonify({"message": "Fault reported"})


# ------------------------
# VIEW ALL REQUESTS (MANAGER)
# ------------------------

@app.route("/requests", methods=["GET"])
def view_requests():
    db = connect_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM MaintenanceRequests")
    rows = cursor.fetchall()

    db.close()

    return jsonify(rows)


# ------------------------
# ASSIGN JOB
# ------------------------

@app.route("/assign", methods=["POST"])
def assign_job():
    data = request.json

    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO JobAssignments
        (request_id, assigned_to)
        VALUES (?, ?)
    """, (
        data["request_id"],
        data["staff_id"]
    ))

    db.commit()
    db.close()

    return jsonify({"message": "Job assigned"})


# ------------------------
# UPDATE STATUS
# ------------------------

@app.route("/update_status", methods=["POST"])
def update_status():
    data = request.json

    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE MaintenanceRequests
        SET status=?
        WHERE request_id=?
    """, (
        data["status"],
        data["request_id"]
    ))

    db.commit()
    db.close()

    return jsonify({"message": "Status updated"})


# ------------------------
# SIMPLE ANALYTICS
# ------------------------

@app.route("/analytics", methods=["GET"])
def analytics():
    db = connect_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) FROM MaintenanceRequests")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM MaintenanceRequests 
        WHERE status='Completed'
    """)
    completed = cursor.fetchone()[0]

    db.close()

    return jsonify({
        "total_requests": total,
        "completed_requests": completed
    })


# ------------------------
# RUN SERVER
# ------------------------

if __name__ == "__main__":
    app.run(debug=True)

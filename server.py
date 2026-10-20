from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
import joblib
import os
import sqlite3
import pandas as pd
import json
from datetime import datetime, timezone
from uuid import uuid4
from werkzeug.utils import secure_filename

try:
    import pymysql
except ImportError:
    pymysql = None

SUBJECTS = [
    {"key": "ai", "name": "AI", "internal_col": "AI Total Internal", "hours_col": "AI Study Hours/Week"},
    {"key": "ml", "name": "Machine Learning", "internal_col": "Machine Learning Total Internal", "hours_col": "Machine Learning Study Hours/Week"},
    {"key": "cn", "name": "Computer Networks", "internal_col": "Computer Networks Total Internal", "hours_col": "Computer Networks Study Hours/Week"},
    {"key": "cd", "name": "Compiler Design", "internal_col": "Compiler Design Total Internal", "hours_col": "Compiler Design Study Hours/Week"},
    {"key": "web", "name": "Web Technology", "internal_col": "Web Technology Total Internal", "hours_col": "Web Technology Study Hours/Week"},
    {"key": "mp", "name": "Mini Project", "internal_col": "Mini Project Total Internal", "hours_col": "Mini Project Study Hours/Week"},
]
SUBJECT_KEYS = [s["key"] for s in SUBJECTS]

app = Flask(__name__, static_folder=".")
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
STUDENT_PROFILES_FILE = os.path.join(BASE_DIR, "student_profiles.json")
ALLOWED_CERTIFICATE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-local-placement-secret")
ADMIN_USERNAME = os.environ.get("PLACEMENT_ADMIN_USERNAME", "placementadmin")
ADMIN_PASSWORD = os.environ.get("PLACEMENT_ADMIN_PASSWORD", "Sahrdaya@2026")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Database config ---
# Locally: SQLite file (placement.db) — no install needed.
# On AWS:  set DB_HOST env var to use RDS MySQL instead.
SQLITE_DB = os.path.join(BASE_DIR, "placement.db")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "studentdb")
DEPARTMENT_MAP = {"CE": 0, "CSE": 1, "ECE": 2, "EEE": 3, "IT": 4, "ME": 5}
INTERNSHIP_MAP = {"No": 0, "Yes": 1}


def load_model(filename):
    """Model files are optional so the UI remains runnable during development."""
    try:
        return joblib.load(os.path.join(BASE_DIR, filename))
    except Exception as error:
        print(f"Could not load {filename}; using local estimate ({error}).")
        return None


# ---------------------------------------------------------------------------
# SQLite helpers (local)
# ---------------------------------------------------------------------------

def get_sqlite():
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_sqlite_schema():
    with get_sqlite() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                register_number TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                software        TEXT DEFAULT '[]',
                hardware        TEXT DEFAULT '[]',
                certificates    TEXT DEFAULT '[]',
                certificate_files TEXT DEFAULT '[]',
                applied_company TEXT DEFAULT '',
                cgpa            REAL,
                updated_at      TEXT
            )
            """
        )
        conn.commit()


def migrate_json_to_sqlite():
    """One-time import of student_profiles.json into SQLite on first run."""
    try:
        with open(STUDENT_PROFILES_FILE, encoding="utf-8-sig") as f:
            profiles = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not profiles:
        return
    with get_sqlite() as conn:
        existing = {row[0] for row in conn.execute("SELECT register_number FROM students")}
        rows = [
            (
                p["registerNumber"], p["name"],
                json.dumps(p.get("software", [])),
                json.dumps(p.get("hardware", [])),
                json.dumps(p.get("certificates", [])),
                json.dumps(p.get("certificateFiles", [])),
                p.get("appliedCompany", ""),
                p.get("cgpa"),
                p.get("updatedAt"),
            )
            for p in profiles.values()
            if p.get("registerNumber") and p["registerNumber"] not in existing
        ]
        if rows:
            conn.executemany(
                "INSERT OR IGNORE INTO students VALUES (?,?,?,?,?,?,?,?,?)", rows
            )
            conn.commit()
            print(f"Migrated {len(rows)} records from student_profiles.json -> placement.db")


# ---------------------------------------------------------------------------
# RDS (MySQL) helpers — only used on AWS when DB_HOST env var is set
# ---------------------------------------------------------------------------

def rds_enabled():
    return bool(DB_HOST and DB_PASSWORD and pymysql is not None)


def get_rds():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4", connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
    )


def ensure_rds_schema():
    if not rds_enabled():
        return False
    try:
        with get_rds() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS students (
                        register_number VARCHAR(30) PRIMARY KEY,
                        name            VARCHAR(100) NOT NULL,
                        software        TEXT,
                        hardware        TEXT,
                        certificates    TEXT,
                        certificate_files TEXT,
                        applied_company VARCHAR(150),
                        cgpa            DECIMAL(4,2),
                        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP
                    )
                    """
                )
        return True
    except Exception as e:
        print(f"RDS schema setup failed ({e}); using SQLite.")
        return False


# ---------------------------------------------------------------------------
# Unified profile CRUD — RDS on AWS, SQLite locally
# ---------------------------------------------------------------------------

def to_list(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []


def _row_to_profile(row):
    return {
        "registerNumber": row["register_number"],
        "name": row["name"],
        "software": to_list(row["software"]),
        "hardware": to_list(row["hardware"]),
        "certificates": to_list(row["certificates"]),
        "certificateFiles": to_list(row["certificate_files"]),
        "appliedCompany": row["applied_company"] or "",
        "cgpa": float(row["cgpa"]) if row["cgpa"] is not None else None,
        "updatedAt": str(row["updated_at"]) if row["updated_at"] else None,
    }


def db_save_profile(profile):
    vals = (
        profile["registerNumber"], profile["name"],
        json.dumps(profile["software"]), json.dumps(profile["hardware"]),
        json.dumps(profile["certificates"]), json.dumps(profile["certificateFiles"]),
        profile["appliedCompany"],
        profile["cgpa"] if profile["cgpa"] not in (None, "") else None,
        profile["updatedAt"],
    )
    if rds_enabled():
        with get_rds() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO students
                        (register_number,name,software,hardware,certificates,
                         certificate_files,applied_company,cgpa,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        name=VALUES(name), software=VALUES(software),
                        hardware=VALUES(hardware), certificates=VALUES(certificates),
                        certificate_files=VALUES(certificate_files),
                        applied_company=VALUES(applied_company), cgpa=VALUES(cgpa)
                    """, vals
                )
            conn.commit()
    else:
        with get_sqlite() as conn:
            conn.execute(
                """
                INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(register_number) DO UPDATE SET
                    name=excluded.name, software=excluded.software,
                    hardware=excluded.hardware, certificates=excluded.certificates,
                    certificate_files=excluded.certificate_files,
                    applied_company=excluded.applied_company,
                    cgpa=excluded.cgpa, updated_at=excluded.updated_at
                """, vals
            )
            conn.commit()


def db_load_all_profiles():
    if rds_enabled():
        with get_rds() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM students")
                rows = cur.fetchall()
        return {r["register_number"]: _row_to_profile(r) for r in rows}
    else:
        with get_sqlite() as conn:
            rows = conn.execute("SELECT * FROM students").fetchall()
        return {r["register_number"]: _row_to_profile(r) for r in rows}


# ---------------------------------------------------------------------------
# JSON file fallback (kept for read-only legacy access)
# ---------------------------------------------------------------------------

def load_student_profiles():
    try:
        with open(STUDENT_PROFILES_FILE, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def clean_list(values):
    return [str(value).strip() for value in values if str(value).strip()][:50]


backlog_model = load_model("backlog_model.pkl")
placement_model = load_model("placement_model.pkl")
subject_models = load_model("subject_models.pkl")


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/college-logo.jpg")
def college_logo():
    return send_from_directory(BASE_DIR, "college-logo.jpg")


@app.route("/companies")
def companies():
    return send_from_directory(BASE_DIR, "company_jobs.json", mimetype="application/json")


@app.route("/upload-certificate", methods=["POST"])
def upload_certificate():
    file = request.files.get("certificate")
    if file is None or not file.filename:
        return jsonify({"error": "Choose a certificate file to attach."}), 400

    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_CERTIFICATE_EXTENSIONS:
        return jsonify({"error": "Only PDF, PNG, JPG, and JPEG certificate files are supported."}), 400

    stored_name = f"{uuid4().hex}_{filename}"
    file.save(os.path.join(UPLOAD_DIR, stored_name))
    return jsonify({"name": filename, "url": f"/uploads/{stored_name}"}), 201


@app.route("/uploads/<path:filename>")
def uploaded_certificate(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/student-profile", methods=["POST"])
def save_student_profile():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    register_number = str(data.get("registerNumber", "")).strip().upper()
    if not name or not register_number:
        return jsonify({"error": "Student name and register number are required."}), 400

    profile = {
        "name": name,
        "registerNumber": register_number,
        "software": clean_list(data.get("software", [])),
        "hardware": clean_list(data.get("hardware", [])),
        "certificates": clean_list(data.get("certificates", [])),
        "certificateFiles": clean_list(file.get("name", "") for file in data.get("certificateFiles", [])),
        "appliedCompany": str(data.get("appliedCompany", "")).strip(),
        "cgpa": data.get("cgpa"),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    try:
        db_save_profile(profile)
        return jsonify({"saved": True, "store": "rds" if rds_enabled() else "sqlite"})
    except Exception as error:
        print(f"DB write failed ({error}).")
        return jsonify({"error": "Could not save profile."}), 500


@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    if data.get("username") != ADMIN_USERNAME or data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Invalid admin credentials."}), 401
    session["placement_admin"] = True
    return jsonify({"authenticated": True})


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("placement_admin", None)
    return jsonify({"logged_out": True})


@app.route("/admin/students")
def admin_students():
    if not session.get("placement_admin"):
        return jsonify({"error": "Admin sign-in required."}), 401

    terms = [term.lower() for term in request.args.get("skills", "").split() if term]
    skill_type = request.args.get("skillType", "all")
    minimum_cgpa = request.args.get("minimumCgpa", type=float)

    try:
        profiles = list(db_load_all_profiles().values())
    except Exception as error:
        print(f"DB read failed ({error}); falling back to JSON.")
        profiles = list(load_student_profiles().values())

    def matches(profile):
        scoped = profile.get(skill_type, []) if skill_type in {"software", "hardware", "certificates"} else (
            profile.get("software", []) + profile.get("hardware", []) + profile.get("certificates", [])
        )
        searchable = " ".join(scoped + [profile.get("appliedCompany", "")]).lower()
        return all(term in searchable for term in terms) and (minimum_cgpa is None or float(profile.get("cgpa") or 0) >= minimum_cgpa)

    results = [profile for profile in profiles if matches(profile)]
    return jsonify({"students": sorted(results, key=lambda profile: profile["name"].lower())})


@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True) or {}
    required = {"department", "semester", "study", "attendance", "internal", "cgpa", "communication", "technical", "coding", "aptitude", "projects", "certifications", "internship"}
    if not required.issubset(data):
        return jsonify({"error": "Complete all profile fields before running an assessment."}), 400

    input_data = pd.DataFrame([[
        DEPARTMENT_MAP[data["department"]], int(data["semester"]), int(data["study"]),
        int(data["attendance"]), int(data["internal"]), float(data["cgpa"]),
        int(data["communication"]), int(data["technical"]), int(data["coding"]),
        int(data["aptitude"]), int(data["projects"]), int(data["certifications"]),
        INTERNSHIP_MAP[data["internship"]]
    ]], columns=[
        "Department", "Semester", "Study_Hours", "Attendance", "Internal_Marks", "CGPA",
        "Communication_Skill", "Technical_Skill", "Coding_Skill", "Aptitude_Score",
        "Projects", "Certifications", "Internship"
    ])

    if backlog_model is not None and placement_model is not None:
        backlog = int(backlog_model.predict(input_data)[0])
        placement = int(placement_model.predict(input_data)[0])
        backlog_probability = model_probability(backlog_model, input_data, backlog)
        placement_probability = model_probability(placement_model, input_data, placement)
    else:
        backlog_probability, placement_probability = estimate_probabilities(data)
        backlog = int(backlog_probability >= 50)
        placement = int(placement_probability >= 55)

    subject_predictions = predict_subjects(data, input_data, backlog)

    return jsonify({
        "backlog": backlog,
        "placement": placement,
        "backlog_probability": round(backlog_probability, 1),
        "placement_probability": round(placement_probability, 1),
        "subjects": subject_predictions,
        "predicted_backlog_count": sum(1 for s in subject_predictions if s["at_risk"]),
        "tips": generate_tips(data, backlog, placement)
    })


def predict_subjects(data, input_data, backlog):
    """Predict which subjects the student is at risk of failing (backlogs in)."""
    results = []
    raw_subjects = data.get("subjects", {})

    for subject in SUBJECTS:
        key = subject["key"]
        raw = raw_subjects.get(key, {})
        internal = raw.get("internal", raw.get("internal_marks"))
        hours = raw.get("hours", raw.get("study_hours"))

        # Default from overall profile when subject values are missing
        if internal is None:
            internal = int(data.get("internal", 50))
        else:
            internal = int(internal)
        if hours is None:
            hours = int(data.get("study", 4))
        else:
            hours = int(hours)
        internal = max(0, min(40, internal))
        hours = max(0, min(15, hours))

        weak_threshold = 24
        if subject_models is not None and key in subject_models:
            weak_threshold = subject_models[key].get("weak_threshold") or weak_threshold

        record = {
            "key": key,
            "name": subject["name"],
            "internal": internal,
            "hours": hours,
            "at_risk": bool(backlog == 1 and internal < weak_threshold),
        }

        if subject_models is not None and key in subject_models:
            entry = subject_models[key]
            subject_row = pd.DataFrame([[
                input_data.iloc[0]["Department"], input_data.iloc[0]["Semester"],
                input_data.iloc[0]["Study_Hours"], input_data.iloc[0]["Attendance"],
                input_data.iloc[0]["Internal_Marks"], input_data.iloc[0]["CGPA"],
                input_data.iloc[0]["Communication_Skill"], input_data.iloc[0]["Technical_Skill"],
                input_data.iloc[0]["Coding_Skill"], input_data.iloc[0]["Aptitude_Score"],
                input_data.iloc[0]["Projects"], input_data.iloc[0]["Certifications"],
                input_data.iloc[0]["Internship"],
                internal, hours
            ]], columns=[
                "Department", "Semester", "Study_Hours", "Attendance", "Internal_Marks", "CGPA",
                "Communication_Skill", "Technical_Skill", "Coding_Skill", "Aptitude_Score",
                "Projects", "Certifications", "Internship",
                subject["internal_col"], subject["hours_col"]
            ])
            try:
                risk = int(entry["model"].predict(subject_row)[0])
                probability = float(entry["model"].predict_proba(subject_row)[0][1]) * 100
            except Exception as error:
                print(f"Subject model {key} failed: {error}")
                risk, probability = record["at_risk"], (85.0 if record["at_risk"] else 15.0)
            record["at_risk"] = bool(risk)
            record["probability"] = round(probability, 1)
            record["weak_threshold"] = entry.get("weak_threshold")
        else:
            record["probability"] = 85.0 if record["at_risk"] else 15.0

        results.append(record)

    return results


def model_probability(model, input_data, prediction):
    try:
        return float(model.predict_proba(input_data)[0][1]) * 100
    except Exception:
        return 85.0 if prediction else 15.0


def estimate_probabilities(data):
    """Bounded development estimate used only when trained models are unavailable."""
    attendance, study, internal = int(data["attendance"]), int(data["study"]), int(data["internal"])
    cgpa = float(data["cgpa"])
    communication, technical, coding = int(data["communication"]), int(data["technical"]), int(data["coding"])
    aptitude, projects, certifications = int(data["aptitude"]), int(data["projects"]), int(data["certifications"])
    internship = data["internship"] == "Yes"

    backlog_score = (75 - attendance) * 0.9 + (6.5 - cgpa) * 13 + (4 - study) * 4 + (55 - internal) * 0.35
    placement_score = (cgpa - 5) * 10 + communication * 3 + technical * 4 + coding * 4 + aptitude * 0.18 + projects * 5 + certifications * 3 + (10 if internship else 0)
    return max(3, min(97, 20 + backlog_score)), max(3, min(97, placement_score - 25))


def generate_tips(data, backlog, placement):
    tips = []
    if backlog:
        if int(data["attendance"]) < 75:
            tips.append({"type": "danger", "text": "Boost attendance above 75% to reduce backlog exposure."})
        if int(data["study"]) < 4:
            tips.append({"type": "warning", "text": "Increase daily study time to at least 4 to 5 hours."})
        if float(data["cgpa"]) < 6.5:
            tips.append({"type": "warning", "text": "Focus on core subjects to move your CGPA above 6.5."})
    if not placement:
        if int(data["communication"]) < 6:
            tips.append({"type": "info", "text": "Build communication skills through public speaking practice and feedback."})
        if int(data["technical"]) < 6 or int(data["coding"]) < 6:
            tips.append({"type": "info", "text": "Create a consistent technical and coding practice routine."})
        if int(data["projects"]) == 0:
            tips.append({"type": "info", "text": "Build one or two practical projects to strengthen your resume."})
        if data["internship"] == "No":
            tips.append({"type": "info", "text": "Pursue an internship to add relevant experience to your profile."})
    if not tips:
        tips = [
            {"type": "success", "text": "Maintain your performance and continue upskilling in your chosen area."},
            {"type": "success", "text": "Your profile supports applying to more selective opportunities."}
        ]
    return tips


ensure_sqlite_schema()
migrate_json_to_sqlite()
if ensure_rds_schema():
    print(f"RDS connected at {DB_HOST}:{DB_PORT}/{DB_NAME} - using MySQL.")
else:
    print("Using SQLite database: placement.db")

if __name__ == "__main__":
    print("Server running at http://localhost:5000")
    app.run(debug=True, port=5000, use_reloader=False)

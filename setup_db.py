"""
Run this once to create the local SQLite database and import all students
from student_profiles.json into it.

Usage:
    python setup_db.py
"""

import sqlite3
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "placement.db")
PROFILES_FILE = os.path.join(BASE_DIR, "student_profiles.json")


def create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            register_number TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            department TEXT,
            semester INTEGER,
            software TEXT,
            hardware TEXT,
            certificates TEXT,
            certificate_files TEXT,
            applied_company TEXT,
            cgpa REAL,
            attendance INTEGER,
            aptitude INTEGER,
            projects INTEGER,
            internship TEXT,
            backlog TEXT,
            placed TEXT,
            source TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            register_number TEXT,
            department TEXT,
            semester INTEGER,
            cgpa REAL,
            attendance INTEGER,
            internal_marks INTEGER,
            study_hours INTEGER,
            communication INTEGER,
            technical INTEGER,
            coding INTEGER,
            aptitude INTEGER,
            projects INTEGER,
            certifications INTEGER,
            internship TEXT,
            backlog_prediction INTEGER,
            placement_prediction INTEGER,
            backlog_probability REAL,
            placement_probability REAL,
            predicted_at TEXT
        );
    """)
    conn.commit()


def import_profiles(conn):
    if not os.path.exists(PROFILES_FILE):
        print("student_profiles.json not found, skipping import.")
        return 0

    with open(PROFILES_FILE, encoding="utf-8-sig") as f:
        profiles = json.load(f)

    count = 0
    for reg, p in profiles.items():
        try:
            conn.execute("""
                INSERT OR REPLACE INTO students
                    (register_number, name, department, semester, software, hardware,
                     certificates, certificate_files, applied_company, cgpa,
                     attendance, aptitude, projects, internship, backlog, placed,
                     source, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                p.get("registerNumber", reg),
                p.get("name", ""),
                p.get("department", ""),
                p.get("semester"),
                json.dumps(p.get("software", [])),
                json.dumps(p.get("hardware", [])),
                json.dumps(p.get("certificates", [])),
                json.dumps(p.get("certificateFiles", [])),
                p.get("appliedCompany", ""),
                p.get("cgpa"),
                p.get("attendance"),
                p.get("aptitude"),
                p.get("projects"),
                p.get("internship", ""),
                p.get("backlog", ""),
                p.get("placed", ""),
                p.get("source", ""),
                p.get("updatedAt", ""),
            ))
            count += 1
        except Exception as e:
            print(f"  Skipped {reg}: {e}")

    conn.commit()
    return count


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    print(f"Tables created in {DB_PATH}")

    imported = import_profiles(conn)
    print(f"Imported {imported} student profiles.")

    total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    print(f"Total students in DB: {total}")

    conn.close()
    print("Done! Database is ready.")

"""Populate the placement-cell directory from the student dataset CSV.

Reads Student_Backlog_Placement_Dataset_No_Subject_Attendance.csv and writes
student_profiles.json in the schema the admin /admin/students route expects.

Run:  python import_students.py
"""

import csv
import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "Student_Backlog_Placement_Dataset_No_Subject_Attendance.csv")
OUT_FILE = os.path.join(BASE_DIR, "student_profiles.json")

# Skills that belong to the hardware bucket when they appear in the dataset.
HARDWARE_SKILLS = {"iot", "arduino", "vlsi", "embedded c", "raspberry pi"}

DEPARTMENT_NAMES = {
    "CS": "Computer Science",
    "CSE": "Computer Science",
    "IT": "Information Technology",
    "EC": "Electronics & Communication",
    "ECE": "Electronics & Communication",
    "EE": "Electrical & Electronics",
    "EEE": "Electrical & Electronics",
    "ME": "Mechanical",
    "CE": "Civil",
}


def split_skills(raw):
    return [token.strip() for token in (raw or "").split(",") if token.strip()]


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def build_profile(row):
    register_number = (row.get("Student_ID") or "").strip().upper()
    if not register_number:
        return None

    department_code = (row.get("Department") or "").strip().upper()
    department = DEPARTMENT_NAMES.get(department_code, department_code)

    # Every coding skill goes into software unless it is a known hardware skill.
    software, hardware = [], []
    for skill in split_skills(row.get("Coding Skills")):
        (hardware if skill.lower() in HARDWARE_SKILLS else software).append(skill)

    certificates = []
    certification_count = to_int(row.get("Certifications")) or 0
    if certification_count > 0:
        certificates.append(f"{certification_count} certification(s) on record")

    internship = (row.get("Internship") or "").strip()
    backlog = (row.get("Backlog") or "").strip()
    placed = (row.get("Placed") or "").strip()

    return {
        "name": f"Student {register_number}",
        "registerNumber": register_number,
        "department": department,
        "semester": to_int(row.get("Semester")),
        "software": software,
        "hardware": hardware,
        "certificates": certificates,
        "certificateFiles": [],
        "appliedCompany": (row.get("Applied Company") or "").strip(),
        "cgpa": to_float(row.get("CGPA")),
        # Extra academic context shown in the directory.
        "attendance": to_int(row.get("Attendance")),
        "aptitude": to_int(row.get("Aptitude_Score")),
        "projects": to_int(row.get("Projects")),
        "internship": internship,
        "backlog": backlog,
        "placed": placed,
        "source": "dataset",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def main():
    if not os.path.exists(CSV_FILE):
        raise SystemExit(f"Dataset not found: {CSV_FILE}")

    with open(CSV_FILE, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    profiles = {}
    for row in rows:
        profile = build_profile(row)
        if profile:
            profiles[profile["registerNumber"]] = profile

    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        json.dump(profiles, handle, indent=2)

    skill_counter = {}
    for profile in profiles.values():
        for skill in profile["software"] + profile["hardware"]:
            skill_counter[skill] = skill_counter.get(skill, 0) + 1

    print(f"Imported {len(profiles)} students from {os.path.basename(CSV_FILE)}")
    print(f"Wrote {OUT_FILE}")
    print("Skills in directory:", ", ".join(f"{k} ({v})" for k, v in sorted(skill_counter.items())))


if __name__ == "__main__":
    main()

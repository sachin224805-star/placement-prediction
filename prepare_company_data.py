"""Convert the company-job workbook into the JSON consumed by the portal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
REQUIRED_COLUMNS = {
    "Company_ID", "Company", "Industry", "Job Role", "Required Skills",
    "Minimum CGPA", "Internship Required", "Backlogs Allowed",
    "Primary Location", "Experience Level", "Job Type",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare company job data for the portal.")
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()

    source = pd.read_excel(args.workbook)
    missing = REQUIRED_COLUMNS.difference(source.columns)
    if missing:
        raise ValueError(f"Workbook is missing required columns: {', '.join(sorted(missing))}")

    jobs = []
    for row in source.fillna("").to_dict(orient="records"):
        skills = [skill.strip() for skill in str(row["Required Skills"]).split(",") if skill.strip()]
        jobs.append({
            "id": str(row["Company_ID"]),
            "name": str(row["Company"]),
            "industry": str(row["Industry"]),
            "role": str(row["Job Role"]),
            "skills": skills,
            "minimumCgpa": float(row["Minimum CGPA"]),
            "internshipRequired": str(row["Internship Required"]),
            "backlogsAllowed": str(row["Backlogs Allowed"]),
            "location": str(row["Primary Location"]),
            "experience": str(row["Experience Level"]),
            "jobType": str(row["Job Type"]),
        })

    target = BASE_DIR / "company_jobs.json"
    target.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    print(f"Prepared {len(jobs)} company jobs in {target.name}")


if __name__ == "__main__":
    main()

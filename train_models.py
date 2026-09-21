"""Train the prediction models from the local dataset and supplied college reports.

The placement workbook is aggregate company-offer data, so it is summarised for
audit purposes but is not used as an individual student placement label.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier


BASE_DIR = Path(__file__).resolve().parent
FEATURES = [
    "Department", "Semester", "Study_Hours", "Attendance", "Internal_Marks",
    "CGPA", "Communication_Skill", "Technical_Skill", "Coding_Skill",
    "Aptitude_Score", "Projects", "Certifications", "Internship",
]
DEPARTMENT_MAP = {"CE": 0, "CSE": 1, "ECE": 2, "EEE": 3, "IT": 4, "ME": 5}
DEFAULTS = {
    "Department": DEPARTMENT_MAP["CSE"], "Semester": 7, "Study_Hours": 4,
    "Attendance": 75, "Internal_Marks": 65, "CGPA": 7.0,
    "Communication_Skill": 5, "Technical_Skill": 5, "Coding_Skill": 5,
    "Aptitude_Score": 65, "Projects": 1, "Certifications": 1, "Internship": 0,
}


def load_base_dataset() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    dataset = pd.read_csv(BASE_DIR / "Student_Backlog_Placement_Dataset_No_Subject_Attendance.csv")
    features = pd.DataFrame({column: dataset[column] for column in FEATURES})
    features["Department"] = features["Department"].replace({"CS": "CSE"}).map(DEPARTMENT_MAP)
    features["Internship"] = features["Internship"].map({"No": 0, "Yes": 1})
    return features, dataset["Backlog"].eq("Yes"), dataset["Placed"].eq("Yes")


def normalise_internal_marks(values: pd.Series) -> pd.Series:
    """Map report totals with varying subject counts onto the UI's 30-100 scale."""
    numeric = pd.to_numeric(values, errors="coerce").replace(0, pd.NA)
    lower, upper = numeric.quantile([0.05, 0.95])
    if pd.isna(lower) or pd.isna(upper) or lower == upper:
        return pd.Series(DEFAULTS["Internal_Marks"], index=values.index)
    scaled = 35 + (numeric - lower) * 60 / (upper - lower)
    return scaled.clip(30, 100).fillna(DEFAULTS["Internal_Marks"])


def load_academic_reports(paths: list[Path]) -> tuple[pd.DataFrame, pd.Series]:
    report_features: list[pd.DataFrame] = []
    report_targets: list[pd.Series] = []
    for path in paths:
        report = pd.read_csv(path, skiprows=1)
        needed = {"CGPA", "Internal Mark", "Current Backlogs"}
        if not needed.issubset(report.columns):
            raise ValueError(f"{path.name} is missing expected academic-report columns.")

        features = pd.DataFrame(DEFAULTS, index=report.index)
        features["CGPA"] = pd.to_numeric(report["CGPA"], errors="coerce").fillna(DEFAULTS["CGPA"])
        features["Internal_Marks"] = normalise_internal_marks(report["Internal Mark"])
        report_features.append(features[FEATURES])
        report_targets.append(pd.to_numeric(report["Current Backlogs"], errors="coerce").fillna(0).gt(0))
    return pd.concat(report_features, ignore_index=True), pd.concat(report_targets, ignore_index=True)


def workbook_summary(path: Path) -> dict[str, object]:
    placements = pd.read_excel(path, sheet_name="Placement Data", header=4)
    placements = placements.rename(columns={"Number of Students Selected": "students_selected"})
    selected = pd.to_numeric(placements["students_selected"], errors="coerce").fillna(0)
    return {
        "source": str(path),
        "companies": int(placements["Company Name"].notna().sum()),
        "reported_selections": int(selected.sum()),
        "note": "Aggregate offer data only; no individual student placement labels were available for model training.",
    }


def make_model() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=400, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=-1
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train backlog and placement models.")
    parser.add_argument("--academic-reports", nargs=2, type=Path, required=True)
    parser.add_argument("--placement-workbook", type=Path, required=True)
    args = parser.parse_args()

    base_features, base_backlog, placement = load_base_dataset()
    report_features, report_backlog = load_academic_reports(args.academic_reports)

    backlog_features = pd.concat([base_features, report_features], ignore_index=True)
    backlog_labels = pd.concat([base_backlog, report_backlog], ignore_index=True)
    backlog_model = make_model().fit(backlog_features, backlog_labels)
    placement_model = make_model().fit(base_features, placement)

    joblib.dump(backlog_model, BASE_DIR / "backlog_model.pkl")
    joblib.dump(placement_model, BASE_DIR / "placement_model.pkl")

    summary = workbook_summary(args.placement_workbook)
    summary.update({
        "base_student_records": int(len(base_features)),
        "academic_report_records": int(len(report_features)),
        "backlog_training_records": int(len(backlog_features)),
        "placement_training_records": int(len(base_features)),
    })
    (BASE_DIR / "training_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

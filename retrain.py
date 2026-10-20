"""Retrain backlog and placement models with 80/20 train-test split.

Uses only the CSV dataset (no academic reports or workbook needed).
Saves new .pkl files and writes model_evaluation.json with full metrics.
"""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "Student_Backlog_Placement_Dataset_No_Subject_Attendance.csv"

FEATURES = [
    "Department", "Semester", "Study_Hours", "Attendance", "Internal_Marks",
    "CGPA", "Communication_Skill", "Technical_Skill", "Coding_Skill",
    "Aptitude_Score", "Projects", "Certifications", "Internship",
]
DEPARTMENT_MAP = {"CE": 0, "CSE": 1, "ECE": 2, "EEE": 3, "IT": 4, "ME": 5}


def load_dataset():
    df = pd.read_csv(CSV_PATH)
    X = df[FEATURES].copy()
    X["Department"] = X["Department"].replace({"CS": "CSE"}).map(DEPARTMENT_MAP)
    X["Internship"] = X["Internship"].map({"No": 0, "Yes": 1})
    y_backlog = df["Backlog"].eq("Yes")
    y_placement = df["Placed"].eq("Yes")
    return X, y_backlog, y_placement


def make_model():
    return RandomForestClassifier(
        n_estimators=400, min_samples_leaf=2,
        class_weight="balanced", random_state=42, n_jobs=-1
    )


def evaluate(model, X_test, y_test):
    y_pred = model.predict(X_test)
    return {
        "train_size": int(len(X_test) * 4),   # 80% train
        "test_size": int(len(X_test)),
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "classification_report": classification_report(y_test, y_pred, output_dict=True),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    }


def main():
    print(f"Loading dataset: {CSV_PATH.name}")
    X, y_backlog, y_placement = load_dataset()
    print(f"  Total records : {len(X)}")

    # --- Backlog model ---
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_backlog, test_size=0.2, random_state=42, stratify=y_backlog
    )
    print(f"\nBacklog model  — train: {len(X_train)}, test: {len(X_test)}")
    backlog_model = make_model().fit(X_train, y_train)
    backlog_eval = evaluate(backlog_model, X_test, y_test)
    print(f"  Accuracy      : {backlog_eval['accuracy']:.4f}")
    print(f"  Confusion matrix (TN FP / FN TP):")
    for row in backlog_eval["confusion_matrix"]:
        print(f"    {row}")

    # --- Placement model ---
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_placement, test_size=0.2, random_state=42, stratify=y_placement
    )
    print(f"\nPlacement model — train: {len(X_train)}, test: {len(X_test)}")
    placement_model = make_model().fit(X_train, y_train)
    placement_eval = evaluate(placement_model, X_test, y_test)
    print(f"  Accuracy      : {placement_eval['accuracy']:.4f}")
    print(f"  Confusion matrix (TN FP / FN TP):")
    for row in placement_eval["confusion_matrix"]:
        print(f"    {row}")

    # --- Save models ---
    joblib.dump(backlog_model,   BASE_DIR / "backlog_model.pkl")
    joblib.dump(placement_model, BASE_DIR / "placement_model.pkl")
    print("\nSaved: backlog_model.pkl, placement_model.pkl")

    # --- Save evaluation report ---
    report = {
        "dataset": CSV_PATH.name,
        "total_records": int(len(X)),
        "split": "80% train / 20% test (stratified)",
        "backlog_model": backlog_eval,
        "placement_model": placement_eval,
    }
    out = BASE_DIR / "model_evaluation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved: model_evaluation.json")

    print("\n--- SUMMARY ---")
    print(f"Backlog  accuracy : {backlog_eval['accuracy']:.4f}")
    print(f"Placement accuracy: {placement_eval['accuracy']:.4f}")


if __name__ == "__main__":
    main()

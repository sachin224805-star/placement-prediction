import streamlit as st
import pandas as pd
import joblib

# Load models
backlog_model = joblib.load("backlog_model.pkl")
placement_model = joblib.load("placement_model.pkl")

st.set_page_config(page_title="Student Prediction System")

st.title("🎓 Student Backlog & Placement Prediction")

study = st.slider("Study Hours",1,10,4)
attendance = st.slider("Attendance (%)",50,100,80)
internal = st.slider("Internal Marks",30,100,60)
cgpa = st.slider("CGPA",5.0,10.0,7.0)
communication = st.slider("Communication Skill",1,10,5)
technical = st.slider("Technical Skill",1,10,5)
coding = st.slider("Coding Skill",1,10,5)
aptitude = st.slider("Aptitude Score",30,100,60)
projects = st.slider("Projects",0,5,1)
certifications = st.slider("Certifications",0,6,1)

internship = st.selectbox(
    "Internship",
    ["No","Yes"]
)

department = st.selectbox(
    "Department",
    ["CSE","ECE","EEE","ME","CE","IT"]
)

semester = st.selectbox(
    "Semester",
    [3,4,5,6,7,8]
)

# Encode values
dept_map = {
    "CE":0,
    "CSE":1,
    "ECE":2,
    "EEE":3,
    "IT":4,
    "ME":5
}

internship_map = {
    "No":0,
    "Yes":1
}

input_data = pd.DataFrame([[
    dept_map[department],
    semester,
    study,
    attendance,
    internal,
    cgpa,
    communication,
    technical,
    coding,
    aptitude,
    projects,
    certifications,
    internship_map[internship]
]], columns=[
    "Department",
    "Semester",
    "Study_Hours",
    "Attendance",
    "Internal_Marks",
    "CGPA",
    "Communication_Skill",
    "Technical_Skill",
    "Coding_Skill",
    "Aptitude_Score",
    "Projects",
    "Certifications",
    "Internship"
])

if st.button("Predict"):

    backlog = backlog_model.predict(input_data)[0]
    placement = placement_model.predict(input_data)[0]

    if backlog==1:
        st.error("⚠️ Backlog Risk : YES")
    else:
        st.success("✅ Backlog Risk : NO")

    if placement==1:
        st.success("🎉 Placement Chance : HIGH")
    else:
        st.warning("❌ Placement Chance : LOW")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import gspread
import os, json
from google.oauth2.service_account import Credentials

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_info = json.loads(os.environ["GOOGLE_CREDS_JSON"])
creds = Credentials.from_service_account_info(creds_info, scopes=scope)
client = gspread.authorize(creds)

sheet = client.open("EMPIRIA_DB")
students_sheet = sheet.worksheet("students")
skills_sheet = sheet.worksheet("skills")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def calculate_csi(attendance, internal_avg, certifications):
    return round((attendance * 0.4) + (internal_avg * 0.4) + (certifications * 10), 2)

@app.get("/student_intelligence")
def student_intelligence():
    records = students_sheet.get_all_records()
    results = []

    for r in records:
        att = int(r.get("attendance", 0))
        avg = int(r.get("internal_avg", 0))
        cert = int(r.get("certifications", 0))

        csi = calculate_csi(att, avg, cert)
        status = "Stable" if csi >= 80 else "At Risk" if csi >= 60 else "Critical"

        reasons = explain_csi(att, avg, cert)
        days_critical, days_save = risk_timeline(att, avg, cert, csi)
        drop_prob, urgency = dropout_engine(att, avg, cert, csi, days_critical)
        roadmap = branch_roadmap(r.get("branch",""), reasons)
        weak, dom, path, emp = skill_intelligence(r.get("branch",""), cert, csi)

        priority_score = round((80 - csi) * (2 if cert == 0 else 1) * (1.5 if att < 70 else 1), 2)

        job_data = predict_roles_and_salary(csi, dom)

        results.append({
            "id": r.get("id",""),
            "name": r.get("name",""),
            "branch": r.get("branch",""),
            "csi": csi,
            "status": status,

            "reasons": reasons,
            "critical_in_days": days_critical,
            "dropout_probability": drop_prob,
            "rescue_urgency": urgency,
            "days_to_save": days_save,

            "priority_score": priority_score,
            "roadmap": roadmap,

            "weak_skills": weak,
            "dominant_skill": dom,
            "success_path": path,
            "employability_score": emp,

            "job_roles": job_data["roles"],
            "salary_band": job_data["salary_range"],
            "survival_track": branch_survival_track(r.get("branch","")),
            "income_timeline": salary_time_estimator(priority_score)
        })

    return results

##############################################################
def predict_roles_and_salary(csi, dominant_skill):
    if dominant_skill == "Python":
        return {
            "roles": ["Backend Developer", "Data Analyst", "Automation Engineer"],
            "salary_range": "₹4–12 LPA"
        }
    if dominant_skill == "ML":
        return {
            "roles": ["ML Engineer", "AI Analyst"],
            "salary_range": "₹6–18 LPA"
        }
    return {
        "roles": ["IT Support", "QA Intern"],
        "salary_range": "₹2–5 LPA"
    }

def branch_survival_track(branch):
    tracks = {
        "CSE": ["Python","DSA","Backend","Internship"],
        "AIML": ["Python","ML","Projects","Kaggle","Internship"],
        "Data Science": ["Python","SQL","Pandas","Visualization","Internship"],
        "IT": ["Python","Git","Linux","Internship"]
    }
    return tracks.get(branch, ["Python","Git","Linux","Internship"])

def salary_time_estimator(priority_score):
    if priority_score < 10:
        return "2–3 months"
    elif priority_score < 15:
        return "4–6 months"
    else:
        return "6–9 months"
############################################################
def dropout_engine(att, avg, cert, csi, days_critical):
    dropout_prob = round(
        ((80 - csi) + (75 - att) + (65 - avg) + (1 if cert == 0 else 0)*20) / 2,
        2
    )
    dropout_prob = max(0, min(100, dropout_prob))

    rescue_urgency = "LOW"
    if days_critical < 30:
        rescue_urgency = "HIGH"
    elif days_critical < 60:
        rescue_urgency = "MEDIUM"

    return dropout_prob, rescue_urgency

##############################################################
@app.get("/kpi_summary")
def kpi_summary():
    records = students_sheet.get_all_records()
    total = len(records)
    stable = at_risk = critical = total_csi = 0
    for r in records:
        csi = calculate_csi(int(r["attendance"]), int(r["internal_avg"]), int(r["certifications"]))
        total_csi += csi
        if csi >= 80: stable += 1
        elif csi >= 60: at_risk += 1
        else: critical += 1
    return {
        "total_students": total,
        "stable": stable,
        "at_risk": at_risk,
        "critical": critical,
        "health_score": round(total_csi/total,2) if total else 0
    }

@app.get("/skill_demand")
def skill_demand():
    return skills_sheet.get_all_records()

@app.get("/interventions")
def interventions():
    actions = []
    for r in students_sheet.get_all_records():
        csi = calculate_csi(int(r["attendance"]), int(r["internal_avg"]), int(r["certifications"]))
        if csi < 60:
            actions.append({"name": r["name"], "action": "Immediate mentoring + certification push"})
        elif csi < 80:
            actions.append({"name": r["name"], "action": "Skill upgrade + mock interview"})
    return actions

@app.post("/assistant")
def assistant(query: dict):
    q = query["question"].lower()
    students = students_sheet.get_all_records()
    skills = skills_sheet.get_all_records()

    if "at risk" in q:
        return {"reply": [s["name"] for s in students if calculate_csi(int(s["attendance"]), int(s["internal_avg"]), int(s["certifications"])) < 80]}
    if "critical" in q:
        return {"reply": [s["name"] for s in students if calculate_csi(int(s["attendance"]), int(s["internal_avg"]), int(s["certifications"])) < 60]}
    if "skill" in q:
        return {"reply": skills}
    if "health" in q:
        avg = sum(calculate_csi(int(s["attendance"]), int(s["internal_avg"]), int(s["certifications"])) for s in students) / len(students)
        return {"reply": f"Institution Health Score is {round(avg,2)}"}
    return {"reply": "Ask about: at risk, critical, skills, health"}

def explain_csi(att, avg, cert):
    reasons = []
    if att < 75:
        reasons.append("Low attendance")
    if avg < 65:
        reasons.append("Low internal marks")
    if cert == 0:
        reasons.append("No certifications")
    if not reasons:
        reasons.append("Healthy performance")
    return reasons

####Risk timeline####
def risk_timeline(att, avg, cert, csi):
    cert_gap = 1 if cert == 0 else 0

    decay_rate = ((75 - att)/2 + (65 - avg) + (cert_gap * 10)) / 30
    decay_rate = max(decay_rate, 0.5)

    days_to_critical = round((csi - 59) / decay_rate, 1)
    days_to_critical = max(0, min(120, days_to_critical))

    recovery_rate = 1 + (cert * 0.3)
    days_to_save = round((80 - csi) / recovery_rate, 1)
    days_to_save = max(0, min(90, days_to_save))

    return days_to_critical, days_to_save

##Branch roadmap engine##
def branch_roadmap(branch, reasons):
    base = {
        "cse": ["Python", "DSA", "SQL", "Git", "Internship"],
        "aiml": ["Python", "ML", "DL", "SQL", "Internship"],
        "ece": ["Embedded C", "IoT", "MATLAB"],
        "mech": ["SolidWorks", "Manufacturing"],
        "civil": ["AutoCAD", "ETABS", "STAAD"],
        "eee": ["PLC", "SCADA", "MATLAB"]
    }

    roadmap = base.get(branch.lower(), ["Soft Skills", "Internship"])

    if "Low attendance" in reasons:
        roadmap.insert(0, "Attendance mentoring")
    if "Low internal marks" in reasons:
        roadmap.insert(0, "Core subject revision")
    if "No certifications" in reasons:
        roadmap.insert(0, "Mandatory certification")

    return roadmap

####Skill intelligence engine####
def skill_intelligence(branch, cert, csi):
    skill_map = {
        "cse": ["Python", "DSA", "SQL", "Git", "Internship"],
        "aiml": ["Python", "ML", "DL", "SQL", "Internship"],
        "ece": ["Embedded C", "IoT", "MATLAB"],
        "mech": ["SolidWorks", "Manufacturing"],
    }

    weights = {
        "Python":1.2, "DSA":1.4, "ML":1.3, "SQL":1.1,
        "Internship":1.5, "Git":1.0, "DL":1.2
    }

    skills = skill_map.get(branch.lower(), ["Soft Skills"])
    dominant = skills[0]
    employability = min(100, int((csi + cert*10) * weights.get(dominant,1)))

    weak = skills[2:] if cert > 0 else skills
    success_path = f"Can succeed via {dominant}-centric roles"

    return weak, dominant, success_path, employability

##########heatmap API###############
@app.get("/batch_heatmap")
def batch_heatmap():
    records = students_sheet.get_all_records()

    heatmap = {"Stable": 0, "At Risk": 0, "Critical": 0}
    total = len(records)

    for r in records:
        csi = calculate_csi(int(r["attendance"]), int(r["internal_avg"]), int(r["certifications"]))
        if csi >= 80:
            heatmap["Stable"] += 1
        elif csi >= 60:
            heatmap["At Risk"] += 1
        else:
            heatmap["Critical"] += 1

    return {
        "total_students": total,
        "distribution": heatmap,
        "risk_percentage": round((heatmap["Critical"] / total) * 100, 2) if total else 0
    }

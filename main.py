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

@app.get("/students_with_csi")
def students_with_csi():
    records = students_sheet.get_all_records()
    results = []
    for r in records:
        csi = calculate_csi(int(r["attendance"]), int(r["internal_avg"]), int(r["certifications"]))
        status = "Stable" if csi >= 80 else "At Risk" if csi >= 60 else "Critical"
        results.append({
            "name": r["name"],
            "branch": r["branch"],
            "csi": csi,
            "status": status
        })
    return results

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

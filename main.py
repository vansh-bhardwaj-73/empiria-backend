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

def certificate_score(cert_type):
    return certificate_weight(cert_type) * 10

def calculate_csi(att, avg, cert_type):
    return round((att * 0.4) + (avg * 0.4) + certificate_score(cert_type), 2)


def certificate_weight(cert_type):
    weights = {
        "professional": 1.0,     # Google, AWS, IBM, Microsoft
        "short_program": 0.7,    # Coursera, NPTEL, Udemy
        "workshop": 0.4,         # 1–3 day workshops
        "conference": 0.3,       # Paper / Attendee
        "student_coordinator": 0.2
    }
    return weights.get(cert_type.lower(), 0.2)


@app.get("/student_intelligence")
def student_intelligence():
    records = students_sheet.get_all_records()
    results = []

    for r in records:
        att = int(r.get("attendance", 0))
        avg = int(r.get("internal_avg", 0))
        cert_type = r.get("cert_type","student_coordinator")
        cred_weight, cred_tag = certificate_credibility(cert_type, r.get("cert_source","unknown"))
        cert_score = cred_weight * 10
        csi = round((att * 0.4) + (avg * 0.4) + cert_score, 2)

        status = "Stable" if csi >= 80 else "At Risk" if csi >= 60 else "Critical"

        reasons = explain_csi(att, avg, cert_score)
        days_critical, days_save = risk_timeline(att, avg, cert_score, csi)
        drop_prob, urgency = dropout_engine(att, avg, cert_score, csi, days_critical)
        roadmap = branch_roadmap(r.get("branch",""), reasons)
        weak, dom, path, emp = skill_intelligence(r.get("branch",""), cert_score, csi)
        daily_plan = daily_recovery_planner(r.get("branch",""), reasons, days_save, dom)
        placement_prob = placement_probability_engine(csi, emp)
        company_map = company_reality_mapper(dom, csi, emp)

        priority_score = round((80 - csi) * (2 if cert_score < 7 else 1) * (1.5 if att < 70 else 1), 2)

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
            "placement_probability": placement_prob,
            "daily_recovery_plan": daily_plan,
            "company_path": company_map,
            "certificate_credibility": cred_tag,

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

def placement_probability_engine(csi, employability_score):
    prob = round((csi * 0.5 + employability_score * 0.5), 2)
    return max(0, min(100, prob))

############################################################
def dropout_engine(att, avg, cert_score, csi, days_critical):
    dropout_prob = round(
        ((80 - csi) + (75 - att) + (65 - avg) + (1 if cert_score < 7 else 0)*20) / 2,
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
def daily_recovery_planner(branch, reasons, days_to_save, dominant_skill):
    plan = []

    if "Low attendance" in reasons:
        plan.append({"task":"Attend all classes", "hours":6})

    if "Low internal marks" in reasons:
        plan.append({"task":"Revise core subjects", "hours":3})

    if "Low quality certifications" in reasons:
        plan.append({"task":"Complete one professional certificate", "hours":2})

    # Skill track
    if dominant_skill == "Python":
        plan.append({"task":"Python practice", "hours":2})
    elif dominant_skill == "ML":
        plan.append({"task":"ML model building", "hours":2})
    else:
        plan.append({"task":"Technical skill building", "hours":2})

    plan.append({"task":"Mock interview / Resume improvement", "hours":1})

    return {
        "daily_hours_required": sum(p["hours"] for p in plan),
        "days_required": int(days_to_save),
        "daily_plan": plan
    }


##############################################################
@app.get("/kpi_summary")
def kpi_summary():
    records = students_sheet.get_all_records()
    total = len(records)
    stable = at_risk = critical = total_csi = 0
    for r in records:
        csi = calculate_csi(
            int(r["attendance"]),
            int(r["internal_avg"]),
            r.get("cert_type","student_coordinator")
            )

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
        csi = calculate_csi(
    int(r["attendance"]),
    int(r["internal_avg"]),
    r.get("cert_type","student_coordinator")
)

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

def explain_csi(att, avg, cert_score):
    reasons=[]
    if att<75: reasons.append("Low attendance")
    if avg<65: reasons.append("Low internal marks")
    if cert_score<4: reasons.append("Low quality certifications")
    return reasons or ["Healthy performance"]


####Risk timeline####
def risk_timeline(att, avg, cert_score, csi):
    cert_gap = 1 if cert_score < 4 else 0


    decay_rate = ((75 - att)/2 + (65 - avg) + (cert_gap * 10)) / 30
    decay_rate = max(decay_rate, 0.5)

    days_to_critical = round((csi - 59) / decay_rate, 1)
    days_to_critical = max(0, min(120, days_to_critical))

    recovery_rate = 1 + (cert_score * 0.3)
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
def skill_intelligence(branch, cert_score, csi):
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
    cert_weight = cert_score / 10
    employability = min(100, int((csi + cert_score) * weights.get(dominant,1)))
    weak = skills[2:] if cert_score > 4 else skills
    success_path = f"Can succeed via {dominant}-centric roles"

    return weak, dominant, success_path, employability

##########heatmap API###############
@app.get("/batch_heatmap")
def batch_heatmap():
    records = students_sheet.get_all_records()

    heatmap = {"Stable": 0, "At Risk": 0, "Critical": 0}
    total = len(records)

    for r in records:
        csi = calculate_csi(
    int(r["attendance"]),
    int(r["internal_avg"]),
    r.get("cert_type","student_coordinator")
)

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
###################Mentor Assignment Engine####################
@app.get("/mentor_queue")
def mentor_queue():
    records = students_sheet.get_all_records()
    queue = []

    for r in records:
        att = int(r["attendance"])
        avg = int(r["internal_avg"])
        cert_type = r.get("cert_type","student_coordinator")
        cert_score = certificate_score(cert_type)
        csi = calculate_csi(att, avg, cert_type)

        days_critical, _ = risk_timeline(att, avg, cert_score, csi)
        drop_prob, urgency = dropout_engine(att, avg, cert_score, csi, days_critical)

        if urgency == "HIGH":
            queue.append({
                "name": r["name"],
                "branch": r["branch"],
                "urgency": urgency,
                "action": "Immediate personal mentoring"
            })
        elif urgency == "MEDIUM":
            queue.append({
                "name": r["name"],
                "branch": r["branch"],
                "urgency": urgency,
                "action": "Group mentoring + certification plan"
            })

    return queue

###########Placement Probability Engine############
def placement_probability_engine(csi, employability_score):
    prob = round((csi * 0.5 + employability_score * 0.5), 2)
    prob = max(0, min(100, prob))
    return prob

##########Company mapping engine###############
def company_reality_mapper(dominant_skill, csi, employability):
    if dominant_skill == "Python":
        companies = ["TCS", "Accenture", "Infosys", "Zoho"]
        salary = "₹4–7 LPA" if employability < 80 else "₹7–12 LPA"
        blockers = ["DSA", "SQL", "Projects"] if employability < 80 else ["System Design"]
    elif dominant_skill == "ML":
        companies = ["Fractal", "Tiger Analytics", "Mu Sigma"]
        salary = "₹6–10 LPA" if employability < 80 else "₹10–18 LPA"
        blockers = ["Model deployment", "Projects"]
    else:
        companies = ["Wipro", "HCL"]
        salary = "₹2–4 LPA"
        blockers = ["Core skills"]

    return {
        "target_companies": companies,
        "expected_salary": salary,
        "skill_blockers": blockers
    }
##############################################################
###############Certificate credibility engine##################
def certificate_credibility(cert_type, cert_source):
    fake_sources = ["randomsite", "cheapcert", "telegram", "freepdf"]
    premium_sources = ["google", "microsoft", "aws", "ibm", "nptel", "coursera"]

    if cert_source.lower() in fake_sources:
        return -0.4, "FAKE / ZERO VALUE"
    if cert_source.lower() in premium_sources:
        return 1.0, "HIGH CREDIBILITY"
    return 0.4, "LOW CREDIBILITY"

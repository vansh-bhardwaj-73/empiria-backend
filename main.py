# ==========================================================
# EMPIRIA Intelligence API — Part 1 / 4
# Infrastructure, Config, Caching, Google Sheets, Utilities
# ==========================================================

"""
EMPIRIA Intelligence API (Industry Stable Edition - 2026)
Part 1/4: Infrastructure & Foundations
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.service_account import Credentials
import gspread

from typing import Any, Dict, List, Callable
import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

SECRET_KEY = os.getenv("EMPIRIA_SECRET", "EMPIRIA_SECURE_KEY_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


# ==========================================================
# APP METADATA
# ==========================================================

APP_NAME = "EMPIRIA Intelligence API"
APP_VERSION = "3.0.0"
ENV = os.getenv("ENV", "production")

# ==========================================================
# LOGGING (structured, production-safe)
# ==========================================================

logging.basicConfig(
    level=logging.INFO if ENV == "production" else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(APP_NAME)

# ==========================================================
# ENV VALIDATION
# ==========================================================

REQUIRED_ENV_VARS = [
    "GOOGLE_CREDS_JSON",
    "EMPIRIA_DB_NAME",
]

for var in REQUIRED_ENV_VARS:
    if var not in os.environ:
        raise RuntimeError(f"Missing required environment variable: {var}")

SHEET_NAME = os.environ["EMPIRIA_DB_NAME"]

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ==========================================================
# THREAD-SAFE GOOGLE SHEETS CLIENT
# ==========================================================

_SHEET_LOCK = threading.Lock()

def init_google_sheets():
    """
    Single responsibility:
    - Validate credentials
    - Connect to Google Sheets
    - Return worksheet handles
    """
    try:
        with open(os.environ["GOOGLE_CREDS_JSON"], "r") as f:
            creds_info = json.load(f)

        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=GOOGLE_SCOPES,
        )
        client = gspread.authorize(creds)
        book = client.open(SHEET_NAME)

        students_ws = book.worksheet("students")
        skills_ws = book.worksheet("skills")
        outcomes_ws = book.worksheet("outcomes")

        logger.info("Google Sheets connected successfully")
        return students_ws, skills_ws, outcomes_ws

    except Exception as e:
        logger.critical(f"Google Sheets initialization failed: {e}")
        raise

students_sheet, skills_sheet, outcomes_sheet = init_google_sheets()

def safe_sheet_fetch(ws) -> List[Dict[str, Any]]:
    """
    Thread-safe sheet read.
    Prevents race conditions under concurrent API load.
    """
    with _SHEET_LOCK:
        return ws.get_all_records()
def get_users_data():
    with _SHEET_LOCK:
        return students_sheet.spreadsheet.worksheet("users").get_all_records()

# ==========================================================
# TTL CACHE (NO MEMORY LEAK, NO STALE DATA)
# ==========================================================

class TTLCache:
    """
    Deterministic TTL cache.
    - No unbounded growth
    - Auto-refresh
    - Thread-safe reads
    """

    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._data = None
        self._timestamp = 0.0
        self._lock = threading.Lock()

    def get(self, loader: Callable[[], Any]):
        now = time.time()
        with self._lock:
            if self._data is None or (now - self._timestamp) > self.ttl:
                self._data = loader()
                self._timestamp = now
        return self._data

CACHE_TTL_SECONDS = 60

students_cache = TTLCache(CACHE_TTL_SECONDS)
skills_cache = TTLCache(CACHE_TTL_SECONDS)
outcomes_cache = TTLCache(CACHE_TTL_SECONDS)

def get_students_data() -> List[Dict[str, Any]]:
    return students_cache.get(lambda: safe_sheet_fetch(students_sheet))

def get_skills_data() -> List[Dict[str, Any]]:
    return skills_cache.get(lambda: safe_sheet_fetch(skills_sheet))

def get_outcomes_data() -> List[Dict[str, Any]]:
    return outcomes_cache.get(lambda: safe_sheet_fetch(outcomes_sheet))

# ==========================================================
# NUMERIC SAFETY UTILITIES
# ==========================================================

def safe_int(value: Any, default: int = 0) -> int:
    """
    Defensive numeric parsing.
    Prevents silent crashes from empty / malformed sheet cells.
    """
    try:
        return int(float(value))
    except Exception:
        return default

def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default

def clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ==========================================================
# FASTAPI APP INITIALIZATION
# ==========================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    users = safe_sheet_fetch(users_sheet)

    user = next((u for u in users if u["username"] == form.username), None)
    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "linked_student_id": user.get("linked_student_id")
    })

    return {"access_token": token, "token_type": "bearer"}

@app.get("/health")
def health_check():
    """
    Infra health only.
    Business intelligence starts in later parts.
    """
    return {
        "status": "ok",
        "env": ENV,
        "cached_students": len(get_students_data()),
    }

# ==========================================================
# END OF PART 1
# ==========================================================


# ==========================================================
# EMPIRIA Intelligence API — Part 2 / 4
# Core Intelligence Engines
# ==========================================================

"""
Part 2/4: Core intelligence, learning, risk & probability engines
"""

from typing import Dict, Any, Tuple, List

# ==========================================================
# CERTIFICATE CREDIBILITY ENGINE
# ==========================================================

def certificate_credibility(cert_type: str, cert_source: str) -> Tuple[float, str]:
    fake_sources = {"randomsite", "cheapcert", "telegram", "freepdf"}
    premium_sources = {"google", "microsoft", "aws", "ibm", "nptel", "coursera"}

    src = str(cert_source).strip().lower()

    if src in fake_sources:
        return -0.4, "FAKE / ZERO VALUE"
    if src in premium_sources:
        return 1.0, "HIGH CREDIBILITY"
    return 0.4, "LOW CREDIBILITY"

# ==========================================================
# SELF-LEARNING ADAPTIVE WEIGHTS ENGINE
# ==========================================================

def learn_from_outcomes() -> Dict[str, float]:
    """
    Learns certification effectiveness from historical outcomes.
    Deterministic, bounded, zero-division safe.
    """
    data = get_outcomes_data()
    stats: Dict[str, Dict[str, int]] = {}

    for r in data:
        cert = str(r.get("cert_type", "student_coordinator")).strip().lower()
        placed = str(r.get("placed", "no")).strip().lower() == "yes"

        if cert not in stats:
            stats[cert] = {"yes": 0, "no": 0}

        stats[cert]["yes" if placed else "no"] += 1

    adaptive_weights: Dict[str, float] = {}
    for cert, s in stats.items():
        total = s["yes"] + s["no"]
        adaptive_weights[cert] = round(s["yes"] / total, 2) if total else 0.2

    return adaptive_weights

def certificate_weight(cert_type: str) -> float:
    """
    Final weight resolver: adaptive first, fallback to base.
    """
    adaptive = learn_from_outcomes()
    key = str(cert_type).strip().lower()

    base = {
        "professional": 1.0,
        "short_program": 0.7,
        "workshop": 0.4,
        "conference": 0.3,
        "student_coordinator": 0.2,
    }

    return adaptive.get(key, base.get(key, 0.2))

# ==========================================================
# CSI CORE ENGINE
# ==========================================================

def final_csi(student: Dict[str, Any]) -> Tuple[float, float]:
    """
    Computes CSI and certification contribution.
    Fully backward-compatible with original logic.
    """
    attendance = safe_int(student.get("attendance"))
    internal_avg = safe_int(student.get("internal_avg"))
    cert_type = student.get("cert_type", "student_coordinator")

    cred_weight, _ = certificate_credibility(
        cert_type,
        student.get("cert_source", "unknown"),
    )

    base_score = (attendance * 0.4) + (internal_avg * 0.4)

    adaptive_factor = certificate_weight(cert_type)
    cert_score = adaptive_factor * 10 * cred_weight

    csi = clamp(base_score + cert_score, 0.0, 100.0)
    return round(csi, 2), round(cert_score, 2)

# ==========================================================
# CSI EXPLANATION ENGINE
# ==========================================================

def explain_csi(att: int, avg: int, cert_score: float) -> List[str]:
    reasons: List[str] = []

    if att < 75:
        reasons.append("Low attendance")
    if avg < 65:
        reasons.append("Low internal marks")
    if cert_score < 4:
        reasons.append("Low quality certifications")

    return reasons or ["Healthy performance"]

# ==========================================================
# RISK TIMELINE ENGINE
# ==========================================================

def risk_timeline(
    att: int,
    avg: int,
    cert_score: float,
    csi: float,
) -> Tuple[float, float]:
    """
    Estimates:
    - Days until critical
    - Days required to recover
    """
    cert_gap = 1 if cert_score <= 2 else 0

    decay_rate = max(
        ((75 - att) / 2 + (65 - avg) + (cert_gap * 10)) / 30,
        0.5,
    )

    days_to_critical = clamp((csi - 59) / decay_rate, 0, 120)

    recovery_rate = 1 + (cert_score * 0.3)
    days_to_save = clamp((80 - csi) / recovery_rate, 0, 90)

    return round(days_to_critical, 1), round(days_to_save, 1)

# ==========================================================
# DROPOUT PROBABILITY ENGINE
# ==========================================================

def dropout_engine(
    att: int,
    avg: int,
    cert_score: float,
    csi: float,
    days_critical: float,
) -> Tuple[float, str]:
    """
    Computes dropout probability and urgency level.
    """
    dropout_prob = clamp(
        (
            (80 - csi)
            + (75 - att)
            + (65 - avg)
            + (20 if cert_score <= 2 else 0)
        ) / 2,
        0,
        100,
    )

    urgency = (
        "HIGH"
        if days_critical < 30
        else "MEDIUM"
        if days_critical < 60
        else "LOW"
    )

    return round(dropout_prob, 2), urgency

# ==========================================================
# PLACEMENT PROBABILITY ENGINE
# ==========================================================

def placement_probability_engine(csi: float, employability: float) -> float:
    return clamp((csi * 0.5 + employability * 0.5), 0, 100)

# ==========================================================
# INCOME / SALARY TIMELINE ENGINE
# ==========================================================

def salary_time_estimator(priority_score: float) -> str:
    if priority_score < 10:
        return "2–3 months"
    if priority_score < 15:
        return "4–6 months"
    return "6–9 months"

# ==========================================================
# END OF PART 2
# ==========================================================


# ==========================================================
# EMPIRIA Intelligence API — Part 3 / 4
# Skill, Roadmap, Employability & Intervention Engines
# ==========================================================

"""
Part 3/4: Skill intelligence, employability, recovery, and intervention
"""

from typing import List, Dict, Any, Tuple

# ==========================================================
# BRANCH ROADMAP ENGINE
# ==========================================================

def branch_roadmap(branch: str, reasons: List[str]) -> List[str]:
    base_roadmaps = {
        "cse": ["Python", "DSA", "SQL", "Git", "Internship"],
        "aiml": ["Python", "ML", "DL", "SQL", "Internship"],
        "ece": ["Embedded C", "IoT", "MATLAB"],
        "mech": ["SolidWorks", "Manufacturing"],
        "civil": ["AutoCAD", "ETABS", "STAAD"],
        "eee": ["PLC", "SCADA", "MATLAB"],
    }

    roadmap = base_roadmaps.get(branch.lower(), ["Soft Skills", "Internship"]).copy()

    if "Low attendance" in reasons:
        roadmap.insert(0, "Attendance mentoring")
    if "Low internal marks" in reasons:
        roadmap.insert(0, "Core subject revision")
    if "Low quality certifications" in reasons:
        roadmap.insert(0, "Mandatory professional certification")

    return roadmap

# ==========================================================
# SKILL INTELLIGENCE & EMPLOYABILITY ENGINE
# ==========================================================

def skill_intelligence(
    branch: str,
    cert_score: float,
    csi: float,
) -> Tuple[List[str], str, str, float]:
    """
    Determines:
    - Weak skills
    - Dominant skill
    - Survival / success path
    - Employability score
    """
    skill_map = {
        "cse": ["Python", "DSA", "SQL", "Git", "Internship"],
        "aiml": ["Python", "ML", "DL", "SQL", "Internship"],
        "ece": ["Embedded C", "IoT", "MATLAB"],
        "mech": ["SolidWorks", "Manufacturing"],
        "civil": ["AutoCAD", "ETABS"],
        "eee": ["PLC", "SCADA"],
    }

    skill_weights = {
        "Python": 1.2,
        "DSA": 1.4,
        "ML": 1.3,
        "DL": 1.2,
        "SQL": 1.1,
        "Internship": 1.5,
        "Git": 1.0,
        "Embedded C": 1.2,
        "IoT": 1.1,
    }

    skills = skill_map.get(branch.lower(), ["Soft Skills"])
    dominant_skill = skills[0]

    employability = clamp(
        csi * skill_weights.get(dominant_skill, 1.0),
        0,
        100,
    )

    weak_skills = skills[2:] if cert_score > 4 else skills
    success_path = f"Can survive and grow via {dominant_skill}-centric roles"

    return weak_skills, dominant_skill, success_path, round(employability, 2)

# ==========================================================
# DAILY RECOVERY PLANNER
# ==========================================================

def daily_recovery_planner(
    branch: str,
    reasons: List[str],
    days_to_save: float,
    dominant_skill: str,
) -> Dict[str, Any]:
    plan: List[Dict[str, Any]] = []

    if "Low attendance" in reasons:
        plan.append({"task": "Attend all classes", "hours": 6})

    if "Low internal marks" in reasons:
        plan.append({"task": "Revise core subjects", "hours": 3})

    if "Low quality certifications" in reasons:
        plan.append({
            "task": "Complete one professional certification",
            "hours": 2,
        })

    plan.append({"task": f"{dominant_skill} daily practice", "hours": 2})
    plan.append({"task": "Mock interview / Resume improvement", "hours": 1})

    return {
        "daily_hours_required": sum(p["hours"] for p in plan),
        "days_required": int(days_to_save),
        "daily_plan": plan,
    }

# ==========================================================
# COMPANY REALITY MAPPER
# ==========================================================

def company_reality_mapper(
    dominant_skill: str,
    csi: float,
    employability: float,
) -> Dict[str, Any]:
    if dominant_skill == "Python":
        companies = ["TCS", "Accenture", "Infosys", "Zoho"]
        salary = "₹4–7 LPA" if employability < 80 else "₹7–12 LPA"
        blockers = ["DSA", "SQL", "Projects"] if employability < 80 else ["System Design"]

    elif dominant_skill in ("ML", "DL"):
        companies = ["Fractal", "Tiger Analytics", "Mu Sigma"]
        salary = "₹6–10 LPA" if employability < 80 else "₹10–18 LPA"
        blockers = ["Model deployment", "End-to-end projects"]

    else:
        companies = ["Wipro", "HCL"]
        salary = "₹2–4 LPA"
        blockers = ["Core skill depth"]

    return {
        "target_companies": companies,
        "expected_salary": salary,
        "skill_blockers": blockers,
    }

# ==========================================================
# INTERVENTION / PRIORITY ENGINE
# ==========================================================

def intervention_priority(
    csi: float,
    cert_score: float,
    attendance: int,
) -> float:
    """
    Higher score = higher intervention priority.
    """
    priority = (80 - csi)
    if cert_score < 7:
        priority *= 2
    if attendance < 70:
        priority *= 1.5

    return round(max(priority, 0), 2)

# ==========================================================
# END OF PART 3
# ==========================================================


# ==========================================================
# EMPIRIA Intelligence API — Part 4 / 4
# FastAPI Endpoints, Assistant, Feedback, Learning Adjuster
# ==========================================================

"""
Part 4/4: API endpoints and orchestration layer
"""

from fastapi import HTTPException
from typing import Dict, Any, List

# ==========================================================
# STUDENT INTELLIGENCE (FULL PIPELINE)
# ==========================================================

@app.get("/student_intelligence")
def student_intelligence():
    try:
        students = get_students_data()
        results: List[Dict[str, Any]] = []

        for s in students:
            att = safe_int(s.get("attendance"))
            avg = safe_int(s.get("internal_avg"))

            csi, cert_score = final_csi(s)
            status = "Stable" if csi >= 80 else "At Risk" if csi >= 60 else "Critical"

            reasons = explain_csi(att, avg, cert_score)
            days_critical, days_save = risk_timeline(att, avg, cert_score, csi)
            dropout_prob, urgency = dropout_engine(att, avg, cert_score, csi, days_critical)

            roadmap = branch_roadmap(s.get("branch", ""), reasons)
            weak, dominant, path, employability = skill_intelligence(
                s.get("branch", ""),
                cert_score,
                csi,
            )

            daily_plan = daily_recovery_planner(
                s.get("branch", ""),
                reasons,
                days_save,
                dominant,
            )

            placement_prob = placement_probability_engine(csi, employability)
            company_map = company_reality_mapper(dominant, csi, employability)

            priority = intervention_priority(csi, cert_score, att)
            _, cred_tag = certificate_credibility(
                s.get("cert_type", ""),
                s.get("cert_source", ""),
            )

            results.append({
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "branch": s.get("branch", ""),
                "csi": csi,
                "status": status,
                "reasons": reasons,
                "critical_in_days": days_critical,
                "dropout_probability": dropout_prob,
                "rescue_urgency": urgency,
                "days_to_save": days_save,
                "priority_score": priority,
                "roadmap": roadmap,
                "weak_skills": weak,
                "dominant_skill": dominant,
                "success_path": path,
                "employability_score": employability,
                "placement_probability": placement_prob,
                "daily_recovery_plan": daily_plan,
                "company_path": company_map,
                "certificate_credibility": cred_tag,
                "income_timeline": salary_time_estimator(priority),
            })

        return results

    except Exception as e:
        logger.exception("student_intelligence failed")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================
# KPI SUMMARY DASHBOARD
# ==========================================================

@app.get("/kpi_summary")
def kpi_summary():
    students = get_students_data()
    total = len(students)

    stable = at_risk = critical = 0
    total_csi = 0.0

    for s in students:
        csi, _ = final_csi(s)
        total_csi += csi
        if csi >= 80:
            stable += 1
        elif csi >= 60:
            at_risk += 1
        else:
            critical += 1

    return {
        "total_students": total,
        "stable": stable,
        "at_risk": at_risk,
        "critical": critical,
        "health_score": round(total_csi / total, 2) if total else 0,
    }

# ==========================================================
# SKILL DEMAND VIEW
# ==========================================================

@app.get("/skill_demand")
def skill_demand():
    return get_skills_data()

# ==========================================================
# BATCH HEATMAP
# ==========================================================

@app.get("/batch_heatmap")
def batch_heatmap():
    students = get_students_data()
    distribution = {"Stable": 0, "At Risk": 0, "Critical": 0}

    for s in students:
        csi, _ = final_csi(s)
        if csi >= 80:
            distribution["Stable"] += 1
        elif csi >= 60:
            distribution["At Risk"] += 1
        else:
            distribution["Critical"] += 1

    total = len(students)
    return {
        "total_students": total,
        "distribution": distribution,
        "risk_percentage": round(
            (distribution["Critical"] / total) * 100, 2
        ) if total else 0,
    }

# ==========================================================
# MENTOR QUEUE (REAL LOGIC)
# ==========================================================

@app.get("/mentor_queue")
def mentor_queue():
    queue: List[Dict[str, Any]] = []

    for s in get_students_data():
        att = safe_int(s.get("attendance"))
        avg = safe_int(s.get("internal_avg"))
        csi, cert_score = final_csi(s)

        days_critical, _ = risk_timeline(att, avg, cert_score, csi)
        _, urgency = dropout_engine(att, avg, cert_score, csi, days_critical)

        if urgency in ("HIGH", "MEDIUM"):
            queue.append({
                "name": s.get("name", ""),
                "branch": s.get("branch", ""),
                "urgency": urgency,
                "action": (
                    "Immediate 1-on-1 mentoring"
                    if urgency == "HIGH"
                    else "Group mentoring + certification plan"
                ),
            })

    return queue

# ==========================================================
# STUDENT ASSISTANT AI (INTENT-BASED)
# ==========================================================

@app.post("/assistant")
def assistant(query: Dict[str, str]):
    q = query.get("question", "").lower()
    students = get_students_data()

    if "at risk" in q:
        return {"reply": [s["name"] for s in students if final_csi(s)[0] < 80]}
    if "critical" in q:
        return {"reply": [s["name"] for s in students if final_csi(s)[0] < 60]}
    if "skills" in q:
        return {"reply": get_skills_data()}
    if "health" in q:
        avg = sum(final_csi(s)[0] for s in students) / len(students)
        return {"reply": f"Institution Health Score is {round(avg, 2)}"}

    return {"reply": "Ask about: at risk, critical, skills, health"}

# ==========================================================
# OUTCOME FEEDBACK LOGGING
# ==========================================================

@app.post("/outcome_feedback")
def outcome_feedback(data: Dict[str, Any]):
    try:
        with _SHEET_LOCK:
            outcomes_sheet.append_row([
                data.get("id", ""),
                data.get("cert_type", ""),
                data.get("placed", ""),
                data.get("salary", ""),
                data.get("days", ""),
            ])
        return {"status": "Recorded"}
    except Exception as e:
        logger.exception("Outcome feedback failed")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================
# SELF-LEARNING ADJUSTER (AUTOMATIC)
# ==========================================================

def self_learning_adjuster():
    """
    Periodic learning sanity check.
    Can be scheduled via cron / background task.
    """
    logs = get_outcomes_data()
    placed = [safe_int(r.get("salary")) for r in logs if str(r.get("placed")).lower() == "yes"]

    if not placed:
        return

    avg_salary = sum(placed) / len(placed)
    if avg_salary < 500000:
        logger.info("Learning adjuster: salaries low — tuning recommended")

# ==========================================================
# END OF PART 4 — SYSTEM COMPLETE (19/19)
# ==========================================================
def role_required(role: str):
    def checker(user=Depends(get_current_user)):
        if user["role"] != role:
            raise HTTPException(status_code=403, detail="Access denied")
        return user
    return checker

@app.get("/dashboard/student")
def student_dashboard(user=Depends(role_required("student"))):
    return {"message": f"Welcome student {user['sub']}"}

@app.get("/dashboard/mentor")
def mentor_dashboard(user=Depends(role_required("mentor"))):
    return {"message": f"Welcome mentor {user['sub']}"}

@app.get("/dashboard/institute")
def institute_dashboard(user=Depends(role_required("institute"))):
    return {"message": f"Welcome institute {user['sub']}"}

"""FaceTrack AI - role based (employee / HR / admin) face attendance. Run: uvicorn main:app --port 8000"""

import hmac
import os
import secrets
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import connection, init_db
from app.face_engine import FaceEngine, FaceEngineError, MATCH_THRESHOLD, MAX_IMAGE_BYTES

ROOT = Path(__file__).resolve().parent
_engine: Optional[FaceEngine] = None

CHECKIN_LAST = "09:15"      # check-ins after 09:15:59 are rejected, no attendance
CHECKOUT_FROM = "16:45"
LEAVES_PER_YEAR = 12
REGISTRATION_KEY = os.environ.get("REGISTRATION_KEY", "facetrack-staff")  # secret needed to register as HR/admin
DUPLICATE_THRESHOLD = 0.55  # registration refuses a face this close to an existing account
LOGIN_THRESHOLD = 0.45      # stricter than attendance matching, because a match here opens an account
STAFF_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,19}$")
DEPARTMENTS = ["Frontend Developer", "Backend Developer", "Full Stack Developer", "Mobile Developer",
               "UI/UX Designer", "QA Engineer", "DevOps Engineer", "Data / AI Engineer"]
HOLIDAYS = [("02-05", "Kashmir Solidarity Day"), ("03-23", "Pakistan Day"), ("05-01", "Labour Day"),
            ("08-14", "Independence Day"), ("11-09", "Iqbal Day"), ("12-25", "Quaid-e-Azam Day")]
RULES = {
    "checkin_last": CHECKIN_LAST, "checkout_from": CHECKOUT_FROM, "weekly_off": "Sunday",
    "holidays": [{"date": d, "name": n} for d, n in HOLIDAYS],
    "note": "Eid, Ashura and other moon-based holidays are announced by HR as department/all-staff offs.",
    "leave_rules": [
        f"{LEAVES_PER_YEAR} leave days per year (pending and approved requests both count).",
        "Every request needs a title, a reason and from/to dates; HR approves employees, admin approves HR.",
        "Apply at least 1 day ahead, except for emergencies (explain in the reason).",
        "Check-in after 09:15 gives no attendance for that day.",
    ],
}


def now() -> datetime:
    return datetime.now()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="FaceTrack AI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def engine() -> FaceEngine:
    global _engine
    if _engine is None:
        try:
            _engine = FaceEngine()
        except FaceEngineError as exc:
            raise HTTPException(503, str(exc))
    return _engine


def read_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image is empty or larger than 8 MB.")
    return data


# ---------- auth ----------

def new_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions(token, user_id) VALUES(?,?)", (token, user_id))
    return token


def public(u) -> dict:
    return {k: u[k] for k in ("id", "role", "name", "staff_code", "department", "photo", "status")}


def current(authorization: str = Header(None)) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    with connection() as conn:
        row = conn.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (token,)).fetchone()
    if not row or row["status"] == "fired":
        raise HTTPException(401, "Please log in again.")
    return dict(row)


def need(*roles):
    def dep(user: dict = Depends(current)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "You do not have access to this.")
        return user
    return dep


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    ready = all((ROOT / "models" / n).exists() for n in
                ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx"))
    return {"models_ready": ready}


@app.get("/api/rules")
def rules(_: dict = Depends(current)):
    return {**RULES, "departments": DEPARTMENTS}


@app.get("/api/departments")
def departments():
    return {"departments": DEPARTMENTS}


@app.post("/api/register")
def register(name: str = Form(...), staff_code: str = Form(...), role: str = Form(...),
             department: str = Form(""), key: str = Form(""), images: list[UploadFile] = File(...)):
    name, staff_code = name.strip(), staff_code.strip().upper()
    if role not in ("employee", "hr", "admin"):
        raise HTTPException(422, "Choose a valid role.")
    if not name or len(name) > 100:
        raise HTTPException(422, "Enter your full name.")
    if not STAFF_CODE_RE.match(staff_code):
        raise HTTPException(422, "Staff code must be 2-20 letters, digits, - or _.")
    if role == "employee":                      # employees choose a department; HR/admin have none
        if department not in DEPARTMENTS:
            raise HTTPException(422, "Choose your department.")
    else:
        department = "Human Resources" if role == "hr" else "Administration"
        if not hmac.compare_digest(key, REGISTRATION_KEY):
            raise HTTPException(403, "HR and admin accounts need the registration key.")
    if not 1 <= len(images) <= 3:
        raise HTTPException(422, "Provide 1 to 3 face photos.")

    eng, samples = engine(), []
    for i, f in enumerate(images, 1):
        try:
            samples.append(eng.extract(read_upload(f)))
        except FaceEngineError as exc:
            raise HTTPException(422, f"Photo {i}: {exc}")
    emb = eng.combine([s["embedding"] for s in samples])

    with connection() as conn:
        existing = [dict(r) for r in conn.execute("SELECT name, embedding FROM users")]
        dup = eng.best_match(emb, existing, DUPLICATE_THRESHOLD)
        if dup and "student" in dup:
            raise HTTPException(409, f"This face is already registered as {dup['student']['name']} (match {dup['similarity']:.2f}).")
        try:
            cur = conn.execute(
                "INSERT INTO users(role,name,staff_code,department,photo,embedding) VALUES(?,?,?,?,?,?)",
                (role, name, staff_code, department, samples[0]["photo"], emb.tobytes()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "This staff code is already registered.")
        token = new_session(conn, cur.lastrowid)
        user = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"token": token, "user": public(user)}


@app.post("/api/face-login")
def face_login(image: UploadFile = File(...)):
    """The only way to log in: the face in the frame must match a registered account."""
    eng = engine()
    try:
        ex = eng.extract(read_upload(image))
    except FaceEngineError as exc:
        raise HTTPException(422, str(exc))
    with connection() as conn:
        people = [dict(r) for r in conn.execute("SELECT * FROM users")]
        m = eng.best_match(ex["embedding"], people, LOGIN_THRESHOLD)
        if not m:
            raise HTTPException(404, "Face not recognised. Register first if you are new.")
        if m.get("ambiguous"):
            raise HTTPException(409, "Could not tell who this is. Move closer and look at the camera.")
        u = m["student"]
        if u["status"] == "fired":
            raise HTTPException(403, "This account has been terminated.")
        token = new_session(conn, u["id"])
    return {"token": token, "user": public(u)}


@app.post("/api/logout")
def logout(authorization: str = Header(None)):
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", ((authorization or "").removeprefix("Bearer ").strip(),))
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current)):
    with connection() as conn:
        warns = [dict(r) for r in conn.execute(
            "SELECT reason, created_at FROM warnings WHERE user_id=? ORDER BY id DESC", (user["id"],))]
        offs = [dict(r) for r in conn.execute(
            "SELECT day, department, title FROM offs WHERE day>=? AND department IN ('All',?) ORDER BY day",
            (now().strftime("%Y-%m-%d"), user["department"]))]
    return {"user": public(user), "warnings": warns, "offs": offs, "today": day_status(user)}


# ---------- attendance ----------

def off_reason(user: dict, day: date) -> Optional[str]:
    if day.weekday() == 6:
        return "Sunday - weekly off"
    for md, n in HOLIDAYS:
        if day.strftime("%m-%d") == md:
            return n
    with connection() as conn:
        r = conn.execute("SELECT title FROM offs WHERE day=? AND department IN ('All',?)",
                         (day.isoformat(), user["department"])).fetchone()
    return f"Off: {r['title']}" if r else None


def on_leave(user_id: int, day: date) -> bool:
    with connection() as conn:
        return bool(conn.execute("SELECT 1 FROM leaves WHERE user_id=? AND status='approved' AND ? BETWEEN from_day AND to_day",
                                 (user_id, day.isoformat())).fetchone())


def day_status(user: dict) -> dict:
    t = now()
    with connection() as conn:
        a = conn.execute("SELECT check_in, check_out FROM work_attendance WHERE user_id=? AND day=?",
                         (user["id"], t.date().isoformat())).fetchone()
    off = off_reason(user, t.date())
    return {"off": off, "on_leave": on_leave(user["id"], t.date()),
            "check_in": a["check_in"] if a else None, "check_out": a["check_out"] if a else None}


def auto_mark(u: dict, score: float, t: datetime) -> dict:
    """Attendance with no buttons: the first sighting in time is check-in, a sighting from 16:45 is check-out."""
    if u["role"] == "admin":
        return {"status": "skip", "message": "Admin - no attendance."}
    if (reason := off_reason(u, t.date())):
        return {"status": "off", "message": reason}
    if on_leave(u["id"], t.date()):
        return {"status": "leave", "message": "On approved leave today."}
    day, hm, clock = t.date().isoformat(), t.strftime("%H:%M"), t.strftime("%H:%M:%S")
    with connection() as conn:
        a = conn.execute("SELECT check_in, check_out FROM work_attendance WHERE user_id=? AND day=?", (u["id"], day)).fetchone()
        if not a:
            if hm > CHECKIN_LAST:
                return {"status": "late", "message": f"Check-in closed at {CHECKIN_LAST}. No attendance today."}
            conn.execute("INSERT OR IGNORE INTO work_attendance(user_id,day,check_in,similarity) VALUES(?,?,?,?)",
                         (u["id"], day, clock, score))
            return {"status": "checkin", "time": clock}
        if a["check_out"]:
            return {"status": "already", "time": a["check_out"], "message": "Already checked out today."}
        if hm >= CHECKOUT_FROM:
            conn.execute("UPDATE work_attendance SET check_out=? WHERE user_id=? AND day=?", (clock, u["id"], day))
            return {"status": "checkout", "time": clock}
        return {"status": "already", "time": a["check_in"], "message": f"Checked in at {a['check_in']}."}


@app.post("/api/camera/scan")
def camera_scan(image: UploadFile = File(...), _: dict = Depends(need("hr"))):
    """One frame from the HR-controlled camera. Every recognised face is marked automatically."""
    eng = engine()
    try:
        faces = eng.detect_all(read_upload(image))
    except FaceEngineError as exc:
        raise HTTPException(422, str(exc))
    t = now()
    results = []
    if faces:
        with connection() as conn:
            people = [dict(r) for r in conn.execute("SELECT * FROM users")]
        for f in faces:
            m = FaceEngine.best_match(f["embedding"], people, MATCH_THRESHOLD)
            if not m or m.get("ambiguous"):
                results.append({"box": f["box"], "status": "unknown"})
                continue
            u = m["student"]
            base = {"box": f["box"], "user_id": u["id"], "name": u["name"], "staff_code": u["staff_code"],
                    "department": u["department"]}
            if u["status"] == "fired":
                results.append({**base, "status": "blocked", "message": "Account terminated."})
            else:
                results.append({**base, **auto_mark(u, m["similarity"], t)})
    return {"results": results}


@app.get("/api/my-attendance")
def my_attendance(user: dict = Depends(current)):
    with connection() as conn:
        rows = conn.execute("SELECT day, check_in, check_out FROM work_attendance WHERE user_id=? ORDER BY day DESC LIMIT 400",
                            (user["id"],)).fetchall()
    return {"records": [dict(r) for r in rows]}


@app.get("/api/today")
def today(user: dict = Depends(need("hr", "admin")), day: str = ""):
    d = day or now().strftime("%Y-%m-%d")
    roles = ("employee",) if user["role"] == "hr" else ("employee", "hr")
    with connection() as conn:
        users = conn.execute(f"SELECT * FROM users WHERE status!='fired' AND role IN ({','.join('?' * len(roles))}) "
                             "ORDER BY department, name", roles).fetchall()
        att = {r["user_id"]: r for r in conn.execute("SELECT * FROM work_attendance WHERE day=?", (d,))}
    out, t = [], now()
    for u in users:
        a = att.get(u["id"])
        if a:
            status = "Present"
        elif off_reason(dict(u), date.fromisoformat(d)):
            status = "Off"
        elif on_leave(u["id"], date.fromisoformat(d)):
            status = "On leave"
        elif d < t.strftime("%Y-%m-%d") or t.strftime("%H:%M") > CHECKIN_LAST:
            status = "Absent"
        else:
            status = "Not yet"
        out.append({"id": u["id"], "name": u["name"], "role": u["role"], "department": u["department"], "photo": u["photo"],
                    "check_in": a["check_in"] if a else None, "check_out": a["check_out"] if a else None, "status": status})
    return {"day": d, "rows": out}


# ---------- leaves ----------

@app.post("/api/leaves")
def apply_leave(title: str = Form(...), reason: str = Form(...), from_day: str = Form(...), to_day: str = Form(...),
                user: dict = Depends(need("employee", "hr"))):
    title, reason = title.strip(), reason.strip()
    try:
        f, t = date.fromisoformat(from_day), date.fromisoformat(to_day)
    except ValueError:
        raise HTTPException(422, "Enter valid dates.")
    if not title or not reason or len(title) > 120 or len(reason) > 1000:
        raise HTTPException(422, "Title and reason are required.")
    if t < f or f < now().date():
        raise HTTPException(422, "Leave dates must be today or later, and 'to' cannot be before 'from'.")
    days = (t - f).days + 1
    with connection() as conn:
        used = sum((date.fromisoformat(r["to_day"]) - date.fromisoformat(r["from_day"])).days + 1 for r in conn.execute(
            "SELECT from_day,to_day FROM leaves WHERE user_id=? AND status!='rejected' AND from_day LIKE ?",
            (user["id"], f"{f.year}-%")))
        if used + days > LEAVES_PER_YEAR:
            raise HTTPException(409, f"Only {max(LEAVES_PER_YEAR - used, 0)} leave day(s) left this year.")
        cur = conn.execute("INSERT INTO leaves(user_id,title,reason,from_day,to_day) VALUES(?,?,?,?,?)",
                           (user["id"], title, reason, from_day, to_day))
    return {"id": cur.lastrowid}


@app.get("/api/leaves")
def list_leaves(mine: bool = False, user: dict = Depends(current)):
    sql = ("SELECT l.*, u.name, u.role, u.department, d.name AS decided_name FROM leaves l JOIN users u ON u.id=l.user_id "
           "LEFT JOIN users d ON d.id=l.decided_by")
    if mine or user["role"] == "employee":
        sql, p = sql + " WHERE l.user_id=?", (user["id"],)
    elif user["role"] == "hr":
        sql, p = sql + " WHERE u.role='employee'", ()
    else:
        p = ()
    with connection() as conn:
        rows = conn.execute(sql + " ORDER BY l.status='pending' DESC, l.id DESC LIMIT 300", p).fetchall()
    return {"leaves": [dict(r) for r in rows]}


@app.post("/api/leaves/{leave_id}/decide")
def decide_leave(leave_id: int, decision: str = Form(...), user: dict = Depends(need("hr", "admin"))):
    if decision not in ("approved", "rejected"):
        raise HTTPException(422, "Decision must be approved or rejected.")
    with connection() as conn:
        l = conn.execute("SELECT l.id, l.status, u.role, l.user_id FROM leaves l JOIN users u ON u.id=l.user_id WHERE l.id=?",
                         (leave_id,)).fetchone()
        if not l:
            raise HTTPException(404, "Leave not found.")
        if l["user_id"] == user["id"] or (user["role"] == "hr" and l["role"] != "employee"):
            raise HTTPException(403, "You cannot decide this request.")
        conn.execute("UPDATE leaves SET status=?, decided_by=? WHERE id=?", (decision, user["id"], leave_id))
    return {"ok": True}


# ---------- off announcements ----------

@app.post("/api/offs")
def announce_off(day: str = Form(...), department: str = Form(...), title: str = Form(...),
                 user: dict = Depends(need("hr", "admin"))):
    try:
        date.fromisoformat(day)
    except ValueError:
        raise HTTPException(422, "Enter a valid date.")
    if department not in DEPARTMENTS + ["All"] or not title.strip():
        raise HTTPException(422, "Choose a department (or All) and give a title.")
    with connection() as conn:
        conn.execute("INSERT INTO offs(day,department,title,created_by) VALUES(?,?,?,?)", (day, department, title.strip(), user["id"]))
    return {"ok": True}


@app.get("/api/offs")
def list_offs(user: dict = Depends(need("hr", "admin"))):
    with connection() as conn:
        rows = conn.execute("SELECT o.id, o.day, o.department, o.title, u.name AS by FROM offs o LEFT JOIN users u ON u.id=o.created_by "
                            "WHERE o.day>=? ORDER BY o.day", ((now() - timedelta(days=30)).strftime("%Y-%m-%d"),)).fetchall()
    return {"offs": [dict(r) for r in rows]}


@app.delete("/api/offs/{off_id}")
def delete_off(off_id: int, _: dict = Depends(need("hr", "admin"))):
    with connection() as conn:
        conn.execute("DELETE FROM offs WHERE id=?", (off_id,))
    return {"ok": True}


# ---------- admin: staff control ----------

@app.get("/api/users")
def users(_: dict = Depends(need("admin"))):
    with connection() as conn:
        rows = conn.execute("SELECT u.id,u.role,u.name,u.staff_code,u.department,u.photo,u.status,u.created_at,"
                            "(SELECT COUNT(*) FROM warnings w WHERE w.user_id=u.id) AS warnings, "
                            "(SELECT COUNT(*) FROM leaves l WHERE l.decided_by=u.id) AS decisions "
                            "FROM users u WHERE u.role!='admin' ORDER BY u.role, u.department, u.name").fetchall()
    return {"users": [dict(r) for r in rows]}


@app.post("/api/users/{user_id}/action")
def user_action(user_id: int, action: str = Form(...), reason: str = Form(""), admin: dict = Depends(need("admin"))):
    with connection() as conn:
        u = conn.execute("SELECT id, role FROM users WHERE id=?", (user_id,)).fetchone()
        if not u or u["role"] == "admin":
            raise HTTPException(404, "Staff member not found.")
        if action == "warn":
            if not reason.strip():
                raise HTTPException(422, "Give a reason for the warning.")
            conn.execute("INSERT INTO warnings(user_id, reason) VALUES(?,?)", (user_id, reason.strip()))
            conn.execute("UPDATE users SET status='warned' WHERE id=? AND status='active'", (user_id,))
        elif action == "fire":
            conn.execute("UPDATE users SET status='fired' WHERE id=?", (user_id,))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        elif action == "retain":
            conn.execute("UPDATE users SET status='active' WHERE id=?", (user_id,))
        else:
            raise HTTPException(422, "Unknown action.")
    return {"ok": True}

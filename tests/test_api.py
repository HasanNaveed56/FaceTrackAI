"""Role-flow smoke test with a fake face engine. Run: python -m unittest discover tests"""
import sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app.database as database
import main
from app.face_engine import FaceEngine, FaceEngineError


def frame(*ids):                      # a fake camera frame: the first bytes are the people in view
    return bytes(ids) + b"\xff" * 20


def vec(i):
    v = np.zeros(8, dtype=np.float32); v[i % 8] = 1.0
    return v


class Fake(FaceEngine):
    def __init__(self): pass
    def extract(self, raw):
        if raw[:1] == b"x": raise FaceEngineError("No face found.")
        return {"embedding": vec(raw[0]), "photo": "data:image/jpeg;base64,AAAA"}
    def detect_all(self, raw):
        ids = [b for b in raw[:4] if b < 200]
        return [{"embedding": vec(i), "box": [0.1, 0.1, 0.2, 0.2]} for i in ids]


class Flow(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp()); database.DATA_DIR, database.DB_PATH = tmp, tmp / "t.db"
        database.init_db(); main._engine = Fake(); self.c = TestClient(main.app)
        self.clock = datetime(2026, 10, 26, 9, 10)  # a Monday
        main.now = lambda: self.clock

    def reg(self, role, ident, code, **kw):
        d = {"name": f"{role}{ident}", "staff_code": code, "role": role, **kw}
        return self.c.post("/api/register", data=d, files=[("images", ("a.jpg", frame(ident), "image/jpeg"))])

    def login(self, ident):
        return self.c.post("/api/face-login", files={"image": ("a.jpg", frame(ident), "image/jpeg")})

    def scan(self, token, *ids):
        return self.c.post("/api/camera/scan", files={"image": ("a.jpg", frame(*ids), "image/jpeg")},
                           headers={"Authorization": "Bearer " + token})

    def test_registration_fields_depend_on_role(self):
        self.assertEqual(self.reg("employee", 1, "E1").status_code, 422)                       # employee needs a department
        self.assertEqual(self.reg("employee", 1, "E1", department="Backend Developer").status_code, 200)
        self.assertEqual(self.reg("hr", 2, "H1").status_code, 403)                             # HR needs the key, no department
        self.assertEqual(self.reg("hr", 2, "H1", key=main.REGISTRATION_KEY).status_code, 200)
        self.assertEqual(self.reg("employee", 4, "e1", department="QA Engineer").status_code, 409)   # staff code already used
        self.assertEqual(self.reg("employee", 1, "E9", department="QA Engineer").status_code, 409)   # face already registered
        self.assertEqual(self.reg("employee", 5, "bad code!", department="QA Engineer").status_code, 422)
        me = self.c.get("/api/me", headers={"Authorization": "Bearer " + self.login(2).json()["token"]}).json()["user"]
        self.assertEqual((me["role"], me["department"], me["staff_code"]), ("hr", "Human Resources", "H1"))

    def test_face_login_only(self):
        self.reg("employee", 1, "E1", department="Backend Developer")
        self.assertEqual(self.c.post("/api/login", data={"email": "a@b.c", "password": "secret1"}).status_code, 404)  # no password login
        self.assertEqual(self.login(1).json()["user"]["staff_code"], "E1")
        self.assertEqual(self.login(6).status_code, 404)                                       # unknown face
        self.assertEqual(self.c.post("/api/face-login", files={"image": ("a.jpg", b"x" * 20, "image/jpeg")}).status_code, 422)

    def test_auto_attendance_and_hr_only_camera(self):
        e = self.reg("employee", 1, "E1", department="Backend Developer").json()["token"]
        self.reg("employee", 4, "E2", department="QA Engineer")
        h = self.reg("hr", 2, "H1", key=main.REGISTRATION_KEY).json()["token"]
        a = self.reg("admin", 3, "A1", key=main.REGISTRATION_KEY).json()["token"]
        self.assertEqual(self.scan(e, 1).status_code, 403)                                      # employee cannot run the camera
        self.assertEqual(self.scan(a, 1).status_code, 403)                                      # nor admin
        r = self.scan(h, 1, 6).json()["results"]                                                # two faces in one frame
        self.assertEqual([x["status"] for x in r], ["checkin", "unknown"])
        self.assertEqual(self.scan(h, 1).json()["results"][0]["status"], "already")             # no duplicate
        self.assertEqual(self.scan(h, 3).json()["results"][0]["status"], "skip")                # admin has no attendance
        self.clock = self.clock.replace(hour=9, minute=16)
        self.assertEqual(self.scan(h, 4).json()["results"][0]["status"], "late")                # after 09:15: nothing recorded
        self.clock = self.clock.replace(hour=16, minute=44)
        self.assertEqual(self.scan(h, 1).json()["results"][0]["status"], "already")             # too early for check-out
        self.clock = self.clock.replace(hour=16, minute=50)
        self.assertEqual(self.scan(h, 1).json()["results"][0]["status"], "checkout")
        rec = self.c.get("/api/my-attendance", headers={"Authorization": "Bearer " + e}).json()["records"]
        self.assertEqual((len(rec), rec[0]["check_in"], rec[0]["check_out"]), (1, "09:10:00", "16:50:00"))
        today = {r["name"]: r["status"] for r in self.c.get("/api/today", headers={"Authorization": "Bearer " + h}).json()["rows"]}
        self.assertEqual(today["employee4"], "Absent")
        self.clock = datetime(2026, 11, 1, 9, 0)                                                # Sunday
        self.assertEqual(self.scan(h, 1).json()["results"][0]["status"], "off")

    def test_leave_and_admin_actions(self):
        e = self.reg("employee", 1, "E1", department="Backend Developer").json()["token"]
        h = self.reg("hr", 2, "H1", key=main.REGISTRATION_KEY).json()["token"]
        a = self.reg("admin", 3, "A1", key=main.REGISTRATION_KEY).json()["token"]
        H = {k: {"Authorization": "Bearer " + v} for k, v in (("e", e), ("h", h), ("a", a))}
        lv = {"title": "Trip", "reason": "Family", "from_day": "2026-10-26", "to_day": "2026-10-26"}
        self.assertEqual(self.c.post("/api/leaves", data=lv, headers=H["e"]).status_code, 200)
        lid = self.c.get("/api/leaves", headers=H["h"]).json()["leaves"][0]["id"]
        self.assertEqual(self.c.post(f"/api/leaves/{lid}/decide", data={"decision": "approved"}, headers=H["e"]).status_code, 403)
        self.assertEqual(self.c.post(f"/api/leaves/{lid}/decide", data={"decision": "approved"}, headers=H["h"]).status_code, 200)
        self.assertEqual(self.scan(h, 1).json()["results"][0]["status"], "leave")               # approved leave: no attendance
        self.assertEqual(self.c.get("/api/users", headers=H["h"]).status_code, 403)
        users = self.c.get("/api/users", headers=H["a"]).json()["users"]
        emp = [u for u in users if u["role"] == "employee"][0]
        self.assertEqual(self.c.post(f"/api/users/{emp['id']}/action", data={"action": "fire"}, headers=H["a"]).status_code, 200)
        self.assertEqual(self.c.get("/api/me", headers=H["e"]).status_code, 401)
        self.assertEqual(self.login(1).status_code, 403)                                        # fired: face login refused
        self.assertEqual(self.scan(h, 1).json()["results"][0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()

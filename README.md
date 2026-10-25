<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:00ff99,100:0d1117&height=190&section=header&text=FaceTrack%20AI&fontSize=54&fontColor=ffffff&fontAlignY=40&desc=Face%20recognition%20attendance%20for%20teams&descSize=18&descAlignY=60&animation=fadeIn" alt="FaceTrack AI banner" />

![Python](https://img.shields.io/badge/Python-3.10+-0d1117?style=for-the-badge&logo=python&logoColor=00ff99)
![FastAPI](https://img.shields.io/badge/FastAPI-0d1117?style=for-the-badge&logo=fastapi&logoColor=00ff99)
![OpenCV](https://img.shields.io/badge/OpenCV-0d1117?style=for-the-badge&logo=opencv&logoColor=00ff99)
![SQLite](https://img.shields.io/badge/SQLite-0d1117?style=for-the-badge&logo=sqlite&logoColor=00ff99)

### [🚀 Live Demo](https://facetrackai-8630b.containers.snapdeploy.app/)

*Employees, HR and admins check in and out with their face. No cards, no passwords at the door.*

</div>

---

## ✨ Features

| | |
|---|---|
| 🧑‍💻 **Face check-in / check-out** | Each person is verified against their own enrolled face. |
| 🔐 **Role-based accounts** | Separate register and login for Employee, HR and Admin. |
| ⏰ **Attendance rules** | Check-in closes at **09:15** (later = no attendance), check-out opens at **16:45**. |
| 🗓️ **Off days** | Sundays, public holidays and department-wise off announcements are blocked automatically. |
| 📝 **Leave workflow** | Employees apply with title, reason and dates; HR approves. HR's own leaves go to Admin. |
| ⚠️ **Staff control** | Admin can warn, fire or retain staff. Fired accounts lose access immediately. |

---

## 👥 Dashboards

### 🧑 Employee
- Check in / out with the camera and a live clock
- Own attendance with date and time down to the second
- Leave requests and their status
- Company rules: yearly holidays, Sunday off, leave policy
- Warnings and upcoming offs

### 🧑‍💼 HR
- Today's check-ins and check-outs for every employee (Present, Not yet, Absent, On leave, Off)
- Off announcements for one department or everyone
- Leave requests with the employee's department, Approve / Reject

### 🛡️ Admin
- Monitors both HR and employees
- Warn (with a reason), Fire or Retain any staff member
- See every leave and off announcement, and how many leaves each HR has decided

---

## 🚀 Run locally

```bash
./run_server.sh        # macOS / Linux
run_server.bat         # Windows
```

Open **http://localhost:8000**. The first run installs the dependencies and downloads two pretrained models (about 40 MB) from the OpenCV Zoo. Python 3.10 or newer is required. The camera only works on `localhost` or HTTPS.

**HR and admin sign-up** needs a staff code. Set your own before going live:

```bash
STAFF_CODE="your-secret-code" ./run_server.sh      # default: facetrack-staff
```

---

## 🧠 How recognition works

```
Camera frame ──► YuNet (detect face + 5 landmarks) ──► SFace (align + embed)
                                                          │
                          cosine similarity with the logged-in user's face
                                                          │
                              ≥ 0.363  ──►  check-in / check-out recorded
```

1. **YuNet** finds exactly one face and its landmarks.
2. **SFace** aligns the face and produces an embedding.
3. The embedding is compared with the logged-in user's enrolled face. It must score at least **0.363**, the threshold recommended by OpenCV for SFace.
4. Registration rejects blurry or distant faces, photos with more than one face, and a face that is already registered under another account.

---

## 🗂️ Project structure

```
FaceTrackAI/
├── main.py              # FastAPI: auth, attendance, leaves, offs, admin
├── app/
│   ├── face_engine.py   # detection and recognition
│   └── database.py      # SQLite schema
├── static/              # index.html, style.css, app.js (dashboards)
├── models/              # YuNet and SFace ONNX models
└── tests/               # face engine + role-flow tests
```

---

## ⚠️ Limits

- **No liveness detection.** A printed photo or a phone screen can fool it. Use it with a person supervising.
- Passwords are stored as salted PBKDF2 hashes, but serve the app over **HTTPS** and change `STAFF_CODE` before exposing it.
- `data/facetrack.db` holds each person's face embedding and a small cropped photo. Treat it as personal data.
- Accuracy depends on lighting and camera quality. Tune `MATCH_THRESHOLD` in `app/face_engine.py` on your own team.
- Eid and other moon-based holidays are not hardcoded; HR announces them as offs.

---

## 🧪 Tests

```bash
python tests/test_face_engine.py     # matching logic, no models needed
python tests/test_api.py             # role flow with a fake face engine
```

---

<div align="center">

Built by [Hasan Naveed](https://github.com/HasanNaveed56) · **Code. Create. Innovate.**

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,100:00ff99&height=100&section=footer" alt="Footer" />

</div>

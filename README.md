# FaceTrack AI

Face recognition attendance for staff. Everything runs on the local computer.

## Run

```
run_server.bat         # Windows
./run_server.sh        # macOS / Linux
```

Open http://localhost:8000. First run downloads two pretrained models (about 40 MB). Python 3.10+. The camera only works on `localhost` or HTTPS.

## How it works

- **Login is by face only.** There are no passwords. The login screen opens the camera and logs you in when your face matches a registered account.
- **Register** (name, staff code, one camera photo; up to 2 more are optional). Fields depend on the role:
  - Employee: name, staff code, department.
  - HR / Admin: name, staff code, registration key (env `REGISTRATION_KEY`, default `facetrack-staff`). No department.
- **Attendance camera (HR only).** HR starts and stops it from the *Attendance camera* page. While it is on, every registered face it sees is marked automatically: first sighting until 09:15 = check-in, a sighting from 16:45 = check-out. After 09:15 with no check-in = no attendance. Sundays, listed holidays, HR-announced offs and approved leave are skipped. The camera keeps running while HR uses other pages, and stops on Stop or Logout.
- **Dashboards**
  - Employee: My attendance, Leave, Company rules.
  - HR: Today, Attendance camera, Off announcements, Leave requests, My attendance, Company rules.
  - Admin: Overview, Staff control (warn / fire / retain), Leaves, Off announcements, Company rules.
- Employee leaves go to HR, HR leaves go to admin.

## Recognition

YuNet detects faces and landmarks, SFace aligns and embeds them (128 numbers), and the embedding is matched by cosine similarity. Attendance matching uses 0.363 (the OpenCV recommendation); face login uses a stricter 0.45 and must beat the runner-up by 0.05. Registration rejects blurry or distant photos and a face that matches an existing account at 0.55 or more.

Files: `app/face_engine.py` (recognition), `app/database.py` (SQLite), `main.py` (API), `static/` (interface).

## Limits

- No liveness detection: a printed photo or phone screen can fool the camera and the face login. Run the attendance camera where a person can see it.
- Face login opens an account, so keep `REGISTRATION_KEY` secret and change the default before real use.
- `data/facetrack.db` stores face embeddings and a small face crop per person. Treat it as personal data.
- If an older database (email/password version) is found, it is kept as `data/facetrack.old.db` and a new one is created.

## Tests

```
python -m unittest discover tests
```

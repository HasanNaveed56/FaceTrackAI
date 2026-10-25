# FaceTrack AI: Face Recognition Attendance System

## 1. Problem
Paper roll calls take lecture time and allow proxy attendance. This project marks attendance from a webcam using face recognition, running entirely on a local computer.

## 2. Approach
| Step | Method |
|---|---|
| Detection | YuNet (OpenCV Zoo), gives a face box and 5 landmarks |
| Alignment | SFace `alignCrop` to a 112x112 face |
| Embedding | SFace, 128 numbers per face, scaled to unit length |
| Matching | Cosine similarity against all enrolled students; accept if >= 0.363 and ahead of the runner-up by 0.05 |
| Storage | SQLite: classes, students (embedding + small face photo), attendance |

Both models are pretrained and used as published; no training was done in this project. The 0.363 threshold comes from the OpenCV SFace documentation.

## 3. Workflow
1. Enrol: name, roll number, 1-3 photos. Photos are checked for exactly one face, minimum size and sharpness. Several photos are averaged into one embedding. A face already enrolled under another roll number is refused.
2. Scan: choose a class and start the camera. A frame is sent about every 1.5 seconds. A recognised student is marked present for that class and day; a repeat scan reports "already marked".
3. Review: Records tab filters by name, class and date and exports CSV.

## 4. Implementation notes
- FastAPI backend, plain HTML/CSS/JavaScript frontend with no external libraries.
- A lock protects the OpenCV models because requests run in parallel threads.
- A database uniqueness rule (student, class, day) prevents duplicate attendance even under concurrent scans.

## 5. Evaluation
Automated tests cover the matching logic (similarity, thresholding, ambiguity, averaging) and the API flow with a stand-in engine. **Recognition accuracy on real faces has not been measured in this report.** To report it honestly, enrol a group of volunteers, take separate test photos, and record how many are correctly accepted, wrongly rejected and wrongly matched. Add those numbers here. The published SFace results (LFW benchmark) are in the OpenCV Zoo model card and may be cited as the model's published result, not as this system's result.

## 6. Limitations
- No liveness or anti-spoofing: a photo or screen can fool it.
- No user login.
- One embedding per student; large changes in appearance may need re-enrolment.
- Performance and accuracy depend on lighting and camera; speed was not benchmarked.

## 7. Future work
Add liveness detection (for example a blink or head-turn challenge), user accounts, and an accuracy study on a real group.

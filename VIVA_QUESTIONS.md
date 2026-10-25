# Likely viva questions

**1. Why YuNet and SFace?**
Both are small pretrained models from the OpenCV Zoo that run on a normal CPU and ship with OpenCV, so no GPU or extra framework is needed. YuNet also returns five landmarks, which SFace uses to align the face.

**2. What does the embedding mean and why cosine similarity?**
SFace turns an aligned face into 128 numbers. Faces of the same person give vectors pointing in similar directions, so the angle (cosine similarity) between them measures how alike two faces are. We scale vectors to length 1, so the score is just their dot product.

**3. How was the 0.363 threshold chosen?**
It is the value recommended in the OpenCV SFace documentation. It trades wrong accepts against wrong rejects, and should be tuned on the real students and camera.

**4. How are duplicate attendance records prevented?**
The database enforces one record per student, class and day, so a second scan returns "already marked".

**5. How do you avoid matching the wrong student?**
The best score must pass the threshold and beat the second best by 0.05; otherwise the scan is rejected as unclear. Enrolment also refuses a face that already exists.

**6. Can someone fool it with a photo?**
Yes. There is no liveness detection. The blur check only rejects poor images; it is not an anti-spoofing measure. Adding a blink or head-turn challenge is the planned improvement.

**7. What personal data is stored?**
Each student's name, roll number, a 128-number embedding and one small cropped face photo (used to show who was recognised). Uploaded full photos and camera frames are not saved. The database is not encrypted and the app has no login, so it should run on a trusted machine.

**8. How would you measure accuracy?**
Enrol volunteers, collect separate test photos in realistic conditions, and count correct accepts, false rejects and false matches at the chosen threshold.

"""Face detection (YuNet) and recognition (SFace) using OpenCV's pretrained ONNX models."""

import base64
import threading
from pathlib import Path

import cv2
import numpy as np

MODELS = Path(__file__).resolve().parents[1] / "models"
DETECTOR_PATH = MODELS / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_PATH = MODELS / "face_recognition_sface_2021dec.onnx"

# 0.363 is the cosine threshold recommended by the OpenCV SFace documentation.
MATCH_THRESHOLD = 0.363
# If the runner-up is this close to the best match, the result is treated as ambiguous.
AMBIGUITY_MARGIN = 0.05
MIN_FACE_PX = 80          # smallest accepted face width in the source image
MIN_SHARPNESS = 25.0      # Laplacian variance of the aligned crop; below this the face is too blurry
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class FaceEngineError(Exception):
    pass


class FaceEngine:
    def __init__(self):
        if not DETECTOR_PATH.exists() or not RECOGNIZER_PATH.exists():
            raise FaceEngineError("Face models are missing. Run: python download_models.py")
        self.detector = cv2.FaceDetectorYN.create(
            str(DETECTOR_PATH), "", (320, 320), score_threshold=0.85, nms_threshold=0.3, top_k=50
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(RECOGNIZER_PATH), "")
        self._lock = threading.Lock()  # OpenCV model objects are not thread-safe

    @staticmethod
    def decode_image(raw: bytes) -> np.ndarray:
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise FaceEngineError("Image is empty or larger than 8 MB.")
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceEngineError("Could not read the image. Use a JPEG or PNG file.")
        if min(image.shape[:2]) < 96:
            raise FaceEngineError("Image is too small.")
        return image

    def extract(self, raw: bytes) -> dict:
        """Return the unit-length embedding and a small face photo for exactly one face."""
        image = self.decode_image(raw)
        h, w = image.shape[:2]
        with self._lock:
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(image)
            if faces is None or len(faces) == 0:
                raise FaceEngineError("No face found. Face the camera in good light.")
            if len(faces) > 1:
                raise FaceEngineError("More than one face in view. Only one person at a time.")
            face = faces[0]
            if face[2] < MIN_FACE_PX:
                raise FaceEngineError("Face is too far away. Move closer to the camera.")
            aligned = self.recognizer.alignCrop(image, face)
            sharpness = float(cv2.Laplacian(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
            if sharpness < MIN_SHARPNESS:
                raise FaceEngineError("Image is blurry. Hold still and try again.")
            feature = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)

        norm = float(np.linalg.norm(feature))
        if norm == 0:
            raise FaceEngineError("Could not compute a face signature. Try again.")
        ok, buf = cv2.imencode(".jpg", aligned, [cv2.IMWRITE_JPEG_QUALITY, 85])
        photo = "data:image/jpeg;base64," + base64.b64encode(buf).decode()
        return {"embedding": feature / norm, "photo": photo}

    def detect_all(self, raw: bytes) -> list[dict]:
        """Every usable face in a camera frame (used by the always-on attendance camera).

        Returns [{'embedding', 'box': [x, y, w, h] as 0-1 fractions of the frame}]. Faces that are
        too small or blurry are skipped instead of raising, because a live camera sees many bad frames.
        """
        image = self.decode_image(raw)
        h, w = image.shape[:2]
        found = []
        with self._lock:
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(image)
            for face in (faces if faces is not None else []):
                if face[2] < MIN_FACE_PX:
                    continue
                aligned = self.recognizer.alignCrop(image, face)
                if float(cv2.Laplacian(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) < MIN_SHARPNESS:
                    continue
                feature = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
                norm = float(np.linalg.norm(feature))
                if norm == 0:
                    continue
                box = [max(0.0, float(face[0]) / w), max(0.0, float(face[1]) / h), float(face[2]) / w, float(face[3]) / h]
                found.append({"embedding": feature / norm, "box": box})
        return found

    @staticmethod
    def combine(embeddings: list[np.ndarray]) -> np.ndarray:
        """Average several samples of one person into a single unit-length embedding."""
        mean = np.mean(np.stack(embeddings), axis=0)
        norm = float(np.linalg.norm(mean))
        if norm == 0:
            raise FaceEngineError("Could not combine the samples.")
        return (mean / norm).astype(np.float32)

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float32).reshape(-1)
        b = np.asarray(b, dtype=np.float32).reshape(-1)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        return -1.0 if denom == 0 else float(np.dot(a, b) / denom)

    @staticmethod
    def best_match(query: np.ndarray, students: list[dict], threshold: float = MATCH_THRESHOLD):
        """1:N search. Returns {'student', 'similarity'}, {'ambiguous': True} or None."""
        if not students:
            return None
        query = np.asarray(query, dtype=np.float32).reshape(-1)
        query = query / (np.linalg.norm(query) or 1.0)
        db = np.stack([np.frombuffer(s["embedding"], dtype=np.float32) for s in students])
        db = db / np.maximum(np.linalg.norm(db, axis=1, keepdims=True), 1e-12)
        scores = db @ query
        order = np.argsort(scores)[::-1]
        best = float(scores[order[0]])
        if best < threshold:
            return None
        if len(order) > 1 and best - float(scores[order[1]]) < AMBIGUITY_MARGIN and float(scores[order[1]]) >= threshold:
            return {"ambiguous": True}
        return {"student": students[int(order[0])], "similarity": best}

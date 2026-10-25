"""Downloads the two pretrained ONNX models from the OpenCV Zoo:
YuNet (face detection) and SFace (face recognition)."""

from pathlib import Path
from urllib.request import Request, urlopen

MODELS = Path(__file__).resolve().parent / "models"
MODELS.mkdir(exist_ok=True)

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
FILES = {
    "face_detection_yunet_2023mar.onnx": f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def main():
    for name, url in FILES.items():
        target = MODELS / name
        if target.exists() and target.stat().st_size > 100_000:
            print(f"OK       {name}")
            continue
        print(f"Download {name} ...")
        try:
            with urlopen(Request(url, headers={"User-Agent": "FaceTrackAI"}), timeout=120) as r, target.open("wb") as out:
                while chunk := r.read(1 << 20):
                    out.write(chunk)
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise SystemExit(f"Failed to download {name}: {exc}\nDownload it manually from {url} into the models folder.")
        print(f"Saved    {name} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

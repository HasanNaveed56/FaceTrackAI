import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.face_engine import FaceEngine, FaceEngineError  # noqa: E402


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def student(name, vec):
    return {"name": name, "embedding": unit(vec).tobytes()}


class SimilarityTests(unittest.TestCase):
    def test_identical(self):
        v = [0.5, 0.5, 0.5, 0.5]
        self.assertAlmostEqual(FaceEngine.similarity(v, v), 1.0, places=5)

    def test_orthogonal_and_opposite(self):
        self.assertAlmostEqual(FaceEngine.similarity([1, 0], [0, 1]), 0.0, places=5)
        self.assertAlmostEqual(FaceEngine.similarity([1, 0], [-1, 0]), -1.0, places=5)

    def test_zero_vector(self):
        self.assertEqual(FaceEngine.similarity([0, 0, 0], [1, 2, 3]), -1.0)


class MatchTests(unittest.TestCase):
    def test_picks_closest_student(self):
        db = [student("A", [1, 0, 0]), student("B", [0, 1, 0])]
        r = FaceEngine.best_match(unit([0.95, 0.1, 0]), db, threshold=0.5)
        self.assertEqual(r["student"]["name"], "A")

    def test_below_threshold_is_unknown(self):
        db = [student("A", [1, 0, 0])]
        self.assertIsNone(FaceEngine.best_match(unit([0, 1, 0]), db, threshold=0.5))

    def test_two_near_identical_students_are_ambiguous(self):
        db = [student("A", [1, 0.01, 0]), student("B", [1, 0.02, 0])]
        r = FaceEngine.best_match(unit([1, 0, 0]), db, threshold=0.5)
        self.assertTrue(r.get("ambiguous"))

    def test_empty_database(self):
        self.assertIsNone(FaceEngine.best_match(unit([1, 0]), [], threshold=0.5))


class CombineTests(unittest.TestCase):
    def test_average_is_unit_length(self):
        out = FaceEngine.combine([unit([1, 0, 0]), unit([0.8, 0.6, 0])])
        self.assertAlmostEqual(float(np.linalg.norm(out)), 1.0, places=5)

    def test_opposite_samples_fail(self):
        with self.assertRaises(FaceEngineError):
            FaceEngine.combine([unit([1, 0]), unit([-1, 0])])


if __name__ == "__main__":
    unittest.main()

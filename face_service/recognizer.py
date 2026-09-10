"""Face recognizer backed by OpenCV's built-in SFace + YuNet.

Replaces the DeepFace/TensorFlow/PyTorch stack: same public API
(``enroll_from_dir`` / ``load`` / ``verify_frame``), same on-disk embedding
file, same cosine-*distance* threshold semantics — but the only dependency is
opencv-python, and the models are 227 KB (detect) + 37 MB (embed) instead of
~500 MB of frameworks.

Distances stay comparable to the old code in *direction* only: SFace has its
own scale, so ``threshold`` must be retuned (see ``DEFAULT_THRESHOLD``).
Embeddings are 128-d, so enrollments made with the DeepFace build are
rejected on load and must be rebuilt.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .config import Config, EMBED_PATH, ENROLL_DIR
from .detector import yunet_model_path

log = logging.getLogger(__name__)

EMBED_DIM = 128
# Cosine *distance* cutoff (1 - similarity). OpenCV publishes 0.637 for SFace;
# 0.55 is stricter and still leaves a wide margin on real webcam frames.
DEFAULT_THRESHOLD = 0.55

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SFACE_MODEL = _REPO_ROOT / "models" / "face_recognition_sface_2021dec.onnx"


def sface_model_path() -> Path:
    if not _SFACE_MODEL.exists():
        raise FileNotFoundError(
            f"SFace model not found at {_SFACE_MODEL}. "
            "Run: python installer/download_weights.py"
        )
    return _SFACE_MODEL


class Recognizer:
    """Face recognizer over a set of reference embeddings."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._refs: np.ndarray | None = None  # shape (N, 128)
        self._det: cv2.FaceDetectorYN | None = None
        self._rec: cv2.FaceRecognizerSF | None = None
        self._det_size: tuple[int, int] | None = None

    # ---------- models ----------

    def _detector(self, width: int, height: int) -> cv2.FaceDetectorYN:
        if self._det is None:
            self._det = cv2.FaceDetectorYN.create(
                str(yunet_model_path()), "", (width, height), 0.9, 0.3, 5000
            )
            self._det_size = (width, height)
        elif self._det_size != (width, height):
            self._det.setInputSize((width, height))
            self._det_size = (width, height)
        return self._det

    def _embedder(self) -> cv2.FaceRecognizerSF:
        if self._rec is None:
            self._rec = cv2.FaceRecognizerSF.create(str(sface_model_path()), "")
        return self._rec

    def _detect(self, bgr: np.ndarray) -> np.ndarray | None:
        """Largest face row from YuNet (x, y, w, h, landmarks..., score)."""
        h, w = bgr.shape[:2]
        _, faces = self._detector(w, h).detect(bgr)
        if faces is None or len(faces) == 0:
            return None
        return faces[np.argmax(faces[:, 2] * faces[:, 3])]  # widest*tallest box

    def _embed_face(self, bgr: np.ndarray, face: np.ndarray) -> np.ndarray:
        rec = self._embedder()
        return rec.feature(rec.alignCrop(bgr, face)).flatten().astype(np.float32)

    def _embed(self, bgr: np.ndarray) -> np.ndarray | None:
        """Largest face in the frame as a 128-d vector, or None if no face."""
        face = self._detect(bgr)
        return None if face is None else self._embed_face(bgr, face)

    # ---------- enrollment ----------

    def enroll_from_dir(self, directory: Path = ENROLL_DIR) -> int:
        directory.mkdir(parents=True, exist_ok=True)
        images = [
            p for p in directory.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ]
        if not images:
            raise RuntimeError(f"No enroll images in {directory}")

        vecs: list[np.ndarray] = []
        for p in sorted(images):
            img = cv2.imread(str(p))
            if img is None:
                log.warning("unreadable %s", p.name)
                continue
            vec = self._embed(img)
            if vec is None:
                log.warning("no face in %s", p.name)
                continue
            vecs.append(vec)
            log.info("enrolled %s", p.name)

        if not vecs:
            raise RuntimeError("No face found in enroll images")
        embeds = np.stack(vecs, axis=0)
        EMBED_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.savez(EMBED_PATH, embeddings=embeds)
        self._refs = embeds
        return len(vecs)

    def load(self) -> bool:
        if not EMBED_PATH.exists():
            return False
        refs = np.load(EMBED_PATH)["embeddings"]
        if refs.ndim != 2 or refs.shape[1] != EMBED_DIM:
            raise RuntimeError(
                f"{EMBED_PATH} holds {refs.shape[-1]}-d embeddings from an older "
                f"build; re-enroll to rebuild them as {EMBED_DIM}-d"
            )
        self._refs = refs
        return True

    # ---------- verification ----------

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na = a / (np.linalg.norm(a) + 1e-9)
        nb = b / (np.linalg.norm(b) + 1e-9)
        return float(1.0 - np.dot(na, nb))  # cosine *distance*

    def verify_frame(self, bgr: np.ndarray) -> tuple[bool, float, bool]:
        """(is_match, best_distance, is_real). is_real False if spoof-flagged."""
        if self._refs is None and not self.load():
            raise RuntimeError("No enrollment found. Run enroll first.")

        face = self._detect(bgr)
        if face is None:
            return False, 1.0, True

        if self.cfg.anti_spoofing:
            from .liveness import is_live
            live, reason = is_live(bgr, tuple(face[:4]))
            if not live:
                log.info("liveness rejected: %s", reason)
                return False, 1.0, False

        emb = self._embed_face(bgr, face)
        best = min(self._cosine(emb, r) for r in self._refs)  # type: ignore[union-attr]
        return best <= self.cfg.threshold, best, True

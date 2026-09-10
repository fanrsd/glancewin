"""Regression check for the anti-spoof path.

The liveness model is unforgiving about preprocessing: normalising to [0, 1],
or reading the wrong class index, makes it answer confidently and wrongly on
*every* frame — real faces rejected, or worse, fakes accepted. Neither
mistake is visible from a live smoke test alone.

So assert against upstream's own labelled samples: the two fakes must be
rejected, the real one accepted, and the two must be far apart.

    python -m tools.check_liveness
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from face_service.detector import yunet_model_path
from face_service.liveness import REAL_CLASS, is_live, scores

SAMPLE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "liveness-samples"
BASE = ("https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/"
        "raw/master/images/sample/")
SAMPLES = {"image_F1.jpg": False, "image_F2.jpg": False, "image_T1.jpg": True}
MIN_SEPARATION = 0.5


def _sample(name: str) -> np.ndarray:
    dest = SAMPLE_DIR / name
    if not dest.exists():
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(BASE + name, dest)
    img = cv2.imread(str(dest))
    assert img is not None, f"cannot read {dest}"
    return img


def _largest_face(img: np.ndarray) -> tuple[float, float, float, float]:
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(str(yunet_model_path()), "", (w, h), 0.8, 0.3, 5000)
    _, faces = det.detect(img)
    assert faces is not None and len(faces), "no face detected in sample"
    return tuple(faces[np.argmax(faces[:, 2] * faces[:, 3])][:4])


def main() -> int:
    failures: list[str] = []
    live_prob: dict[str, float] = {}

    for name, want_live in SAMPLES.items():
        img = _sample(name)
        box = _largest_face(img)
        p = scores(img, box)
        got_live, reason = is_live(img, box)

        assert p.shape == (3,), f"{name}: expected 3 classes, got {p.shape}"
        assert abs(p.sum() - 1.0) < 1e-6, f"{name}: softmax does not sum to 1"

        live_prob[name] = float(p[REAL_CLASS])
        print(f"  {name}: live={got_live} p={np.round(p, 3)} ({reason})")
        if got_live != want_live:
            failures.append(f"{name}: expected live={want_live}, got {got_live}")

    gap = live_prob["image_T1.jpg"] - max(live_prob["image_F1.jpg"],
                                          live_prob["image_F2.jpg"])
    if gap < MIN_SEPARATION:
        failures.append(
            f"real/fake separation only {gap:.2f} (want >= {MIN_SEPARATION}); "
            "check that scores() feeds raw 0-255 BGR and REAL_CLASS is right"
        )

    if failures:
        print("\nFAIL")
        for f in failures:
            print("  -", f)
        return 1
    print(f"\nOK: fakes rejected, real accepted, separation {gap:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Is the webcam actually usable? Answers in one line per backend.

    python -m tools.camera_check

Distinguishes the three states that look identical from the GUI:
  * cannot open        -> device off, kill switch, or held by another app
  * opens, all black   -> privacy shutter closed (or the camera key is off)
  * opens with light   -> fine; if verify still fails, it is recognition
"""
from __future__ import annotations

import sys

import cv2
import numpy as np

BACKENDS = (("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF), ("ANY", cv2.CAP_ANY))
FRAMES = 20
DARK = 5.0


def probe(index: int) -> int:
    worst = 2
    for name, api in BACKENDS:
        cap = cv2.VideoCapture(index, api)
        if not cap.isOpened():
            cap.release()
            print(f"{name:6}: cannot open device {index}")
            continue
        means = []
        for _ in range(FRAMES):
            ok, frame = cap.read()
            if ok and frame is not None:
                means.append(float(np.asarray(frame).mean()))
        cap.release()
        if not means:
            print(f"{name:6}: opened but delivered no frames")
            continue
        peak = max(means)
        state = "BLACK" if peak < DARK else "ok"
        print(f"{name:6}: {len(means)}/{FRAMES} frames, brightness "
              f"min={min(means):.1f} max={peak:.1f} -> {state}")
        worst = min(worst, 0 if peak >= DARK else 1)
    return worst


def main() -> int:
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    rc = probe(index)
    print()
    if rc == 0:
        print("Camera works. If unlock still fails, the problem is recognition,")
        print("not the camera: python -m tools.pipe_test verify")
    elif rc == 1:
        print("Camera streams only black frames.")
        print("Open the privacy shutter, or press the camera key (F10 on ASUS).")
    else:
        print("Camera cannot be opened at all.")
        print("Close apps that use it, then: tools\\reset-camera.ps1 (as Administrator)")
    return rc


if __name__ == "__main__":
    sys.exit(main())

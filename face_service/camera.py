from __future__ import annotations
import time
import cv2
import numpy as np


class Camera:
    """Thin wrapper over cv2.VideoCapture with open/close safety."""

    def __init__(self, index: int = 0, warmup_frames: int = 10):
        self.index = index
        self.warmup_frames = warmup_frames
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        if self._cap is not None:
            return
        last_err: str | None = None
        # Three attempts per backend, because Windows webcam drivers often
        # report ``isOpened=True`` from a handle the previous process (or
        # a killed enroll wizard) didn't release cleanly. Releasing the
        # zombie capture + waiting a beat is enough for DirectShow to
        # hand the real device back.
        for attempt in range(3):
            for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
                cap = cv2.VideoCapture(self.index, backend)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok = False
                for _ in range(5):
                    ret, _ = cap.read()
                    if ret:
                        ok = True
                        break
                    time.sleep(0.1)
                if ok:
                    self._cap = cap
                    self._warmup(cap)
                    return
                last_err = (f"attempt={attempt} backend={backend} "
                            f"isOpened={cap.isOpened()}")
                cap.release()
            if attempt < 2:
                time.sleep(1.0)  # let the driver flush stuck handles
        raise RuntimeError(f"Cannot open camera index {self.index} ({last_err})")

    # This webcam opens black and then ramps its auto-exposure over a
    # dozen frames. Burning a fixed count returned mid-ramp, where the
    # frame is lit but too dark for YuNet, so a verify saw no face at all
    # (distance 1.0). Wait for brightness to stop changing instead.
    DARK_MEAN = 5.0
    SETTLE_RATIO = 0.08       # <8% change between frames counts as settled
    SETTLE_FRAMES = 3         # ...for this many frames in a row

    def _warmup(self, cap: cv2.VideoCapture) -> None:
        budget = max(self.warmup_frames, 1) * 6
        prev = None
        settled = 0
        for i in range(budget):
            ok, frame = cap.read()
            time.sleep(0.03)
            if not ok or frame is None:
                continue
            mean = float(frame.mean())
            if mean <= self.DARK_MEAN:
                prev, settled = None, 0
                continue
            if prev is not None and abs(mean - prev) / max(prev, 1.0) < self.SETTLE_RATIO:
                settled += 1
                if settled >= self.SETTLE_FRAMES and i >= self.warmup_frames:
                    return
            else:
                settled = 0
            prev = mean

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def read(self) -> np.ndarray | None:
        assert self._cap is not None, "Camera not opened"
        ok, frame = self._cap.read()
        return frame if ok else None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

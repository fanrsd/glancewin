"""Anti-spoofing (liveness) via MiniFASNetV2, run through OpenCV's DNN module.

Same model DeepFace used for ``anti_spoofing=True`` (Silent-Face-Anti-Spoofing
by minivision-ai), as a 1.7 MB ONNX graph — so PyTorch is no longer a
dependency.

Two details are easy to get wrong and both were verified against upstream's
labelled samples (``images/sample/image_{F1,F2,T1}.jpg``), see
``spike/liveness_gate.py``:

* Input is BGR in the raw **0-255** range. Dividing by 255 saturates the
  network: every input, real or fake, comes back as the same class.
* The **real** class is index **1** — matching upstream's ``if label == 1:
  Real Face``. (Some ONNX re-uploads document [live, print, replay]; that
  ordering does not reproduce upstream's own results.)

Blocks printed photos and photos/videos shown on a screen. Does NOT block
3-D masks. A 2-D webcam cannot; treat this as convenience, not security.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MODEL = _REPO_ROOT / "models" / "2.7_80x80_MiniFASNetV2.onnx"

INPUT_SIZE = 80
# The model file name upstream is "2.7_80x80": the crop must include 2.7x the
# face box, otherwise the border cues it relies on are missing.
CROP_SCALE = 2.7
REAL_CLASS = 1
# Measured: live webcam frames score 0.72-0.93, upstream's fakes score <= 0.02.
LIVE_THRESHOLD = 0.6

_net: cv2.dnn.Net | None = None


def _load() -> cv2.dnn.Net:
    global _net
    if _net is None:
        if not _MODEL.exists():
            raise FileNotFoundError(
                f"anti-spoof model not found at {_MODEL}. "
                "Run: python installer/download_weights.py"
            )
        _net = cv2.dnn.readNetFromONNX(str(_MODEL))
    return _net


def _crop(bgr: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """Square CROP_SCALE window around the face box.

    The window must be the full 2.7x — the model reads the border context, so
    a short window looks like a screen. Upstream simply shrinks the scale when
    the frame is too small, which breaks down on a laptop webcam: sit close
    enough for a 240 px face in a 480 px frame and only 2.0x is available.
    Measured on this machine, that drops a live face to 0.15-0.39 while a
    correctly framed one scores 0.95+.

    So pad the deficit with BORDER_REPLICATE instead (live 0.49-0.90, and
    upstream's labelled fakes stay at 0.00-0.01). Reflect padding was tried
    and rejected: it pushed one labelled fake to 0.91, a false accept.
    """
    x, y, bw, bh = box
    if bw < 8 or bh < 8:
        raise ValueError("face box too small to crop")

    side = max(bw, bh) * CROP_SCALE
    cx, cy = x + bw / 2.0, y + bh / 2.0
    half = int(np.ceil(side / 2.0))

    pad_l = max(0, half - int(cx))
    pad_t = max(0, half - int(cy))
    pad_r = max(0, int(cx) + half - bgr.shape[1])
    pad_b = max(0, int(cy) + half - bgr.shape[0])
    if pad_l or pad_t or pad_r or pad_b:
        bgr = cv2.copyMakeBorder(bgr, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)
        cx, cy = cx + pad_l, cy + pad_t

    x0, y0 = int(cx - side / 2.0), int(cy - side / 2.0)
    return bgr[max(0, y0):int(y0 + side), max(0, x0):int(x0 + side)]


def scores(bgr: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """Softmax over the 3 classes; index REAL_CLASS is the live one."""
    patch = cv2.resize(_crop(bgr, box), (INPUT_SIZE, INPUT_SIZE))
    # scalefactor=1.0: the network wants raw 0-255 BGR, not [0, 1].
    blob = cv2.dnn.blobFromImage(patch, scalefactor=1.0,
                                 size=(INPUT_SIZE, INPUT_SIZE), swapRB=False)
    net = _load()
    net.setInput(blob)
    logits = net.forward().flatten().astype(np.float64)
    e = np.exp(logits - logits.max())
    return e / e.sum()


def is_live(
    bgr: np.ndarray,
    box: tuple[float, float, float, float],
    threshold: float = LIVE_THRESHOLD,
) -> tuple[bool, str]:
    """(is_live, reason). Reason names the winning attack class on rejection."""
    try:
        p = scores(bgr, box)
    except Exception as e:  # model missing, degenerate crop, decode failure
        log.warning("liveness check failed: %s", e)
        return False, f"error: {e}"

    live = float(p[REAL_CLASS])
    if int(np.argmax(p)) == REAL_CLASS and live >= threshold:
        return True, f"live {live:.2f}"
    return False, f"spoof class={int(np.argmax(p))} p={p.max():.2f} (live {live:.2f})"

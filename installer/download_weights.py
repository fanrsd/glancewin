"""Fetch the two ONNX models that aren't in git into models/.

YuNet (227 KB) ships in the repo. SFace (37 MB, recognition) and
MiniFASNetV2 (1.7 MB, liveness) are downloaded here and pinned by SHA-256 —
they come from third parties, so an unverified download would be a trust
boundary with nothing guarding it.

    python installer/download_weights.py
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"

# (url, destination, sha256)
FILES = [
    (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
        "face_recognition_sface_2021dec.onnx",
        MODELS_DIR / "face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
    (
        "https://github.com/QingHeYang/Silent-Face-Anti-Spoofing-onnx/"
        "raw/main/onnx/2.7_80x80_MiniFASNetV2.onnx",
        MODELS_DIR / "2.7_80x80_MiniFASNetV2.onnx",
        "0cbe5caec95c31de9d2ef845cb85407d76aecd1b6a2c0e343f7d35306bfbccb8",
    ),
    (
        # Ships in git, but fetch it too: a repo copied without git history
        # (or a stripped release tarball) would otherwise have no detector.
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
        "face_detection_yunet_2023mar.onnx",
        MODELS_DIR / "face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str, dest: Path) -> None:
    print(f"  -> {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "wfu-installer-builder"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        seen = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            seen += len(chunk)
            if total:
                print(f"\r     {seen // 1024:>10} KB / {total // 1024} KB "
                      f"({seen * 100 // total}%)", end="", flush=True)
        print()
    tmp.replace(dest)


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    rc = 0
    for url, dest, want in FILES:
        if dest.exists() and _sha256(dest) == want:
            print(f"[skip] {dest.name} present and verified")
            continue
        print(f"[get ] {dest.name}")
        try:
            _fetch(url, dest)
        except Exception as e:
            print(f"ERROR downloading {url}: {e}", file=sys.stderr)
            rc = 1
            continue
        got = _sha256(dest)
        if got != want:
            print(f"ERROR {dest.name} hash mismatch\n  want {want}\n  got  {got}",
                  file=sys.stderr)
            dest.unlink(missing_ok=True)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

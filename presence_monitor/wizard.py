"""Setup wizard — numbered steps from nothing installed to face unlock.

    python -m presence_monitor.wizard        (or tools\\wizard.cmd)

Every step is idempotent and detects its own state, so the wizard doubles as
a repair tool: open it any time and it shows which pieces are missing.

Steps that need administrator rights (registering the Credential Provider)
re-launch themselves elevated through PowerShell instead of asking you to
open a second shell.
"""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from face_service.config import CONFIG_PATH, EMBED_PATH, ENROLL_DIR
from face_service.i18n import t

from .enroll_gui import open_enroll
from .gui import PasswordForm
from .monitor import pipe_call
from .theme import apply_theme

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
CP_DIR = REPO_ROOT / "credential_provider"
# build\Release is where CMake puts it; the flat path is for a DLL handed
# over from another machine (copying a repo rarely includes build\).
_CP_CANDIDATES = (
    CP_DIR / "build" / "Release" / "FaceCredentialProvider.dll",
    CP_DIR / "FaceCredentialProvider.dll",
)
CP_DLL = next((p for p in _CP_CANDIDATES if p.exists()), _CP_CANDIDATES[0])
REGISTER_PS1 = REPO_ROOT / "credential_provider" / "register.ps1"
CLSID = "{F50C7625-CF2E-4572-A0CB-BCF578F9BECA}"

OK = "\u2713"      # check mark
BAD = "\u2717"     # ballot X
WARN = "\u2022"    # bullet — neutral / optional


# ---------------------------------------------------------------------------
# State probes — each returns (ok, detail)
# ---------------------------------------------------------------------------

def probe_models() -> tuple[bool, str]:
    models = REPO_ROOT / "models"
    want = {
        "face_detection_yunet_2023mar.onnx": 200_000,
        "face_recognition_sface_2021dec.onnx": 30_000_000,
        "2.7_80x80_MiniFASNetV2.onnx": 1_000_000,
    }
    missing = [
        n for n, least in want.items()
        if not (models / n).exists() or (models / n).stat().st_size < least
    ]
    if missing:
        return False, t("wiz.models.missing", names=", ".join(missing))
    return True, t("wiz.models.ok", count=len(want))


def probe_enrollment() -> tuple[bool, str]:
    try:
        photos = sum(1 for p in ENROLL_DIR.iterdir()
                     if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    except FileNotFoundError:
        photos = 0
    if not EMBED_PATH.exists():
        return False, t("wiz.enroll.none", photos=photos)
    try:
        import numpy as np
        n = int(np.load(EMBED_PATH)["embeddings"].shape[0])
    except Exception as e:
        return False, t("wiz.enroll.broken", error=str(e))
    return n > 0, t("wiz.enroll.ok", count=n, photos=photos)


def probe_service() -> tuple[bool, str]:
    resp = pipe_call({"cmd": "status"}, timeout_s=5.0)
    if not resp:
        return False, t("wiz.service.down")
    return True, t("wiz.service.up", uptime=int(resp.get("uptime_s", 0)))


def probe_cp() -> tuple[bool, str]:
    """Is the Credential Provider built and registered?"""
    if not CP_DLL.exists():
        return False, t("wiz.cp.nodll")
    ps = (
        f"$c='{CLSID}';"
        r"$a=Test-Path \"Registry::HKEY_CLASSES_ROOT\CLSID\$c\InprocServer32\";"
        r"$b=Test-Path \"Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows"
        r"\CurrentVersion\Authentication\Credential Providers\$c\";"
        r"if ($a -and $b) { 'yes' } else { 'no' }"
    )
    out = _powershell(ps)
    if out.strip().endswith("yes"):
        return True, t("wiz.cp.registered")
    return False, t("wiz.cp.unregistered")


def probe_task() -> tuple[bool, str]:
    out = _powershell(
        "(Get-ScheduledTask -TaskName 'FaceUnlock-Service' "
        "-ErrorAction SilentlyContinue).State"
    ).strip()
    if not out:
        return False, t("wiz.task.absent")
    return True, t("wiz.task.present", state=out.splitlines()[-1])


def _powershell(script: str, elevated: bool = False) -> str:
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    if elevated:
        # Start-Process -Verb RunAs raises the UAC prompt; -Wait so the
        # caller can re-probe afterwards.
        inner = script.replace("'", "''")
        args += ["-Command",
                 "Start-Process powershell -Verb RunAs -Wait -ArgumentList "
                 f"'-NoProfile','-ExecutionPolicy','Bypass','-Command','{inner}'"]
    else:
        args += ["-Command", script]
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=180,
                             creationflags=0x08000000)  # CREATE_NO_WINDOW
        return (res.stdout or "") + (res.stderr or "")
    except Exception as e:
        log.exception("powershell failed")
        return f"error: {e}"


# ---------------------------------------------------------------------------
# Stepper header
# ---------------------------------------------------------------------------

class Stepper(tk.Canvas):
    """Numbered circles joined by a rail, current step highlighted."""

    R = 18
    PAD_TOP = 34

    def __init__(self, master, labels: list[str], accent: str, dim: str,
                 bg: str, fg: str):
        self.labels = labels
        self.accent, self.dim, self.bg, self.fg = accent, dim, bg, fg
        super().__init__(master, height=self.PAD_TOP + 2 * self.R + 10,
                         highlightthickness=0, bg=bg)
        self.current = 0
        self.bind("<Configure>", lambda _e: self._draw())

    def set_current(self, index: int) -> None:
        self.current = index
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        n = len(self.labels)
        w = max(self.winfo_width(), 200)
        step = w / n
        cy = self.PAD_TOP + self.R
        for i, label in enumerate(self.labels):
            cx = step * (i + 0.5)
            done = i <= self.current
            colour = self.accent if done else self.dim
            if i:
                prev = step * (i - 0.5)
                self.create_line(prev + self.R, cy, cx - self.R, cy,
                                 fill=self.accent if i <= self.current else self.dim,
                                 width=2)
            self.create_oval(cx - self.R, cy - self.R, cx + self.R, cy + self.R,
                             outline=colour, width=2,
                             fill=colour if i == self.current else self.bg)
            self.create_text(cx, cy, text=str(i + 1),
                             fill=self.bg if i == self.current else colour,
                             font=("", 10, "bold"))
            self.create_text(cx, 14, text=label, width=int(step) - 6,
                             fill=self.fg if done else self.dim,
                             font=("", 8, "bold" if i == self.current else "normal"))


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

class Step:
    """One wizard page. Subclasses fill ``body`` and implement ``refresh``."""

    key = "?"
    optional = False

    def __init__(self, wizard: "Wizard"):
        self.wizard = wizard
        self.frame = ttk.Frame(wizard.body, padding=(4, 8))
        self.status = tk.StringVar()
        self.build()

    def build(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def refresh(self) -> None:
        """Probe off-thread (some probes shell out to PowerShell), then paint."""
        def worker():
            try:
                ok, detail = self.probe()
            except Exception as e:  # a broken probe must not kill the wizard
                log.exception("probe %s failed", self.key)
                ok, detail = False, str(e)
            # Tcl is not thread-safe: hand the result to the main loop
            # instead of touching widgets (or .after) from this thread.
            self.wizard.post(lambda: self.apply(ok, detail))

        threading.Thread(target=worker, name=f"probe-{self.key}",
                         daemon=True).start()

    def apply(self, ok: bool, detail: str) -> None:
        mark = OK if ok else (WARN if self.optional else BAD)
        self.status.set(f"{mark}  {detail}")
        self.wizard.set_step_ok(self, ok)

    def probe(self) -> tuple[bool, str]:  # pragma: no cover - overridden
        raise NotImplementedError

    def _head(self) -> None:
        ttk.Label(self.frame, text=t(f"wiz.{self.key}.title"),
                  font=("", 14, "bold")).pack(anchor="w")
        ttk.Label(self.frame, text=t(f"wiz.{self.key}.body"),
                  wraplength=620, justify="left").pack(anchor="w", pady=(6, 12))

    def _status_row(self) -> None:
        ttk.Label(self.frame, textvariable=self.status, wraplength=620,
                  justify="left").pack(anchor="w", pady=(12, 0))


class ModelsStep(Step):
    key = "models"

    def build(self) -> None:
        self._head()
        row = ttk.Frame(self.frame)
        row.pack(anchor="w")
        self.btn = ttk.Button(row, text=t("wiz.models.btn"), command=self._download)
        self.btn.pack(side="left")
        self._status_row()

    def probe(self) -> tuple[bool, str]:
        return probe_models()

    def _download(self) -> None:
        self.btn.configure(state="disabled")
        self.status.set(t("wiz.models.running"))

        def worker():
            out = subprocess.run(
                [sys.executable, str(REPO_ROOT / "installer" / "download_weights.py")],
                capture_output=True, text=True, cwd=str(REPO_ROOT),
                creationflags=0x08000000,
            )
            tail = (out.stdout or out.stderr or "").strip().splitlines()[-1:]
            self.wizard.post(lambda: (
                self.btn.configure(state="normal"),
                self.status.set(" ".join(tail)),
                self.refresh(),
            ))

        threading.Thread(target=worker, daemon=True).start()


class EnrollStep(Step):
    key = "enroll"

    def build(self) -> None:
        self._head()
        row = ttk.Frame(self.frame)
        row.pack(anchor="w")
        ttk.Button(row, text=t("wiz.enroll.btn"),
                   command=self._open).pack(side="left")
        ttk.Button(row, text=t("wiz.recheck"),
                   command=self.refresh).pack(side="left", padx=6)
        self._status_row()

    def probe(self) -> tuple[bool, str]:
        return probe_enrollment()

    def _open(self) -> None:
        open_enroll()
        self.status.set(t("wiz.enroll.opened"))


class PasswordStep(Step):
    key = "pwd"

    def build(self) -> None:
        self._head()
        self.form = PasswordForm(self.frame, on_saved=self.refresh)
        self.form.pack(anchor="w", fill="x")
        self._status_row()

    def probe(self) -> tuple[bool, str]:
        stored = self.form.is_stored()
        return stored, t("pwd.stored") if stored else t("pwd.absent")


class TileStep(Step):
    key = "cp"
    optional = True

    def build(self) -> None:
        self._head()
        row = ttk.Frame(self.frame)
        row.pack(anchor="w")
        ttk.Button(row, text=t("wiz.cp.btn.register"),
                   command=lambda: self._registry("register")).pack(side="left")
        ttk.Button(row, text=t("wiz.cp.btn.unregister"),
                   command=lambda: self._registry("unregister")).pack(side="left", padx=6)
        ttk.Button(row, text=t("wiz.recheck"),
                   command=self.refresh).pack(side="left", padx=6)
        self._status_row()

    def probe(self) -> tuple[bool, str]:
        return probe_cp()

    def _registry(self, action: str) -> None:
        if not CP_DLL.exists():
            self.status.set(f"{BAD}  {t('wiz.cp.nodll')}")
            return
        self.status.set(t("wiz.cp.elevating"))

        def worker():
            _powershell(
                f"& '{REGISTER_PS1}' -Action {action} -DllPath '{CP_DLL}'",
                elevated=True,
            )
            self.wizard.post(self.refresh)

        threading.Thread(target=worker, daemon=True).start()


class AutostartStep(Step):
    key = "task"

    def build(self) -> None:
        self._head()
        row = ttk.Frame(self.frame)
        row.pack(anchor="w")
        ttk.Button(row, text=t("wiz.task.btn"),
                   command=self._register).pack(side="left")
        ttk.Button(row, text=t("wiz.recheck"),
                   command=self.refresh).pack(side="left", padx=6)
        self._status_row()

    def probe(self) -> tuple[bool, str]:
        ok, detail = probe_task()
        svc_ok, svc_detail = probe_service()
        return ok and svc_ok, f"{detail} | {svc_detail}"

    def _register(self) -> None:
        self.status.set(t("wiz.task.running"))
        pyw = REPO_ROOT / ".venv" / "Scripts" / "pythonw.exe"
        exe = str(pyw if pyw.exists() else Path(sys.executable))
        script = (
            f"$a = New-ScheduledTaskAction -Execute '{exe}' "
            f"-Argument '-m face_service' -WorkingDirectory '{REPO_ROOT}';"
            f"$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME;"
            "$p = New-ScheduledTaskPrincipal -UserId $env:USERNAME "
            "-LogonType Interactive -RunLevel Limited;"
            "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
            "-DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden;"
            "Register-ScheduledTask -TaskName 'FaceUnlock-Service' -Action $a "
            "-Trigger $t -Principal $p -Settings $s -Force | Out-Null;"
            "Start-ScheduledTask -TaskName 'FaceUnlock-Service';"
            "Start-Sleep 6"
        )

        def worker():
            _powershell(script)
            self.wizard.post(self.refresh)

        threading.Thread(target=worker, daemon=True).start()


class TestStep(Step):
    key = "test"

    def build(self) -> None:
        self._head()
        row = ttk.Frame(self.frame)
        row.pack(anchor="w")
        self.btn = ttk.Button(row, text=t("wiz.test.btn"), command=self._run)
        self.btn.pack(side="left")
        self._status_row()

    def probe(self) -> tuple[bool, str]:
        return probe_service()

    def _run(self) -> None:
        self.btn.configure(state="disabled")
        self.status.set(t("wiz.test.running"))

        def worker():
            resp = pipe_call({"cmd": "verify"}, timeout_s=60.0)
            if not resp:
                text = f"{BAD}  {t('wiz.service.down')}"
            elif resp.get("match") and resp.get("real"):
                text = f"{OK}  " + t("wiz.test.pass", dist=resp.get("distance", 0))
            else:
                text = f"{BAD}  " + t("wiz.test.fail",
                                      dist=resp.get("distance", 1.0),
                                      real=resp.get("real"))
            self.wizard.post(lambda: (
                self.btn.configure(state="normal"), self.status.set(text)))

        threading.Thread(target=worker, daemon=True).start()


STEPS: list[type[Step]] = [
    ModelsStep, EnrollStep, PasswordStep, AutostartStep, TileStep, TestStep,
]


# ---------------------------------------------------------------------------
# Wizard shell
# ---------------------------------------------------------------------------

class Wizard:
    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self.root = tk.Tk()
        self.root.title(t("wiz.title"))
        self.root.geometry("760x560")
        self.root.minsize(700, 520)
        theme = apply_theme(self.root)
        dark = theme == "dark"
        bg = self.root.cget("bg")
        accent = "#4cc2ff" if dark else "#005fb8"
        dim = "#555a60" if dark else "#b8bcc2"
        fg = "#f0f0f0" if dark else "#101010"

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=t("wiz.title"), font=("", 17, "bold")).pack(anchor="w")
        ttk.Separator(outer).pack(fill="x", pady=(8, 2))

        self.stepper = Stepper(
            outer, [t(f"wiz.{c.key}.step") for c in STEPS],
            accent=accent, dim=dim, bg=bg, fg=fg,
        )
        self.stepper.pack(fill="x", pady=(4, 4))
        ttk.Separator(outer).pack(fill="x", pady=(2, 8))

        self.body = ttk.Frame(outer)
        self.body.pack(fill="both", expand=True)

        self.steps = [cls(self) for cls in STEPS]
        self._ok: dict[str, bool] = {}
        self.index = 0

        nav = ttk.Frame(outer)
        nav.pack(fill="x", pady=(10, 0))
        self.summary = tk.StringVar()
        ttk.Label(nav, textvariable=self.summary).pack(side="left")
        self.next_btn = ttk.Button(nav, text=t("wiz.next"), command=self._next)
        self.next_btn.pack(side="right", padx=4)
        self.back_btn = ttk.Button(nav, text=t("wiz.back"), command=self._back)
        self.back_btn.pack(side="right", padx=4)
        ttk.Button(nav, text=t("wiz.close"),
                   command=self.root.destroy).pack(side="right", padx=(4, 16))

        self._show(0)
        # Probe every step, not just the visible one, so the footer summary
        # tells you what is missing before you click through six pages.
        for step in self.steps:
            step.refresh()
        self._pump()

    # -- cross-thread plumbing --------------------------------------------
    def post(self, fn) -> None:
        """Queue ``fn`` for the main loop. Safe from any thread."""
        self._q.put(fn)

    def _pump(self) -> None:
        while True:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("queued UI callback failed")
        self.root.after(80, self._pump)

    # -- navigation --------------------------------------------------------
    def _show(self, index: int) -> None:
        self.steps[self.index].frame.pack_forget()
        self.index = max(0, min(index, len(self.steps) - 1))
        step = self.steps[self.index]
        step.frame.pack(fill="both", expand=True)
        self.stepper.set_current(self.index)
        self.back_btn.configure(state="normal" if self.index else "disabled")
        self.next_btn.configure(
            state="normal" if self.index < len(self.steps) - 1 else "disabled")
        step.refresh()

    def _next(self) -> None:
        self._show(self.index + 1)

    def _back(self) -> None:
        self._show(self.index - 1)

    def set_step_ok(self, step: Step, ok: bool) -> None:
        self._ok[step.key] = ok
        done = sum(1 for s in self.steps if self._ok.get(s.key))
        required = [s for s in self.steps if not s.optional]
        missing = [s.key for s in required if not self._ok.get(s.key)]
        self.summary.set(t("wiz.summary", done=done, total=len(self.steps),
                           missing=", ".join(missing) or "-"))

    def run(self) -> None:
        self.root.mainloop()


def open_wizard() -> None:
    """Launch the wizard in its own thread (tray stays responsive)."""
    threading.Thread(target=lambda: Wizard().run(),
                     name="wizard-window", daemon=True).start()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    os.environ.setdefault("FACE_UNLOCK_WIZARD", "1")
    Wizard().run()


if __name__ == "__main__":
    main()

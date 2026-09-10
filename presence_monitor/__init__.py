"""Tray app + management GUI for Face Unlock.

Declares DPI awareness before any Tk window exists. Without it Tk scales
fonts for the display (tk scaling 1.67 at 125%) but reports unscaled
geometry, so every window comes out too small and clips its buttons.
"""
import ctypes

try:
    # 1 = system-DPI aware. Enough here: the windows are small and static,
    # and it avoids the per-monitor rescaling Tk cannot follow anyway.
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:  # pragma: no cover - pre-8.1 Windows or already set
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

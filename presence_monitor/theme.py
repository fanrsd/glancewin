"""Sun Valley ttk theme, following the Windows light/dark setting.

Every window calls :func:`apply_theme` right after creating its root. The
widgets themselves are unchanged plain ``ttk`` — this only swaps the theme,
which is why it costs one 87 KB dependency instead of a UI rewrite.
"""
from __future__ import annotations

import logging
import winreg

import sv_ttk

log = logging.getLogger(__name__)

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def windows_prefers_dark() -> bool:
    """Read the per-user app theme. Defaults to light if the key is absent."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def apply_theme(root, mode: str = "auto") -> str:
    """Apply the theme to ``root``. ``mode``: auto | light | dark."""
    theme = mode
    if mode not in ("light", "dark"):
        theme = "dark" if windows_prefers_dark() else "light"
    try:
        sv_ttk.set_theme(theme, root=root)
    except Exception:
        log.exception("theme %s failed; staying on default ttk", theme)
    return theme

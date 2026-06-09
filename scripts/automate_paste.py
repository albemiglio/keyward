#!/usr/bin/env python3
"""
Cross-platform paste-and-submit automation.

Usage:
    automate_paste.py <sanitized_text_file> [<expected_frontmost_app>]

Reads sanitized text from a tempfile, backs up the system clipboard, puts the
sanitized text in the clipboard, simulates Cmd/Ctrl+V + Enter against the
currently-focused application, then restores the original clipboard contents
and deletes the tempfile.

Designed to be called detached from intercept.py so it survives after the
hook returns its block JSON to Claude Code.

Backends per platform:
    macOS:           osascript (System Events) + pbcopy/pbpaste
    Linux X11:       xdotool + xclip (or xsel)
    Linux Wayland:   wtype + wl-clipboard (wl-copy/wl-paste)
    Windows:         PowerShell SendKeys + Set-Clipboard/Get-Clipboard

Failure mode: errors are appended to ~/.claude/secrets/.last-error (no secret
values logged), the tempfile is removed, and the script exits non-zero. The
secret has already been saved to disk by intercept.py, so the user can paste
the sanitized text manually if automation failed.

This script never reads or logs the secret value itself — only the sanitized
prompt (which is, by definition, secret-free).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "secrets" / ".last-error"

# Timing tuned by experiment on macOS:
#   - Anything below 250 ms races the "blocked" message render and lands
#     in the wrong UI state.
#   - Anything above 600 ms is perceptibly slow.
PASTE_DELAY_S = 0.35
RESTORE_DELAY_S = 0.30


# ---------------------------------------------------------------------------
# Logging (errors only; no secret data ever logged)
# ---------------------------------------------------------------------------
def log_err(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(LOG_PATH.parent, 0o700)
        except OSError:
            pass
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
def detect_platform() -> str:
    """Return one of: 'macos', 'linux-x11', 'linux-wayland', 'windows', 'unknown'."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        # Wayland indicators
        if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return "linux-wayland"
        if os.environ.get("DISPLAY"):
            return "linux-x11"
        # No display server detected → headless / ssh / tmux without DISPLAY
        return "unknown"
    return "unknown"


# ---------------------------------------------------------------------------
# Backend: macOS
# ---------------------------------------------------------------------------
class MacOSBackend:
    name = "macos"

    @staticmethod
    def available() -> bool:
        return shutil.which("osascript") is not None and shutil.which("pbcopy") is not None

    @staticmethod
    def get_clipboard() -> str:
        try:
            return subprocess.run(
                ["pbpaste"], check=False, capture_output=True, text=True, timeout=2
            ).stdout
        except (subprocess.SubprocessError, OSError):
            return ""

    @staticmethod
    def set_clipboard(text: str) -> bool:
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=2)
            return True
        except (subprocess.SubprocessError, OSError):
            return False

    @staticmethod
    def get_frontmost_app() -> str:
        try:
            return subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to name of first application process whose frontmost is true'],
                check=False, capture_output=True, text=True, timeout=2,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return ""

    @staticmethod
    def paste_and_enter() -> bool:
        script = (
            'tell application "System Events"\n'
            '    keystroke "v" using command down\n'
            '    delay 0.05\n'
            '    key code 36\n'
            'end tell'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script], check=False, capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                log_err(f"macOS osascript exit={result.returncode}: {result.stderr.strip()}")
                return False
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            log_err(f"macOS osascript exception: {exc}")
            return False


# ---------------------------------------------------------------------------
# Backend: Linux X11
# ---------------------------------------------------------------------------
class LinuxX11Backend:
    name = "linux-x11"

    @staticmethod
    def _clipboard_tool() -> str | None:
        if shutil.which("xclip"):
            return "xclip"
        if shutil.which("xsel"):
            return "xsel"
        return None

    @classmethod
    def available(cls) -> bool:
        return shutil.which("xdotool") is not None and cls._clipboard_tool() is not None

    @classmethod
    def get_clipboard(cls) -> str:
        tool = cls._clipboard_tool()
        try:
            if tool == "xclip":
                return subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    check=False, capture_output=True, text=True, timeout=2,
                ).stdout
            if tool == "xsel":
                return subprocess.run(
                    ["xsel", "-b", "-o"],
                    check=False, capture_output=True, text=True, timeout=2,
                ).stdout
        except (subprocess.SubprocessError, OSError):
            pass
        return ""

    @classmethod
    def set_clipboard(cls, text: str) -> bool:
        tool = cls._clipboard_tool()
        try:
            if tool == "xclip":
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text, text=True, check=True, timeout=2,
                )
                return True
            if tool == "xsel":
                subprocess.run(
                    ["xsel", "-b", "-i"],
                    input=text, text=True, check=True, timeout=2,
                )
                return True
        except (subprocess.SubprocessError, OSError):
            pass
        return False

    @staticmethod
    def get_frontmost_app() -> str:
        # xdotool can give us the active window class
        try:
            wid = subprocess.run(
                ["xdotool", "getactivewindow"],
                check=False, capture_output=True, text=True, timeout=2,
            ).stdout.strip()
            if not wid:
                return ""
            return subprocess.run(
                ["xdotool", "getwindowclassname", wid],
                check=False, capture_output=True, text=True, timeout=2,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return ""

    @staticmethod
    def paste_and_enter() -> bool:
        try:
            result = subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                check=False, capture_output=True, text=True, timeout=3,
            )
            if result.returncode != 0:
                log_err(f"linux-x11 xdotool ctrl+v exit={result.returncode}: {result.stderr.strip()}")
                return False
            time.sleep(0.05)
            result = subprocess.run(
                ["xdotool", "key", "Return"],
                check=False, capture_output=True, text=True, timeout=3,
            )
            if result.returncode != 0:
                log_err(f"linux-x11 xdotool Return exit={result.returncode}: {result.stderr.strip()}")
                return False
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            log_err(f"linux-x11 xdotool exception: {exc}")
            return False


# ---------------------------------------------------------------------------
# Backend: Linux Wayland
# ---------------------------------------------------------------------------
class LinuxWaylandBackend:
    name = "linux-wayland"

    @staticmethod
    def available() -> bool:
        # wtype requires compositor support for virtual-keyboard protocol.
        # wl-copy/wl-paste come from wl-clipboard.
        return shutil.which("wtype") is not None and shutil.which("wl-copy") is not None

    @staticmethod
    def get_clipboard() -> str:
        try:
            return subprocess.run(
                ["wl-paste", "--no-newline"],
                check=False, capture_output=True, text=True, timeout=2,
            ).stdout
        except (subprocess.SubprocessError, OSError):
            return ""

    @staticmethod
    def set_clipboard(text: str) -> bool:
        try:
            subprocess.run(
                ["wl-copy"], input=text, text=True, check=True, timeout=2,
            )
            return True
        except (subprocess.SubprocessError, OSError):
            return False

    @staticmethod
    def get_frontmost_app() -> str:
        # No portable cross-compositor way. Sway: swaymsg. Hyprland: hyprctl.
        # Skip detection — return empty so the focus check is bypassed.
        return ""

    @staticmethod
    def paste_and_enter() -> bool:
        try:
            result = subprocess.run(
                ["wtype", "-M", "ctrl", "v", "-m", "ctrl"],
                check=False, capture_output=True, text=True, timeout=3,
            )
            if result.returncode != 0:
                log_err(f"linux-wayland wtype ctrl+v exit={result.returncode}: {result.stderr.strip()}")
                return False
            time.sleep(0.05)
            result = subprocess.run(
                ["wtype", "-k", "Return"],
                check=False, capture_output=True, text=True, timeout=3,
            )
            if result.returncode != 0:
                log_err(f"linux-wayland wtype Return exit={result.returncode}: {result.stderr.strip()}")
                return False
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            log_err(f"linux-wayland wtype exception: {exc}")
            return False


# ---------------------------------------------------------------------------
# Backend: Windows
# ---------------------------------------------------------------------------
class WindowsBackend:
    name = "windows"

    @staticmethod
    def _powershell() -> str | None:
        return shutil.which("pwsh") or shutil.which("powershell")

    @classmethod
    def available(cls) -> bool:
        return cls._powershell() is not None

    @classmethod
    def get_clipboard(cls) -> str:
        ps = cls._powershell()
        if not ps:
            return ""
        try:
            return subprocess.run(
                [ps, "-NoProfile", "-Command", "Get-Clipboard"],
                check=False, capture_output=True, text=True, timeout=3,
            ).stdout
        except (subprocess.SubprocessError, OSError):
            return ""

    @classmethod
    def set_clipboard(cls, text: str) -> bool:
        ps = cls._powershell()
        if not ps:
            return False
        # Use stdin → Set-Clipboard to avoid argument quoting headaches with multi-line text.
        try:
            subprocess.run(
                [ps, "-NoProfile", "-Command", "$input | Set-Clipboard"],
                input=text, text=True, check=True, timeout=3,
            )
            return True
        except (subprocess.SubprocessError, OSError):
            return False

    @classmethod
    def get_frontmost_app(cls) -> str:
        ps = cls._powershell()
        if not ps:
            return ""
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$proc = Get-Process | Where-Object { $_.MainWindowHandle -eq "
            "[System.Windows.Forms.Form]::ActiveForm.Handle } | Select-Object -First 1;"
            "if ($proc) { $proc.ProcessName }"
        )
        try:
            return subprocess.run(
                [ps, "-NoProfile", "-Command", script],
                check=False, capture_output=True, text=True, timeout=3,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return ""

    @classmethod
    def paste_and_enter(cls) -> bool:
        ps = cls._powershell()
        if not ps:
            return False
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "[System.Windows.Forms.SendKeys]::SendWait('^v');"
            "Start-Sleep -Milliseconds 50;"
            "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')"
        )
        try:
            result = subprocess.run(
                [ps, "-NoProfile", "-Command", script],
                check=False, capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                log_err(f"windows SendKeys exit={result.returncode}: {result.stderr.strip()}")
                return False
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            log_err(f"windows SendKeys exception: {exc}")
            return False


BACKENDS = {
    "macos": MacOSBackend,
    "linux-x11": LinuxX11Backend,
    "linux-wayland": LinuxWaylandBackend,
    "windows": WindowsBackend,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) < 2:
        log_err("automate_paste.py: missing tempfile argument")
        return 2

    text_path = Path(sys.argv[1])
    expected_app = sys.argv[2] if len(sys.argv) >= 3 else ""

    if not text_path.is_file():
        log_err(f"automate_paste.py: tempfile not found: {text_path}")
        return 2

    try:
        sanitized = text_path.read_text(encoding="utf-8")
    except OSError as exc:
        log_err(f"automate_paste.py: cannot read tempfile: {exc}")
        try:
            text_path.unlink(missing_ok=True)
        except OSError:
            pass
        return 2

    platform = detect_platform()
    backend = BACKENDS.get(platform)
    if backend is None or not backend.available():
        log_err(
            f"automate_paste.py: no usable backend (platform={platform}). "
            f"Install required tools — see README. Secret was still saved; "
            f"sanitized text was put in clipboard if possible."
        )
        # Best-effort: still try to set clipboard so the user can paste manually.
        for cls in BACKENDS.values():
            try:
                if cls.available():
                    cls.set_clipboard(sanitized)
                    break
            except Exception:
                continue
        try:
            text_path.unlink(missing_ok=True)
        except OSError:
            pass
        return 1

    # Save clipboard, load sanitized text.
    original_clipboard = backend.get_clipboard()
    if not backend.set_clipboard(sanitized):
        log_err(f"automate_paste.py: {backend.name}: failed to set clipboard")
        try:
            text_path.unlink(missing_ok=True)
        except OSError:
            pass
        return 1

    # Give Claude Code time to render the "blocked" message before we paste.
    time.sleep(PASTE_DELAY_S)

    # Best-effort focus check (skip if backend can't determine frontmost).
    if expected_app:
        current = backend.get_frontmost_app()
        if current and current != expected_app:
            log_err(
                f"automate_paste.py: frontmost changed "
                f"'{expected_app}' -> '{current}' — paste aborted (sanitized text left in clipboard)"
            )
            backend.set_clipboard(original_clipboard)  # restore
            try:
                text_path.unlink(missing_ok=True)
            except OSError:
                pass
            return 1

    success = backend.paste_and_enter()

    # Wait a tick so the paste lands before we restore the clipboard.
    time.sleep(RESTORE_DELAY_S)
    backend.set_clipboard(original_clipboard)

    try:
        text_path.unlink(missing_ok=True)
    except OSError:
        pass

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

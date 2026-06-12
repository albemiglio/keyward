#!/usr/bin/env python3
"""
keyward — UserPromptSubmit hook entry point (cross-platform).

Pipeline:
    stdin (UserPromptSubmit JSON)
        ↓
    detect.py        — regex + explicit markers → list of secrets
        ↓
    save each secret → ~/.claude/secrets/<name>.txt  (chmod 600, atomic write)
        ↓
    build sanitized prompt (each secret span → <<secret:NAME stored at ...>>)
        ↓
    write sanitized → $TMPDIR/keyward/sanitized_<random>.txt  (chmod 600)
        ↓
    spawn automate_paste.py DETACHED  (cross-platform paste+enter automation)
        ↓
    emit hook JSON: {"decision":"block","suppressOriginalPrompt":true,"reason":...}

Fail-open: any unexpected error returns empty JSON so the original prompt
passes through unchanged. Better to leak a key in an edge case than to
silently swallow the user's message.
"""
from __future__ import annotations

import json
import os
import re
import secrets as pysecrets
import subprocess
import sys
import tempfile
from pathlib import Path

# Resolve plugin root from CLAUDE_PLUGIN_ROOT (set by Claude Code) or by
# walking up from this script's location.
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
SECRETS_DIR = Path.home() / ".claude" / "secrets"
# tempfile.gettempdir() is cross-platform (honors TMPDIR on Unix, TEMP/TMP on
# Windows) — never hardcode /tmp, which doesn't exist on Windows.
TMP_DIR = Path(tempfile.gettempdir()) / "keyward"

# Make detect.py importable.
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from detect import detect as detect_secrets
except ImportError:
    # Fail open if detect.py is missing or broken.
    print("{}")
    sys.exit(0)


def ensure_dirs() -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    # Best-effort tighten perms (no-op on Windows).
    try:
        os.chmod(SECRETS_DIR, 0o700)
        os.chmod(TMP_DIR, 0o700)
    except OSError:
        pass


def save_secret(name: str, value: str) -> Path:
    """Atomic write of a secret to disk with chmod 600."""
    safe_name = re.sub(r"[^A-Za-z0-9_\-]", "_", name)[:64] or "default"
    target = SECRETS_DIR / f"{safe_name}.txt"
    tmp = target.with_suffix(".txt.tmp")
    tmp.write_text(value, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(target)
    return target


def sanitize_prompt(prompt: str, secrets: list[dict]) -> str:
    """Replace each secret span with a reference, processed right-to-left."""
    sorted_secrets = sorted(secrets, key=lambda s: s["span"][0], reverse=True)
    out = prompt
    for s in sorted_secrets:
        start, end = s["span"]
        ref = f"<<secret:{s['name']} stored at ~/.claude/secrets/{s['name']}.txt>>"
        out = out[:start] + ref + out[end:]
    return out


def strip_raw_prefix(prompt: str) -> str:
    return re.sub(r"^\s*/raw\s+", "", prompt, count=1)


def write_tempfile(text: str) -> Path:
    path = TMP_DIR / f"sanitized_{pysecrets.token_hex(8)}.txt"
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def get_frontmost_app() -> str:
    """Best-effort: returns the name of the currently-focused app, or ''."""
    if sys.platform == "darwin":
        try:
            return subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to name of first application process whose frontmost is true'],
                check=False, capture_output=True, text=True, timeout=2,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return ""
    # On Linux X11 / Windows the automate_paste.py script will do its own
    # check. Returning empty here disables the early focus check at the
    # intercept layer — acceptable; the backend handles its own focus logic.
    return ""


def spawn_detached(cmd: list[str]) -> None:
    """Spawn a child process that survives this process exiting.

    Honors KEYWARD_DISABLE_PASTE=1 to skip the automation entirely. Useful for
    testing, headless environments, or users who prefer to paste manually
    (the sanitized text is still written to the tempfile path passed to the
    spawn — they can read it from there or from the clipboard if backend set it).
    """
    if os.environ.get("KEYWARD_DISABLE_PASTE") == "1":
        return
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        creationflags = 0x00000008 | 0x00000200
        subprocess.Popen(
            cmd,
            creationflags=creationflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    else:
        subprocess.Popen(
            cmd,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )


def emit(payload: dict) -> None:
    print(json.dumps(payload))


def main() -> int:
    try:
        ensure_dirs()
    except OSError:
        emit({})
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        emit({})
        return 0

    prompt = payload.get("user_prompt") or payload.get("prompt") or ""
    if not isinstance(prompt, str) or not prompt:
        emit({})
        return 0

    try:
        detection = detect_secrets(prompt)
    except Exception:
        emit({})
        return 0

    secrets_found = detection.get("secrets", [])
    raw_mode = detection.get("raw_mode", False)

    # --- /raw mode: strip prefix and re-submit ---
    if raw_mode:
        sanitized = strip_raw_prefix(prompt)
        if sanitized == prompt:
            emit({})
            return 0
        tmp = write_tempfile(sanitized)
        spawn_detached([
            sys.executable, str(SCRIPTS_DIR / "automate_paste.py"),
            str(tmp), get_frontmost_app(),
        ])
        emit({
            "decision": "block",
            "reason": "[keyward] /raw mode — prompt re-submitted without prefix.",
            "suppressOriginalPrompt": True,
        })
        return 0

    # --- no secrets: pass through unchanged ---
    if not secrets_found:
        emit({})
        return 0

    # --- secrets detected: save, sanitize, queue paste ---
    saved: list[tuple[str, str]] = []
    for s in secrets_found:
        try:
            save_secret(s["name"], s["value"])
            saved.append((s["name"], s["source"]))
        except OSError:
            # If even one secret fails to save, fail open: better to pass the
            # raw prompt (and have Claude tell the user to rotate) than to
            # silently block half-handled.
            emit({})
            return 0

    sanitized = sanitize_prompt(prompt, secrets_found)
    tmp = write_tempfile(sanitized)
    spawn_detached([
        sys.executable, str(SCRIPTS_DIR / "automate_paste.py"),
        str(tmp), get_frontmost_app(),
    ])

    summary = ", ".join(f"{name} [{source}]" for name, source in saved)
    reason = (
        f"[keyward] Intercepted {len(saved)} secret(s): {summary}. "
        f"Saved to ~/.claude/secrets/ (chmod 600). "
        f"Sanitized prompt queued for auto-paste."
    )
    emit({
        "decision": "block",
        "reason": reason,
        "suppressOriginalPrompt": True,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
keyward — Gemini CLI adapter for the BeforeAgent hook.

Gemini's BeforeAgent hook can DENY a prompt but cannot rewrite it
(`additionalContext` only appends, it does not redact), so this adapter is
fail-safe like the Codex one: on a detected secret it saves the value and
DENIES the prompt. The raw secret never reaches the model.

Reuses the shared detection core (scripts/detect.py) and the tested
save_secret() from the Claude hook — no logic duplicated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # adapters/gemini/ -> plugin root
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks"))

try:
    from detect import detect
    from intercept import save_secret
except ImportError:
    print("{}")
    sys.exit(0)


def handle(payload: dict) -> dict | None:
    """Return the JSON to emit (deny), or None to allow the prompt through."""
    prompt = payload.get("prompt") or ""
    if not isinstance(prompt, str) or not prompt:
        return None
    try:
        result = detect(prompt)
    except Exception:
        return None  # fail open
    if result.get("raw_mode"):
        return None  # /raw → user explicitly opted out
    secrets = result.get("secrets", [])
    if not secrets:
        return None

    saved = []
    for s in secrets:
        try:
            save_secret(s["name"], s["value"])
            saved.append(s["name"])
        except OSError:
            return None  # fail open if we can't persist
    names = ", ".join(saved)
    return {
        "decision": "deny",
        "reason": (
            f"[keyward] Secret(s) detected and saved to ~/.claude/secrets/ "
            f"({names}). Prompt denied to avoid leaking the value. Re-send "
            f"referencing the saved file path instead of the raw secret. "
            f"(Gemini hooks cannot auto-redact; prefix the prompt with /raw to send as-is.)"
        ),
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("{}")
        return 0
    out = handle(payload)
    print(json.dumps(out) if out is not None else "{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

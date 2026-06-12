#!/usr/bin/env python3
"""
keyward demo driver.

Runs the REAL detection + sanitization engine against a FAKE key, in a
sandboxed HOME, and narrates each step. Used to render demo/keyward-demo.gif
via VHS (see demo/demo.tape), and runnable standalone:

    python3 demo/demo.py

Nothing real is touched: HOME is redirected to a temp sandbox that is deleted
on exit, and the key shown is a syntactically-valid but fake GitHub PAT.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# ANSI colors
DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
GREY = "\033[90m"
RESET = "\033[0m"

PAUSE = float(os.environ.get("KV_DEMO_PAUSE", "1.1"))


def p(text="", end="\n", pause=None):
    print(text, end=end, flush=True)
    time.sleep(PAUSE if pause is None else pause)


def main() -> int:
    plugin_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_root / "scripts"))
    import detect  # the real engine

    sandbox = Path(tempfile.mkdtemp(prefix="kv-demo-"))
    secrets_dir = sandbox / ".claude" / "secrets"
    secrets_dir.mkdir(parents=True)

    # A fake-but-valid-looking GitHub PAT (ghp_ + 36 chars). Not a real token.
    fake_key = "ghp_" + "R3dac7edDEMOkeyNOTreal000000000000aa"[:36]
    user_prompt = f"deploy the bot to fly.io using {fake_key}"

    try:
        title_plain = "Keyward — secret interception for Claude Code"
        title = f"{BOLD}Keyward{RESET} — secret interception for Claude Code"
        w = 61  # inner width (number of box-drawing dashes)
        pad = " " * (w - 2 - len(title_plain))
        p(f"{GREY}┌{'─' * w}┐{RESET}")
        p(f"{GREY}│{RESET} {title} {pad}{GREY}│{RESET}")
        p(f"{GREY}└{'─' * w}┘{RESET}")
        p()
        p(f"{BOLD}1.{RESET} You type a prompt that contains an API key:")
        p()
        highlighted = user_prompt.replace(fake_key, f"{RED}{fake_key}{RESET}")
        p(f"   {DIM}>{RESET} {highlighted}")
        p()

        p(f"{BOLD}2.{RESET} The UserPromptSubmit hook scans it...", pause=PAUSE * 1.2)
        result = detect.detect(user_prompt)
        secret = result["secrets"][0]
        p(f"   {GREEN}✓{RESET} detected: {BOLD}{secret['name']}{RESET} "
          f"{GREY}(source: {secret['source']}, span {secret['span']}){RESET}")
        p()

        p(f"{BOLD}3.{RESET} The value is saved out of band, {BOLD}before the model sees it{RESET}:")
        target = secrets_dir / f"{secret['name']}.txt"
        tmp = target.with_suffix(".txt.tmp")
        tmp.write_text(secret["value"], encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(target)
        mode = oct(target.stat().st_mode & 0o777)
        p(f"   {GREEN}✓{RESET} ~/.claude/secrets/{secret['name']}.txt  {GREY}({mode}){RESET}")
        p()

        p(f"{BOLD}4.{RESET} The original prompt is blocked; Claude receives the {BOLD}sanitized{RESET} version:")
        p()
        sanitized = user_prompt[:secret["span"][0]] + \
            f"<<secret:{secret['name']} stored at ~/.claude/secrets/{secret['name']}.txt>>" + \
            user_prompt[secret["span"][1]:]
        sanitized_hl = sanitized.replace(
            f"<<secret:{secret['name']} stored at ~/.claude/secrets/{secret['name']}.txt>>",
            f"{CYAN}<<secret:{secret['name']} stored at ~/.claude/secrets/{secret['name']}.txt>>{RESET}",
        )
        p(f"   {DIM}>{RESET} {sanitized_hl}")
        p()

        p(f"{BOLD}5.{RESET} Claude uses the key without ever printing it:")
        p(f"   {DIM}>{RESET} {YELLOW}GITHUB_TOKEN=$(cat ~/.claude/secrets/{secret['name']}.txt)"
          f" flyctl deploy{RESET}")
        p()
        p(f"{GREEN}{BOLD}The raw key never reached the model context or the transcript.{RESET}", pause=PAUSE * 1.5)
        p()
        p(f"{GREY}gh:{RESET} github.com/albemiglio/keyward", pause=0.3)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

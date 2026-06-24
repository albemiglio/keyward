#!/usr/bin/env python3
"""
Detect API keys and secrets in a prompt string.

Reads JSON from stdin with field "user_prompt" (or "prompt").
Outputs JSON to stdout: {"secrets": [{"name": str, "value": str, "span": [start, end], "source": str}], "raw_mode": bool}

Detection sources:
  - "explicit": /key NAME=VALUE, KEY:NAME=VALUE, KEY=VALUE  → user-marked, always treated as secret
  - "regex":    known-prefix patterns (sk-ant, ghp_, AIza, etc.) → high-confidence auto-detect
  - "gitleaks": OPT-IN second pass via the gitleaks binary (set KEYWARD_USE_GITLEAKS=1).
                Catches formats not in the built-in regex library. Off by default to
                avoid adding a subprocess spawn to every prompt.

If the prompt starts with "/raw ", raw_mode=True and no detection runs.

Exit codes:
  0 — clean run (may or may not have detected secrets; see "secrets" in output)
  1 — input parse error
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# High-confidence patterns: prefix + length + charset.
# Each name maps to (compiled_regex, default_slot_name)
# Group 0 = full match (the secret value)
# ---------------------------------------------------------------------------
REGEX_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anthropic",          re.compile(r"sk-ant-(?:api|admin)\d+-[A-Za-z0-9_\-]{80,}")),
    ("openai_project",     re.compile(r"sk-proj-[A-Za-z0-9_\-]{40,}")),
    ("openai",             re.compile(r"sk-(?!ant-|proj-)[A-Za-z0-9]{32,}")),
    ("github_pat_classic", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github_pat_fine",    re.compile(r"github_pat_[A-Za-z0-9_]{82}")),
    ("github_oauth",       re.compile(r"gho_[A-Za-z0-9]{36}")),
    ("github_server",      re.compile(r"ghs_[A-Za-z0-9]{36}")),
    ("github_user",        re.compile(r"ghu_[A-Za-z0-9]{36}")),
    ("gitlab_pat",         re.compile(r"glpat-[A-Za-z0-9_\-]{20}")),
    ("slack_token",        re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("google_api",         re.compile(r"AIza[A-Za-z0-9_\-]{35}")),
    ("aws_access_key",     re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}")),
    ("hugging_face",       re.compile(r"hf_[A-Za-z0-9]{34,}")),
    ("stripe_live_secret", re.compile(r"sk_live_[A-Za-z0-9]{24,}")),
    ("stripe_test_secret", re.compile(r"sk_test_[A-Za-z0-9]{24,}")),
    ("stripe_live_pub",    re.compile(r"pk_live_[A-Za-z0-9]{24,}")),
    ("stripe_webhook",     re.compile(r"whsec_[A-Za-z0-9]{32,}")),
    ("sendgrid",           re.compile(r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}")),
    ("replicate",          re.compile(r"r8_[A-Za-z0-9]{40}")),
    ("npm_token",          re.compile(r"npm_[A-Za-z0-9]{36}")),
    ("digitalocean",       re.compile(r"dop_v1_[a-f0-9]{64}")),
    ("mailgun",            re.compile(r"key-[a-f0-9]{32}")),
    ("linear",             re.compile(r"lin_api_[A-Za-z0-9]{40}")),
    ("jwt",                re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
]

# ---------------------------------------------------------------------------
# Explicit markers — what the user types to force-tag a secret.
# All produce named slots.
# ---------------------------------------------------------------------------
# /key NAME=VALUE  or  /<plugin>:key NAME=VALUE   (slash form, namespaced or not)
EXPLICIT_SLASH = re.compile(r"/(?:[\w-]+:)?key\s+([A-Za-z][A-Za-z0-9_\-]{0,63})=(\S+)")
# KEY:NAME=VALUE       (inline marker with explicit name)
EXPLICIT_NAMED = re.compile(r"\bKEY:([A-Za-z][A-Za-z0-9_\-]{0,63})=(\S+)")
# KEY=VALUE            (inline marker, default slot)
EXPLICIT_DEFAULT = re.compile(r"\bKEY=(\S+)")

# ---------------------------------------------------------------------------
# Discussion-safe filter: if the matched text contains an obvious placeholder
# token, skip it. Prevents triggering on chat ABOUT key formats.
# ---------------------------------------------------------------------------
PLACEHOLDER_TOKENS = ("EXAMPLE", "PLACEHOLDER", "XXX", "YYY", "REDACTED", "FAKE", "DUMMY", "...", "***")


def looks_like_placeholder(value: str) -> bool:
    upper = value.upper()
    return any(tok in upper for tok in PLACEHOLDER_TOKENS)


def sanitize_slot_name(raw: str) -> str:
    """Slot names must be filesystem-safe (no path separators, no weird chars)."""
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", raw)
    return safe[:64] or "default"


# ---------------------------------------------------------------------------
# Optional gitleaks pass (opt-in via KEYWARD_USE_GITLEAKS=1).
#
# gitleaks ships a large, battle-tested rule library that covers many providers
# our built-in regex list does not. Running it on every prompt costs a subprocess
# spawn (~50-150 ms), so it's OFF by default — power users opt in.
#
# We scan via a temp file (gitleaks has no clean stdin string mode in v8) and
# locate each reported secret's span by str.find rather than trusting gitleaks'
# line/column reporting (which has varied across versions). This is robust and
# version-independent.
# ---------------------------------------------------------------------------
def gitleaks_enabled() -> bool:
    return os.environ.get("KEYWARD_USE_GITLEAKS") == "1" and shutil.which("gitleaks") is not None


def gitleaks_scan(prompt: str) -> list[tuple[str, str]]:
    """Return [(rule_id, secret_value), ...] from gitleaks, or [] on any failure."""
    binary = shutil.which("gitleaks")
    if not binary:
        return []
    findings: list[tuple[str, str]] = []
    tmpdir = tempfile.mkdtemp(prefix="kv-gitleaks-")
    try:
        src = os.path.join(tmpdir, "prompt.txt")
        report = os.path.join(tmpdir, "report.json")
        with open(src, "w", encoding="utf-8") as f:
            f.write(prompt)
        # --no-git: treat path as plain files. --exit-code 0: don't fail on findings.
        # -f json -r report: machine-readable output.
        try:
            subprocess.run(
                [binary, "detect", "--no-git", "--source", tmpdir,
                 "--report-format", "json", "--report-path", report,
                 "--exit-code", "0", "--no-banner"],
                check=False, capture_output=True, text=True, timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            return []
        if not os.path.exists(report):
            return []
        try:
            with open(report, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        for item in data:
            secret = item.get("Secret") or item.get("Match")
            rule = item.get("RuleID") or item.get("Rule") or "gitleaks"
            if secret and isinstance(secret, str):
                findings.append((sanitize_slot_name(str(rule)), secret))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return findings


def detect(prompt: str) -> dict:
    # /raw bypass — first thing checked, no further processing.
    if prompt.lstrip().startswith("/raw "):
        return {"secrets": [], "raw_mode": True}

    found: list[dict] = []
    claimed_spans: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= s or start >= e) for s, e in claimed_spans)

    # 1. Explicit /key NAME=VALUE (slash command)
    for m in EXPLICIT_SLASH.finditer(prompt):
        name, value = m.group(1), m.group(2)
        if looks_like_placeholder(value):
            continue
        # Claim only the VALUE span — the marker text itself stays in the prompt
        # so the model still understands what happened.
        v_start = m.start(2)
        v_end = m.end(2)
        if overlaps(v_start, v_end):
            continue
        claimed_spans.append((v_start, v_end))
        found.append({
            "name": sanitize_slot_name(name),
            "value": value,
            "span": [v_start, v_end],
            "source": "explicit_slash",
        })

    # 2. Explicit KEY:NAME=VALUE
    for m in EXPLICIT_NAMED.finditer(prompt):
        name, value = m.group(1), m.group(2)
        if looks_like_placeholder(value):
            continue
        v_start = m.start(2)
        v_end = m.end(2)
        if overlaps(v_start, v_end):
            continue
        claimed_spans.append((v_start, v_end))
        found.append({
            "name": sanitize_slot_name(name),
            "value": value,
            "span": [v_start, v_end],
            "source": "explicit_named",
        })

    # 3. Explicit KEY=VALUE (default slot)
    for m in EXPLICIT_DEFAULT.finditer(prompt):
        value = m.group(1)
        if looks_like_placeholder(value):
            continue
        v_start = m.start(1)
        v_end = m.end(1)
        if overlaps(v_start, v_end):
            continue
        claimed_spans.append((v_start, v_end))
        found.append({
            "name": "default",
            "value": value,
            "span": [v_start, v_end],
            "source": "explicit_default",
        })

    # 4. Regex-based auto-detection (prefix patterns)
    for slot_name, pattern in REGEX_PATTERNS:
        for m in pattern.finditer(prompt):
            value = m.group(0)
            if looks_like_placeholder(value):
                continue
            start, end = m.start(), m.end()
            if overlaps(start, end):
                continue
            claimed_spans.append((start, end))
            # Disambiguate multiple keys of the same provider with an index.
            existing_same_provider = sum(1 for f in found if f["name"].startswith(slot_name))
            name = slot_name if existing_same_provider == 0 else f"{slot_name}_{existing_same_provider + 1}"
            found.append({
                "name": name,
                "value": value,
                "span": [start, end],
                "source": "regex",
            })

    # 5. Optional gitleaks pass (opt-in). Adds spans the regex layer missed.
    if gitleaks_enabled():
        for rule_id, secret_value in gitleaks_scan(prompt):
            if looks_like_placeholder(secret_value):
                continue
            # Locate every occurrence of the reported secret in the prompt.
            search_from = 0
            while True:
                idx = prompt.find(secret_value, search_from)
                if idx == -1:
                    break
                start, end = idx, idx + len(secret_value)
                search_from = end
                if overlaps(start, end):
                    continue
                claimed_spans.append((start, end))
                existing_same = sum(1 for f in found if f["name"].startswith(rule_id))
                name = rule_id if existing_same == 0 else f"{rule_id}_{existing_same + 1}"
                found.append({
                    "name": name,
                    "value": secret_value,
                    "span": [start, end],
                    "source": "gitleaks",
                })

    # Stable ordering by span start so sanitization and tests are deterministic.
    found.sort(key=lambda f: f["span"][0])
    return {"secrets": found, "raw_mode": False}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"error": f"input parse failed: {exc}"}))
        sys.exit(1)

    prompt = payload.get("user_prompt") or payload.get("prompt") or ""
    if not isinstance(prompt, str):
        print(json.dumps({"error": "user_prompt missing or not a string"}))
        sys.exit(1)

    result = detect(prompt)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

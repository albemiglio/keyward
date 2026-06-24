# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Context-anchored detection** (`source: context`, ON by default): detects
  `NAME=VALUE` assignments where the name contains a key-ish word component
  (`key`, `token`, `secret`, `password`, `passwd`, `api`, `apikey`, `auth`,
  `bearer`, `credential`, `access_token`) delimited by `_`, `-`, or
  start/end of string. The value must be ≥ 8 characters, not a placeholder,
  and contain both letters and digits. Catches patterns like
  `MISTRAL_API_KEY=KnIjerNTEj215TdLLHuOofGeZQZYwV8c` that the regex layer
  would miss. Does not re-claim spans already owned by explicit or regex layers.
- **`KEYWARD_ENTROPY=1` detector** (`source: entropy`, opt-in): flags any
  standalone high-entropy token (≥ 20 chars, Shannon entropy ≥ 4.0 bits) not
  excluded as a UUID, MD5/SHA1/SHA256 hex hash, or placeholder. Off by default
  to avoid false positives; enable for maximum recall on prefix-less tokens.
- **`shannon_entropy(s)`** and **`is_random_token(s, min_len, min_entropy)`**
  primitives in `detect.py` (stdlib, no dependencies).
- **Gitleaks "wide mode" documentation**: expanded the README and Configuration
  table to explain how `KEYWARD_USE_GITLEAKS=1` fits into the detection stack,
  what it catches beyond the built-in regex library (prefix-less random tokens,
  PEM blocks, 100+ additional providers), and the ~50–150 ms per-prompt cost.
- **`tests/benchmark_entropy.py`**: standalone sweep script (not a unittest)
  that measures FP/FN rates over a labelled corpus across a grid of
  `min_entropy` (3.0→5.0, step 0.25) × `min_len` (16/20/24) combinations and
  prints a recommended operating point.
- 14 new unit tests covering context detection, entropy primitives, and the
  entropy layer opt-in behaviour (50 tests total, all passing).

## [0.1.0] — 2026-06-09

Initial release.

### Added

- **`UserPromptSubmit` hook** (`hooks/intercept.py`) that intercepts every
  submitted prompt, detects secrets, saves them out of band, and re-submits a
  sanitized version.
- **Regex detection** (`scripts/detect.py`) for ~20 well-known key formats:
  Anthropic, OpenAI (project + legacy), GitHub (classic / fine-grained / oauth
  / server / user), GitLab, Slack, Google API, AWS, Hugging Face, Stripe
  (live/test secret + pub + webhook), SendGrid, Replicate, npm, DigitalOcean,
  Mailgun, Linear, and generic JWTs.
- **Explicit markers**: `/key NAME=VALUE`, `KEY:NAME=VALUE`, and `KEY=VALUE`
  for tokens not covered by the regex library.
- **Placeholder filter**: values containing `EXAMPLE`, `PLACEHOLDER`, `XXX`,
  `YYY`, `FAKE`, `DUMMY`, `REDACTED`, `...`, or `***` are ignored so you can
  discuss key formats freely.
- **`/raw` bypass** to disable detection for a single prompt.
- **Cross-platform paste automation** (`scripts/automate_paste.py`):
  - macOS — `osascript` + `pbcopy`/`pbpaste`
  - Linux X11 — `xdotool` + `xclip`/`xsel`
  - Linux Wayland — `wtype` + `wl-clipboard` (compositor-dependent)
  - Windows — PowerShell `SendKeys` + `Set-Clipboard`/`Get-Clipboard`
  - Frontmost-app focus check to abort the paste if focus changed.
  - Clipboard backup/restore around the paste.
- **Optional gitleaks integration** (opt-in via `KEYWARD_USE_GITLEAKS=1`):
  a second detection pass using the gitleaks binary to catch formats the
  built-in regex misses. Off by default to avoid per-prompt subprocess latency.
- **Slash commands**: `/key`, `/key-list`, `/key-rm`, `/raw`.
- **`using-keyward` skill** that teaches Claude to consume saved secrets via
  `export VAR=$(cat ...)` without leaking them into stdout/context.
- **Cross-platform secret management** (`scripts/manage_secrets.py`) for
  `/key-list` and `/key-rm` (no bash dependency).
- **Test suite** (`tests/test_keyward.py`): 35 stdlib-only unittest cases
  covering detection, the hook end-to-end (sandboxed), and slot management.
- **CI** (`.github/workflows/ci.yml`): matrix over Ubuntu / macOS / Windows ×
  Python 3.9 / 3.12, plus a dedicated job exercising the gitleaks path.
- **`KEYWARD_DISABLE_PASTE=1`** escape hatch for SSH / headless / unsupported
  Wayland compositors (saves + sanitizes, you paste manually).

### Security

- Secrets dir `~/.claude/secrets/` is `chmod 700`; each secret file is
  `chmod 600`.
- Sanitized tempfiles are `chmod 600` and deleted after the paste completes.
- `/key-rm` overwrites file contents with zeros before unlink (best-effort).
- No network calls, no telemetry, no third-party runtime dependencies.

### Known limitations

- The session transcript may capture the raw value depending on Claude Code's
  write ordering — treat as defense-in-depth, not a guarantee (see README).
- Auto-paste has a ~350 ms race window and requires a display server.
- Linux Wayland support depends on the compositor implementing
  `virtual-keyboard-v1` (Sway/Hyprland yes; GNOME no by default).
- macOS requires Accessibility permission for the terminal app.

[Unreleased]: https://github.com/albemiglio/keyward/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/albemiglio/keyward/releases/tag/v0.1.0

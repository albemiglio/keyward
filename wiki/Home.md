# Keyward

**Auto-intercept API keys pasted into Claude Code chat.** Keyward is a Claude Code plugin whose `UserPromptSubmit` hook scans every message you submit; when it finds an API key it saves the value to a `chmod 600` file *before the model sees it*, **blocks** the original prompt, and **re-submits** a sanitized version automatically. It's the missing safety net for the "I just need to use this key once, in chat, now" workflow — where a vault is too heavy and rotating the key afterward is too annoying.

Keyward is not a replacement for a real secret manager. It's defense-in-depth for the ad-hoc paste. Read the [[Security-Model]] for exactly what it does and does not protect against — every gap is documented honestly.

## 30-second install

In a Claude Code session:

```text
/plugin marketplace add AlbeMiglio/keyward
/plugin install keyward@keyward
```

Then restart Claude Code. On macOS, grant Accessibility permission to your terminal app so the auto-paste can run; on Linux install the per-platform automation tools. Full per-OS steps (macOS, Linux X11, Linux Wayland, Windows, WSL) are in [[Installation]].

## How it works in one breath

1. You submit a prompt; the `UserPromptSubmit` hook (`hooks/intercept.py`) fires before the prompt is sent.
2. `scripts/detect.py` scans it — ~20-provider regex, explicit markers (`/key NAME=VALUE`), and an opt-in gitleaks pass.
3. Each detected secret is written to `~/.claude/secrets/<name>.txt` (`chmod 600`, atomic write).
4. The hook **blocks** the original prompt (`suppressOriginalPrompt`) so the raw value never reaches the API or the transcript.
5. A detached `scripts/automate_paste.py` puts a sanitized version — `<<secret:NAME stored at ~/.claude/secrets/NAME.txt>>` — on the clipboard and OS-pastes it (osascript / xdotool / wtype / PowerShell SendKeys) ~350 ms later.
6. The bundled `using-keyward` skill teaches Claude to consume the secret via `export VAR=$(cat ~/.claude/secrets/x.txt) && cmd` — never a bare `cat`.

The raw value never appears in the API call, the model context, or (best-effort — see [[Security-Model]]) the transcript.

## Navigation

**Getting started**

- [[Installation]] — per-platform setup: macOS, Linux X11, Linux Wayland, Windows, WSL, and the marketplace quick-start.
- [[Configuration]] — environment variables (`KEYWARD_DISABLE_PASTE`, `KEYWARD_USE_GITLEAKS`, `TMPDIR`) and the optional gitleaks pass.

**Reference**

- [[Architecture]] — the hook → detect → save → sanitize → paste pipeline, file layout, and why it's pure-Python stdlib.
- [[Security-Model]] — file permissions, threat model (what's covered, what isn't), and the honest limitations.
- [[Detection-Patterns]] — the ~20 regex providers, explicit markers, the placeholder filter, and `/raw` bypass.
- [[Troubleshooting]] — hook not firing, detection-works-but-paste-doesn't, per-platform diagnostics, standalone test commands.
- [[FAQ]] — does the key reach Anthropic, what if detection misses, encryption at rest, other AI CLIs, uninstalling, where data lives.

**Project**

- [[Contributing]] — running the test suite, adding regex patterns, Wayland compositor testing, project layout for contributors.

## Slash commands

| Command | What it does |
|---|---|
| `/key NAME=VALUE` | Explicit save — use for tokens the regex library doesn't cover. |
| `/key-list` | List saved slots (names, sizes, modification times — never values). |
| `/key-rm NAME` | Delete a slot (zero-overwrite before unlink, best-effort). |
| `/raw <text>` | Bypass detection for one prompt (e.g. discussing key formats). |

## Requirements

- **Python 3.9+** on `PATH` as `python3` (stdlib only — no `pip install`).
- **Claude Code** with plugin support.
- **Per-platform automation tools** — see [[Installation]].

---

MIT licensed. Source: [github.com/AlbeMiglio/keyward](https://github.com/AlbeMiglio/keyward).

<div align="center">

<img src="assets/social-preview.png" alt="Keyward — secrets never reach the model" width="820">

[![CI](https://github.com/AlbeMiglio/keyward/actions/workflows/ci.yml/badge.svg)](https://github.com/AlbeMiglio/keyward/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)
[![Platforms: macOS · Linux · Windows](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-blue)](#installation)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#requirements)

**Auto-intercept API keys pasted into Claude Code chat.** Keyward saves the value to a `chmod 600` file *before the model sees it*, then re-submits a sanitized version of your message — automatically. Zero-friction secret hygiene.

</div>

![keyward demo](demo/keyward-demo.gif)

> The GIF above shows the real detection + sanitization engine. The full
> in-editor block→auto-paste flow happens inside Claude Code's UI — install it
> (below) to see it live.

---

## Table of contents

- [The problem](#the-problem)
- [What this plugin does](#what-this-plugin-does)
- [Why Keyward (vs the alternatives)](#why-keyward-vs-the-alternatives)
- [Live example](#live-example)
- [Detected key formats](#detected-key-formats)
- [Requirements](#requirements)
- [Install](#install)
  - [Quick start — marketplace](#quick-start--marketplace)
  - [macOS](#installation--macos)
  - [Linux (X11)](#installation--linux-x11)
  - [Linux (Wayland)](#installation--linux-wayland)
  - [Windows (native)](#installation--windows-native)
  - [Windows + WSL](#installation--windows--wsl)
- [Usage](#usage)
- [Slash commands](#slash-commands)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Limitations (read these — they're honest)](#limitations)
- [Troubleshooting](#troubleshooting)
- [Configuration](#configuration)
- [Security model](#security-model)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## The problem

When you paste an API key into Claude Code chat:

1. The key is **sent to Anthropic's API** as part of your prompt
2. The key is **persisted in the local session transcript** (`*.jsonl` files)
3. Claude Code (correctly) shows a warning that the key has leaked and should
   be rotated

Rotating a key every time you reference one is friction. So is being careful
to never paste one. **This plugin removes the friction by intercepting the
key locally before it leaves your machine, on every prompt.**

## What this plugin does

A `UserPromptSubmit` hook scans every message you submit:

1. **Detects secrets** via regex (~20 well-known formats) OR explicit markers
   (`/key NAME=VALUE`, `KEY:NAME=VALUE`, `KEY=VALUE`)
2. **Saves** each detected secret to `~/.claude/secrets/<name>.txt` with
   `chmod 600` permissions
3. **Blocks** the original prompt (the raw value never reaches the model or
   the transcript)
4. **Re-submits** a sanitized version of your prompt automatically — values
   are replaced with `<<secret:NAME stored at ~/.claude/secrets/NAME.txt>>`
5. **Teaches Claude** (via a bundled skill) to USE the saved keys without
   leaking them: `export VAR=$(cat ~/.claude/secrets/x.txt) && cmd`, never
   bare `cat`

The re-submission uses OS-level keystroke automation (osascript / xdotool /
wtype / PowerShell SendKeys), so from your perspective you just press Enter
once and Claude responds to the cleaned-up version.

## Why Keyward (vs the alternatives)

You already have ways to handle secrets. Here's where each one leaves a gap that
Keyward fills:

| Approach | The gap |
|---|---|
| **Just rotate the key after pasting** | Works, but it's friction every single time, and you have to *remember*. Keyward makes the paste safe so there's nothing to rotate. |
| **Be careful never to paste keys** | Discipline fails under deadline. Keyward is a safety net that doesn't depend on you remembering. |
| **`1Password` / `Vault` / Keychain + reference by name** | Great for *stored* secrets you reference deliberately. Useless for the key a colleague just DM'd you that you want to use *right now* without a vault round-trip. Keyward catches the ad-hoc paste. |
| **`.env` file + `direnv`** | Good for project config. But you still had to get the key *into* `.env` without pasting it in chat — Keyward is how it gets there safely. |
| **Claude Code's built-in "key leaked, rotate it" warning** | Reactive: it tells you *after* the value already hit the API and the transcript. Keyward is proactive: the value never gets there. |
| **A `PreToolUse` hook / output filter** | Scrubs *Claude's* tool calls, not *your* prompt. The leak happens at prompt submission, upstream of any tool. Keyward hooks `UserPromptSubmit`, the only point early enough. |

Keyward isn't a replacement for a real secret manager — it's the missing piece
for the **"I just need to use this key once, in chat, now"** workflow, where a
vault is too heavy and rotation is too annoying.

## Live example

You type:

```
fai il deploy con la key ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

What happens (in <500 ms):

1. Hook fires, regex matches `ghp_...` → GitHub PAT
2. Value saved to `~/.claude/secrets/github_pat_classic.txt` (chmod 600)
3. Original message is **blocked** — you see it dimmed/cancelled
4. A new message appears automatically:
   ```
   fai il deploy con la key <<secret:github_pat_classic stored at ~/.claude/secrets/github_pat_classic.txt>>
   ```
5. Claude responds to the sanitized version, using
   `GITHUB_TOKEN=$(cat ~/.claude/secrets/github_pat_classic.txt) gh api ...`
   to actually use the key without ever putting the value in its own output.

The raw `ghp_...` value never appears in the API call, the model context, or
the transcript.

## Detected key formats

Auto-detected via regex (no marker needed):

| Provider | Pattern |
|---|---|
| Anthropic | `sk-ant-(api\|admin)NN-...` |
| OpenAI (project) | `sk-proj-...` |
| OpenAI (legacy) | `sk-...` |
| GitHub PAT (classic) | `ghp_...` |
| GitHub PAT (fine-grained) | `github_pat_...` |
| GitHub OAuth | `gho_...` |
| GitHub server-to-server | `ghs_...` |
| GitHub user-to-server | `ghu_...` |
| GitLab PAT | `glpat-...` |
| Slack token | `xox[baprs]-...` |
| Google API key | `AIza...` |
| AWS Access Key | `(AKIA\|ASIA)...` |
| Hugging Face | `hf_...` |
| Stripe (live/test secret/pub) | `sk_live_`, `sk_test_`, `pk_live_`, `whsec_` |
| SendGrid | `SG.xxx.yyy` |
| Replicate | `r8_...` |
| npm token | `npm_...` |
| DigitalOcean PAT | `dop_v1_...` |
| Mailgun | `key-...` |
| Linear | `lin_api_...` |
| JWT | `eyJ...eyJ...xxx` |

For anything not in the list (custom/internal tokens), use one of the
explicit markers:

```
/key prod_db=postgres://u:p@host/db        ← slash form
fai deploy con KEY:internal_api=mytokenXYZ ← inline named
salva questa KEY=randomvalue123            ← inline default slot
```

Placeholder/example values are ignored: any matched value containing
`EXAMPLE`, `PLACEHOLDER`, `XXX`, `YYY`, `FAKE`, `DUMMY`, `REDACTED`, `...`,
or `***` (case-insensitive) is left alone. So discussing key formats like
"`sk-ant-EXAMPLE...`" does not trigger the hook.

## Requirements

- **Python 3.9+** in your `PATH` as `python3`
- **Claude Code** with plugin support
- **Per-platform automation tools** (see [Installation](#installation))

## Install

### Quick start — marketplace

The fastest path. In a Claude Code session:

```text
/plugin marketplace add AlbeMiglio/keyward
/plugin install keyward@keyward
```

Then restart Claude Code. On macOS, also grant Accessibility permission to your
terminal (see the [macOS](#installation--macos) notes below) so the auto-paste
can run; on Linux install the per-platform tools listed in your section.

> Prefer to read the code before trusting it with your prompts? Use the manual
> clone-and-link method for your platform below — it's identical, just explicit.

### Installation — macOS

**1. Install platform deps:** macOS ships with `osascript`, `pbcopy`, and
`pbpaste` — nothing extra to install.

**2. Clone the plugin:**

```bash
git clone https://github.com/AlbeMiglio/keyward.git ~/keyward
```

(Or wherever you keep your plugins.)

**3. Link into Claude Code's plugin directory:**

```bash
mkdir -p ~/.claude/plugins
ln -s ~/keyward ~/.claude/plugins/keyward
```

**4. Grant Accessibility permission to your terminal app:**

- `System Settings` → `Privacy & Security` → `Accessibility`
- Click `+` and add your terminal: **Terminal.app**, **iTerm**, **Ghostty**,
  **Warp**, **Alacritty**, etc. — whichever you use to run Claude Code
- Toggle it on

Without this, the keystroke automation will fail silently and you'll need to
paste the sanitized text manually.

**5. Restart Claude Code:**

```bash
# Exit current session, then:
claude
```

Hooks load at session start; configuration changes require restart.

**6. Verify:**

In a Claude Code session, run `/hooks` — you should see:

```
UserPromptSubmit  →  python3 /Users/you/.claude/plugins/keyward/hooks/intercept.py
```

### Installation — Linux (X11)

**1. Install platform deps:**

```bash
# Debian/Ubuntu
sudo apt install python3 xdotool xclip

# Fedora/RHEL
sudo dnf install python3 xdotool xclip

# Arch
sudo pacman -S python xdotool xclip
```

(`xsel` works as a substitute for `xclip`.)

**2. Clone & link** (same as macOS steps 2–3).

**3. Restart Claude Code.** No additional permission grant is required —
X11 allows synthetic input by default.

**4. Verify** with `/hooks`.

### Installation — Linux (Wayland)

> ⚠️ **Wayland support is compositor-dependent.** Synthetic keystroke
> injection requires the compositor to implement the `virtual-keyboard-v1`
> protocol. **Sway** and **Hyprland** support it. **GNOME** blocks it by
> default (no fix without an extension). **KDE Plasma** depends on version.
> If your compositor blocks `wtype`, the hook will still save the secret and
> set the clipboard, but you'll need to `Ctrl+V + Enter` manually.

**1. Install platform deps:**

```bash
# Debian/Ubuntu
sudo apt install python3 wtype wl-clipboard

# Fedora
sudo dnf install python3 wtype wl-clipboard

# Arch
sudo pacman -S python wtype wl-clipboard
```

**2. Clone & link** (same as macOS).

**3. Test `wtype` on your compositor:**

```bash
echo "test ok" | wl-copy
sleep 2 && wtype -M ctrl v -m ctrl
# focus a text editor in the 2s window; if "test ok" appears, you're set
```

If `wtype` errors with `Compositor does not support virtual_keyboard_v1`,
you're on an unsupported compositor — the hook will degrade to "save +
clipboard set, paste manually."

**4. Restart Claude Code.**

### Installation — Windows (native)

**1. Install Python 3.9+** from [python.org](https://www.python.org/downloads/)
or via `winget install Python.Python.3.12`. Ensure `python3` is in `PATH`
(the installer offers a checkbox).

PowerShell ships with Windows — no extra install needed.

**2. Clone the plugin:**

```powershell
git clone https://github.com/AlbeMiglio/keyward.git "$env:USERPROFILE\keyward"
```

**3. Link / copy into the plugins directory:**

```powershell
# Native plugin dir
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\plugins"

# Symlink (requires admin OR Developer Mode):
New-Item -ItemType SymbolicLink `
    -Path "$env:USERPROFILE\.claude\plugins\keyward" `
    -Target "$env:USERPROFILE\keyward"

# Or copy if symlinks aren't available:
Copy-Item -Recurse "$env:USERPROFILE\keyward" "$env:USERPROFILE\.claude\plugins\keyward"
```

**4. Restart Claude Code** and verify with `/hooks`.

No special permission grant is required on Windows — `SendKeys` works against
the foreground window by default. (Some enterprise group policies disable
`SendKeys`; if yours does, the plugin will fall back to clipboard-only mode.)

### Installation — Windows + WSL

If you run Claude Code inside WSL, the hook executes inside WSL — but the
foreground window is hosted by Windows. Cross-boundary keystroke automation
is fragile. You have two options:

- **Recommended:** Install the plugin on the **WSL side** as a Linux install
  (X11 if you use an X server like VcXsrv/X410, or skip the automation and
  paste manually). The hook still saves and sanitizes; auto-paste just won't
  work for the WSL-window → Windows-host crossing.
- **Alternative:** Run Claude Code natively on Windows (see above).

For pure manual mode (no auto-paste, just save + clipboard set), set:

```bash
export KEYWARD_DISABLE_PASTE=1
```

in your shell rc. The hook will still save and sanitize; you copy and paste
yourself.

## Usage

Just type normally. The hook does the rest.

```
deploy con ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa            → auto-detected
/key prod_db=postgres://u:p@host/db then migrate                → explicit
fai deploy con KEY:stripe=sk_live_xxxxxxxx                      → inline named
salva questa KEY=randomvalue123                                 → inline default
/raw che formato ha una key tipo sk-ant-...?                    → bypass detection
```

### Using a saved key in a task

Just reference it. Claude (with the bundled `using-keyward` skill) knows
to read it safely:

```
deploy il bot a fly.io usando la key github salvata
→ Claude runs:  GITHUB_TOKEN=$(cat ~/.claude/secrets/github_pat_classic.txt) flyctl deploy
```

The skill **forbids** `cat ~/.claude/secrets/x.txt` as a standalone command,
because that would print the value into Claude's stdout context — defeating
the vault.

## Slash commands

| Command | What it does |
|---|---|
| `/key NAME=VALUE` | Explicit save (use for tokens not in the regex library) |
| `/key-list` | List saved slots (names + sizes + modification times — never values) |
| `/key-rm NAME` | Delete a slot (overwrites with zeros first, best-effort) |
| `/raw <text>` | Bypass detection for one prompt |

## How it works

```
┌─────────────────────────────────────────────────────────────────────────┐
│  user types prompt and presses Enter                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Claude Code fires UserPromptSubmit hook                                │
│  → python3 ${CLAUDE_PLUGIN_ROOT}/hooks/intercept.py                     │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  intercept.py:                                                          │
│   1. read JSON {user_prompt: "..."} from stdin                          │
│   2. detect.py scans prompt with regex + explicit markers               │
│   3. for each secret: save to ~/.claude/secrets/<name>.txt (chmod 600)  │
│   4. build sanitized prompt with <<secret:NAME ...>> references         │
│   5. write sanitized to $TMPDIR/keyward/sanitized_<rand>.txt          │
│   6. fork-and-detach automate_paste.py (will run AFTER hook returns)    │
│   7. emit JSON: {"decision":"block","suppressOriginalPrompt":true,...}  │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Claude Code receives block JSON → original prompt suppressed entirely  │
│  (the raw value never reaches the API or the transcript)                │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                          ~350 ms later
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  automate_paste.py (detached child):                                    │
│   1. backs up current clipboard contents                                │
│   2. puts sanitized text in clipboard (pbcopy / xclip / wl-copy / etc.) │
│   3. verifies frontmost app hasn't changed                              │
│   4. simulates Cmd/Ctrl+V → 50ms → Enter                                │
│   5. waits 300ms → restores original clipboard                          │
│   6. deletes the sanitized tempfile                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Claude receives the sanitized prompt as a fresh user message,          │
│  processes it normally, responds.                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## Architecture

```
keyward/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest (name, version, author, etc.)
├── hooks/
│   ├── hooks.json            # Hook registration (UserPromptSubmit → intercept.py)
│   └── intercept.py          # Main orchestrator: detect → save → sanitize → spawn
├── scripts/
│   ├── detect.py             # Pure detection: regex + explicit markers (testable)
│   ├── automate_paste.py     # Cross-platform paste+enter (osascript/xdotool/wtype/SendKeys)
│   └── manage_secrets.py     # Cross-platform list/remove for slash commands
├── commands/
│   ├── key.md                # /key NAME=VALUE
│   ├── key-list.md           # /key-list
│   ├── key-rm.md             # /key-rm NAME
│   └── raw.md                # /raw <text>
├── skills/
│   └── using-keyward/
│       └── SKILL.md          # Teaches Claude to use saved keys safely
├── tests/
│   └── test_keyward.py      # 35 stdlib unittest cases (detect/intercept/manage)
├── demo/
│   ├── demo.py               # Narration driver (real engine, fake key, sandboxed)
│   ├── demo.tape             # VHS script to render the GIF
│   └── keyward-demo.gif    # Rendered demo
├── .github/
│   └── workflows/
│       └── ci.yml            # Ubuntu/macOS/Windows × py3.9/3.12 + gitleaks job
├── CHANGELOG.md              # Keep-a-changelog history
├── README.md                 # This file
└── LICENSE                   # MIT
```

**Why Python (not bash)?** Bash isn't a first-class citizen on Windows.
Keeping the whole runtime in Python 3.9+ stdlib (no `pip install`) means
the same plugin works identically on macOS, Linux, and Windows.

## Limitations

These are real. Read them before relying on this plugin for production secrets.

1. **The transcript may have already captured the key.** Claude Code's
   transcript write order vs. hook execution order is not formally documented.
   If the transcript is written before the hook runs, your raw value is in
   `~/.claude/projects/.../session_*.jsonl` even though the API call was
   blocked. **Treat the vault as defense-in-depth, not absolute guarantee.**
   If a key value appears visibly in a prior assistant message in the
   transcript, rotate it.

2. **300 ms race window** for the auto-paste. If you alt-tab to another
   window in the 350 ms between pressing Enter and the paste, the script
   detects focus change and aborts (the sanitized text stays in clipboard,
   you paste it yourself).

3. **Clipboard is temporarily overwritten.** Your previous clipboard is
   saved before and restored ~600 ms after. If you `Cmd+C` something else
   in that window, your copy wins and the original is lost.

4. **macOS Accessibility permission required** for auto-paste. Without it,
   the keystroke automation fails silently. The secret is still saved and
   the sanitized text is still in the clipboard — you just paste manually.

5. **Linux Wayland is hit-or-miss.** Sway/Hyprland work. GNOME blocks
   synthetic input by default. KDE depends on version. The plugin degrades
   to "save + clipboard set, paste manually" gracefully.

6. **Detection regex is curated, not exhaustive.** ~20 well-known formats are
   recognized. A custom internal token (no known prefix) needs explicit
   `/key NAME=VALUE` registration. False positives are possible for any
   sufficiently-random string matching `sk-[A-Za-z0-9]{32,}` — use `/raw` to
   bypass for one prompt.

7. **`/raw` disables protection entirely** for the prompt it prefixes. Don't
   use it for messages that actually contain real, live keys.

8. **No SSH / remote / headless support.** The auto-paste needs a display
   server. In SSH sessions or headless environments, set
   `KEYWARD_DISABLE_PASTE=1` — the hook will save and sanitize, you paste
   manually.

## Troubleshooting

**Hook not firing**

- Restart Claude Code (hooks load at session start)
- Run `claude --debug` and look for hook registration warnings
- Verify with `/hooks` in a session
- Check that `python3 --version` works in your shell

**Detection works, paste doesn't (macOS)**

- Check `~/.claude/secrets/.last-error`
- Most common cause: missing Accessibility permission. Re-grant it to your
  terminal app and restart the terminal.
- Try `osascript -e 'tell application "System Events" to keystroke "x"'`
  from a regular terminal — if that fails too, your permissions are wrong.

**Detection works, paste doesn't (Linux X11)**

- `which xdotool xclip` — both must be in PATH
- Try `xdotool key x` in a focused text field — if that does nothing, your
  display server is rejecting synthetic input (rare on X11)

**Detection works, paste doesn't (Linux Wayland)**

- Your compositor probably doesn't support `virtual-keyboard-v1`
- Test: `wtype "hello"` in a focused text field
- If it errors, set `KEYWARD_DISABLE_PASTE=1` and use clipboard mode

**Detection works, paste doesn't (Windows)**

- Check `~/.claude/secrets/.last-error`
- Some enterprise group policies disable `SendKeys` — check with your IT

**Test the detection layer standalone**

```bash
echo '{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' \
  | python3 ~/.claude/plugins/keyward/scripts/detect.py
```

Should output: `{"secrets": [{"name": "github_pat_classic", "value": "ghp_...", ...}], "raw_mode": false}`

**Test the orchestrator without triggering paste**

```bash
# Note: the env var must be set on the python3 process, not on `echo` —
# a here-string is the clean way to do that.
KEYWARD_DISABLE_PASTE=1 \
  python3 ~/.claude/plugins/keyward/hooks/intercept.py \
  <<<'{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
```

**Where are the secrets stored?**

`~/.claude/secrets/` — chmod 700 on the dir, chmod 600 on each `<name>.txt`
file. View names (never values) with `/key-list` or
`ls -la ~/.claude/secrets/`.

## Configuration

All config is via environment variables:

| Variable | Effect |
|---|---|
| `KEYWARD_DISABLE_PASTE=1` | Skip the auto-paste spawn entirely. Hook still saves + sanitizes, you paste manually. Useful for SSH, WSL, or unsupported Wayland compositors. |
| `KEYWARD_USE_GITLEAKS=1` | Enable the optional gitleaks detection pass (see below). Requires the `gitleaks` binary in `PATH`. Off by default. |
| `TMPDIR` / `TEMP` / `TMP` | Override where sanitized tempfiles are written (default: the OS temp dir + `/keyward`). Honored cross-platform via Python's `tempfile.gettempdir()`. |
| `CLAUDE_PLUGIN_ROOT` | Set by Claude Code automatically. Falls back to script's parent dir if unset (manual invocation). |

### Optional: deeper detection with gitleaks

The built-in regex library covers ~20 well-known providers. For broader
coverage — generic high-entropy keys, private-key blocks, and dozens of
additional providers — you can enable a second detection pass powered by
[gitleaks](https://github.com/gitleaks/gitleaks).

**1. Install gitleaks:**

```bash
brew install gitleaks          # macOS
# or: https://github.com/gitleaks/gitleaks#installing
```

**2. Enable the pass** by adding the env var to your shell rc (so Claude Code
inherits it):

```bash
export KEYWARD_USE_GITLEAKS=1
```

**3. Restart Claude Code.**

When enabled, every prompt is also scanned by gitleaks; any finding the regex
layer missed is saved and sanitized with `source: gitleaks`. The placeholder
filter still applies (example/dummy values are ignored).

**Trade-off:** this adds a ~50–150 ms subprocess spawn to *every* prompt, which
is why it's off by default. gitleaks' `generic-api-key` rule can also be noisy
on high-entropy strings — use `/raw` to bypass a false positive. The regex-only
default stays fast and conservative.

## Security model

- Secrets dir: `~/.claude/secrets/`, `chmod 700`
- Each secret: `~/.claude/secrets/<name>.txt`, `chmod 600`
- Sanitized tempfiles: `$TMPDIR/keyward/sanitized_<random-hex>.txt`, `chmod 600`,
  deleted by `automate_paste.py` after paste completes
- `/key-rm` uses `os.write` over the file contents before unlink (best-effort
  secure delete; **not guaranteed** on SSDs with wear-leveling or COW
  filesystems like APFS / Btrfs / ZFS)
- No network calls
- No telemetry
- No third-party dependencies (Python stdlib only)
- Error log at `~/.claude/secrets/.last-error` — only error messages, never
  secret values

**Threat model addressed:**
- ✅ Casual paste of a key into chat (the common case)
- ✅ Key value reaching the model context
- ✅ Key value reaching the live transcript (best-effort; see Limitations #1)
- ✅ Key value persisting in clipboard after paste

**Threat model NOT addressed:**
- ❌ Malicious plugin reading `~/.claude/secrets/` (any plugin with file
  system access can read these files)
- ❌ Adversary with physical/SSH access to your machine
- ❌ Keylogger between your keyboard and the terminal
- ❌ Memory-resident attacks
- ❌ Backup tools that ignore file permissions

For high-stakes secrets, use a proper secret manager (`1Password CLI`,
macOS Keychain via `security`, HashiCorp Vault, etc.) and reference them by
name. This plugin is for the daily "I just need to use this key once, don't
want to rotate it after pasting" workflow.

## FAQ

**Does the key still get sent to Anthropic?**
No — that's the entire point. The `UserPromptSubmit` hook fires *before* the
prompt is sent. Keyward blocks the original prompt (the one containing the raw
value) and re-submits a sanitized one. The model and the API only ever see the
`<<secret:NAME ...>>` reference.

**What if I forget and the hook misses my key?**
Two layers reduce this: the ~20-provider regex catches common formats with no
marker, and you can force-tag anything with `/key NAME=VALUE`. For maximum
coverage, enable the [optional gitleaks pass](#optional-deeper-detection-with-gitleaks).
If a value genuinely slips through (custom format, gitleaks off), treat it like
any leak and rotate — Keyward is defense-in-depth, not a guarantee.

**Will it trigger when I'm just *talking* about keys?**
Values containing `EXAMPLE`, `PLACEHOLDER`, `XXX`, `FAKE`, `DUMMY`, etc. are
ignored. For anything else, prefix the message with `/raw ` to bypass detection
for that one prompt.

**Does Claude ever see the real value when it *uses* the key?**
No. The bundled `using-keyward` skill teaches Claude to expand the secret inline
in a single shell command — `export VAR=$(cat ~/.claude/secrets/x.txt) && cmd`
— so the value flows disk → process env → tool, never through stdout or the
model's context.

**Is my key encrypted at rest?**
No. It's stored as a `chmod 600` plaintext file under `~/.claude/secrets/`,
readable only by your user. This is the same trust model as `~/.aws/credentials`
or a `.env` file. If you need encryption at rest, use a real secret manager and
reference it by path — Keyward deliberately doesn't reinvent one.

**Why does the prompt flash red / get cancelled?**
That's the `block` decision doing its job: the original prompt (with the raw
value) is rejected, and the sanitized version is pasted and submitted in its
place. You see a brief cancelled message, then the clean one.

**It saved the key but didn't auto-paste. Why?**
The save always succeeds; the *paste* needs OS automation. On macOS that means
Accessibility permission for your terminal; on Wayland it's compositor-dependent.
Check `~/.claude/secrets/.last-error`. The sanitized text is on your clipboard —
just `Cmd/Ctrl+V` + Enter. Or set `KEYWARD_DISABLE_PASTE=1` to always paste
manually.

**Does this work in SSH / headless / Docker?**
Detection and saving do. Auto-paste needs a display server, so set
`KEYWARD_DISABLE_PASTE=1` and paste manually in those environments.

**Can I use it with other AI CLIs (Cursor, Codex, Gemini)?**
Not yet — Keyward relies on Claude Code's `UserPromptSubmit` hook, which those
tools don't currently expose. See the project notes for why an OS-level
text-expander is the only cross-tool option today.

## Contributing

Issues and PRs welcome. Key areas where help is wanted:

- Additional regex patterns for less-common providers
- Wayland compositor compatibility testing (Sway / Hyprland / KDE / GNOME)
- Windows-native edge cases (SendKeys under different focus models)
- `detect-secrets` (Yelp) as an alternative to gitleaks for the optional pass
- A `/key-rotate` command that calls provider-specific rotation APIs

To develop:

```bash
git clone https://github.com/AlbeMiglio/keyward.git
cd keyward

# Run the full test suite (35 tests, stdlib only — no pip install needed)
python3 -m unittest discover -s tests -p 'test_*.py' -v

# The gitleaks integration tests self-skip unless gitleaks is installed.
# To exercise them locally:
brew install gitleaks
python3 -m unittest discover -s tests -p 'test_*.py' -v

# Test detection on a single sample input
echo '{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' | python3 scripts/detect.py

# Test the orchestrator end-to-end without triggering the real paste
KEYWARD_DISABLE_PASTE=1 \
  python3 hooks/intercept.py <<<'{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'

# Re-render the demo GIF (requires charmbracelet/vhs)
vhs demo/demo.tape
```

### Project layout for contributors

| Path | Purpose |
|---|---|
| `scripts/detect.py` | Pure detection logic — start here for new patterns. Has no side effects, easy to unit-test. |
| `hooks/intercept.py` | Orchestration: save, sanitize, spawn paste, emit hook JSON. |
| `scripts/automate_paste.py` | Per-platform paste backends. Add compositor support here. |
| `scripts/manage_secrets.py` | `/key-list` and `/key-rm` implementation. |
| `tests/test_keyward.py` | The whole test suite. Add a case alongside any change. |
| `demo/` | `demo.py` narration driver + `demo.tape` VHS script. |

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- The Claude Code hooks API for making this possible
- [gitleaks](https://github.com/gitleaks/gitleaks) and
  [detect-secrets](https://github.com/Yelp/detect-secrets) for the curated
  regex library that inspired this one

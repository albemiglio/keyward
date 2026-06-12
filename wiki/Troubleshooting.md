# Troubleshooting

Symptom → cause → fix for Keyward, with copy-pasteable diagnostics. Most issues fall into one of two buckets: **the hook isn't firing at all** (detection never runs) or **detection runs but the auto-paste doesn't land** (a per-platform layer-2 problem). The first thing to know is which bucket you're in — the [quick triage](#quick-triage) below tells you in two commands.

See also: [[Installation]] · [[Configuration]] · [[Security-Model]] · [[FAQ]] · [[Home]]

---

## Contents

- [Quick triage](#quick-triage)
- [Symptom → cause → fix table](#symptom--cause--fix-table)
- [Hook not firing](#hook-not-firing)
- [Detection works but no paste](#detection-works-but-no-paste)
  - [macOS — Accessibility](#macos--accessibility-permission)
  - [Linux X11 — missing xdotool/xclip](#linux-x11--missing-xdotoolxclip)
  - [Linux Wayland — compositor support](#linux-wayland--compositor-support)
  - [Windows — SendKeys policy](#windows--sendkeys-policy)
- [Paste lands in the wrong window (focus race)](#paste-lands-in-the-wrong-window-focus-race)
- [Clipboard not restored](#clipboard-not-restored)
- [False positives — it triggers when I'm just talking about keys](#false-positives)
- [False negatives — it missed my key](#false-negatives)
- [Reading ~/.claude/secrets/.last-error](#reading-claudesecretslast-error)
- [Testing the engine standalone from the CLI](#testing-the-engine-standalone-from-the-cli)

---

## Quick triage

**1. Does the detection layer run?** (No display server needed — works everywhere.)

```bash
echo '{"user_prompt": "x ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' \
  | python3 ~/.claude/plugins/keyward/scripts/detect.py
```

- **Outputs a JSON `secrets` array** → the engine is fine. Your problem is either hook registration ([Hook not firing](#hook-not-firing)) or the paste layer ([Detection works but no paste](#detection-works-but-no-paste)).
- **`command not found` / `No such file`** → the plugin isn't where you think. Re-check the symlink/copy in [[Installation]].
- **A Python traceback** → your `python3` is too old or broken. Run `python3 --version` (need 3.9+).

**2. Is the hook registered?** In a Claude Code session:

```text
/hooks
```

If there's no `UserPromptSubmit → intercept.py` line, the engine works but Claude Code isn't calling it → [Hook not firing](#hook-not-firing).

**3. Did the last paste attempt log an error?**

```bash
cat ~/.claude/secrets/.last-error
```

This file only exists if something in the paste layer failed. It never contains secret values — only error text. See [Reading the error log](#reading-claudesecretslast-error).

---

## Symptom → cause → fix table

| Symptom | Likely cause | Fix |
|---|---|---|
| `/hooks` shows no Keyward entry | Plugin not installed where Claude Code looks, or session predates install | Re-check symlink in `~/.claude/plugins/keyward`; **restart Claude Code** (hooks load at session start). See [Hook not firing](#hook-not-firing). |
| Nothing happens at all on any prompt | `python3` not on PATH, or `detect.py` import failed → hook fails open (empty JSON, prompt passes through) | `python3 --version`; run the [standalone detect test](#testing-the-engine-standalone-from-the-cli). |
| Key **saved** but prompt **not** auto-pasted (macOS) | Terminal lacks Accessibility permission | Grant it, **fully restart the terminal**. See [macOS](#macos--accessibility-permission). |
| Saved but not pasted (Linux X11) | `xdotool` or clipboard tool missing | `which xdotool xclip xsel`; install. See [X11](#linux-x11--missing-xdotoolxclip). |
| Saved but not pasted (Linux Wayland) | Compositor lacks `virtual-keyboard-v1` | Test `wtype`; if unsupported, set `KEYWARD_DISABLE_PASTE=1`. See [Wayland](#linux-wayland--compositor-support). |
| Saved but not pasted (Windows) | Group policy disables `SendKeys`, or `python3` alias missing | Check `.last-error`; see [Windows](#windows--sendkeys-policy). |
| Sanitized text pastes into the **wrong** app | You changed focus during the ~350 ms paste delay (macOS aborts; others may not) | Don't switch windows after Enter; see [focus race](#paste-lands-in-the-wrong-window-focus-race). |
| Clipboard has the sanitized prompt afterward, not my old contents | You copied something else during the ~600 ms restore window, or the paste was aborted | See [clipboard not restored](#clipboard-not-restored). |
| Blocked a prompt where I was just **discussing** a key format | A real-looking value with no placeholder token matched the regex | Prefix the message with `/raw `. See [false positives](#false-positives). |
| Didn't catch my key | Custom/unknown format, or value contained a placeholder token | Use `/key NAME=VALUE`, or enable gitleaks. See [false negatives](#false-negatives). |
| Prompt "flashes red" / gets cancelled then a clean one appears | **This is correct behavior** — the `block` decision suppresses the raw prompt and the sanitized one is submitted in its place | Nothing to fix. |

---

## Hook not firing

Detection never runs — no block, no save, no `.last-error`. Causes, in order of likelihood:

1. **Session started before the plugin was installed.** Hooks are registered at session start. **Quit and relaunch `claude`.**
2. **Plugin not in the expected directory.** Confirm:
   ```bash
   ls -l ~/.claude/plugins/keyward          # should resolve (symlink → your clone, or a real dir)
   ls ~/.claude/plugins/keyward/hooks/hooks.json
   ```
   If the symlink is dangling (clone moved/deleted), re-create it per [[Installation]].
3. **`python3` not resolvable in the environment Claude Code launched from.** The hook command is `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/intercept.py`. If `python3` isn't on PATH, the hook can't start.
   ```bash
   python3 --version          # need 3.9+
   command -v python3
   ```
   On **Windows**, if only `python` exists and not `python3`, either install the official python.org build (it provides `python3`) or disable the conflicting "python3" App Execution Alias under **Settings → Apps → Advanced app settings → App execution aliases**.
4. **Claude Code didn't load the plugin.** Launch with debug and look for hook-registration warnings:
   ```bash
   claude --debug
   ```
   Then confirm in-session with `/hooks`.
5. **`detect.py` is missing or unparseable.** `intercept.py` **fails open** if it can't import `detect` — it prints `{}` and lets your prompt through unchanged (by design: better to pass a prompt than to swallow your message). So a broken `detect.py` looks exactly like "hook does nothing." Verify the engine directly with the [standalone test](#testing-the-engine-standalone-from-the-cli).

> **Why fail-open matters here:** almost every error path in `intercept.py` emits empty JSON and lets the original prompt proceed. That's deliberate — Keyward will never block your message because of its own bug. The flip side is that a misconfigured Keyward is silent, so use the standalone tests to tell "working but no secrets" apart from "not running."

---

## Detection works but no paste

The secret **was** saved (check `ls -la ~/.claude/secrets/`) but the clean prompt didn't get typed back in. This is a **layer-2** (automation) issue — the security layer did its job. The sanitized text is already on your clipboard, so the immediate unblock is always: **`Cmd/Ctrl+V` then Enter.** Below is how to fix the automation per platform. Start by reading [`~/.claude/secrets/.last-error`](#reading-claudesecretslast-error) — `automate_paste.py` writes the precise failure there.

### macOS — Accessibility permission

By far the most common cause. `automate_paste.py` drives `osascript` → System Events to send `Cmd+V` + Return, and macOS silently drops synthetic keystrokes from apps without **Accessibility** permission.

**Fix:**

1. **System Settings → Privacy & Security → Accessibility**
2. Add and enable your terminal app (**Terminal.app**, **iTerm**, **Ghostty**, **Warp**, **Alacritty**, **kitty**, **WezTerm**, or **Visual Studio Code** for its integrated terminal).
3. **Fully quit and reopen** the terminal — the permission is read at process launch, so a running terminal won't pick it up.

**Confirm the permission independently of Keyward** — run this in the same terminal; if it does nothing or errors, the permission is the problem, not Keyward:

```bash
osascript -e 'tell application "System Events" to keystroke "x"'
```

Focus a text field first; if no `x` appears, fix Accessibility. Also confirm the clipboard tools resolve (they're built in, so this should always pass):

```bash
command -v osascript pbcopy pbpaste
```

### Linux X11 — missing xdotool/xclip

`automate_paste.py` needs **`xdotool`** plus **one** of `xclip` / `xsel`. If either piece is absent, the backend reports unavailable and falls back to clipboard-only (it still tries to set the clipboard via any working backend).

```bash
which xdotool xclip xsel       # need xdotool + (xclip OR xsel)
```

Install the missing piece (`sudo apt install xdotool xclip`, or the `dnf`/`pacman` equivalents in [[Installation]]). Then verify synthetic input works at all on your session:

```bash
# focus a text field, then:
xdotool key x
```

If that types nothing, your X server is rejecting synthetic input (rare on X11). Also sanity-check you're really on X11, not Wayland:

```bash
echo "$XDG_SESSION_TYPE"         # 'x11' here; if 'wayland', see the Wayland section
```

### Linux Wayland — compositor support

Keyward uses **`wtype`** + **`wl-clipboard`** on Wayland, and `wtype` only works if the compositor implements `virtual-keyboard-v1`. **Sway** and **Hyprland** do; **GNOME/Mutter** does not (no fix without an extension); **KDE/KWin** is version-dependent.

**Test directly:**

```bash
echo "kv test" | wl-copy
sleep 2 && wtype -M ctrl v -m ctrl     # focus an editor during the 2s window
```

If `wtype` prints `Compositor does not support virtual_keyboard_v1` (or nothing pastes), auto-paste cannot work on your compositor. The clean fallback:

```bash
# add to ~/.bashrc / ~/.zshrc so Claude Code inherits it, then restart Claude Code
export KEYWARD_DISABLE_PASTE=1
```

With that set, Keyward skips the doomed keystroke attempt; it still saves the secret and sets the clipboard, and you paste with `Ctrl+V` + Enter. See [[Configuration]].

> **Note on the focus check:** the Wayland backend has no portable way to read the frontmost window, so it deliberately **skips** the focus-race guard. That makes the [focus race](#paste-lands-in-the-wrong-window-focus-race) slightly more likely on Wayland than on macOS — don't switch windows right after pressing Enter.

### Windows — SendKeys policy

The Windows backend uses PowerShell `Set-Clipboard`/`Get-Clipboard` and `System.Windows.Forms.SendKeys`. Two things can break it:

1. **Enterprise group policy disabling `SendKeys`/`System.Windows.Forms`.** `.last-error` will show a non-zero `SendKeys exit=` or an exception. Check with your IT; if it's locked down, you're in clipboard-only mode — paste manually or set `KEYWARD_DISABLE_PASTE=1`.
2. **`python3` not resolvable**, so the hook itself never runs (this is really a [Hook not firing](#hook-not-firing) case). Confirm `python3 --version`, and watch for the App Execution Alias conflict noted above.

Verify PowerShell is reachable:

```powershell
Get-Command pwsh, powershell -ErrorAction SilentlyContinue
```

---

## Paste lands in the wrong window (focus race)

**Cause.** After the prompt is blocked, `automate_paste.py` waits ~350 ms (`PASTE_DELAY_S`) so Claude Code can render the "blocked" state, then sends `Ctrl/Cmd+V` + Enter to **whatever window is focused at that instant**. If you alt-tab away during that window, the paste can land elsewhere.

**Mitigation built in (macOS).** Before pasting, the backend captures the frontmost app name and compares it to the app that was frontmost when the hook fired. If they differ, it **aborts the paste**, leaves the sanitized text in the clipboard, restores the original clipboard, and logs:

```
automate_paste.py: frontmost changed 'iTerm2' -> 'Safari' — paste aborted (sanitized text left in clipboard)
```

**Where the guard does _not_ apply:**

- **Linux X11** and **Windows** — `intercept.py` only computes the frontmost app on macOS; on these platforms it passes an empty expected-app, so the early focus check is skipped. (The X11 backend _can_ read the active window class but isn't given an expected value to compare against.)
- **Linux Wayland** — the backend can't read the frontmost window portably, so the check is skipped there too.

**What to do:**

- **Don't switch windows after pressing Enter** until the clean prompt appears (it's well under a second).
- If a paste landed in the wrong app: the sanitized text is on your clipboard — paste it into Claude Code manually (`Cmd/Ctrl+V` + Enter), and your secret is already saved.
- For maximum control, set `KEYWARD_DISABLE_PASTE=1` and paste every sanitized prompt yourself — no race at all. See [[Configuration]].

---

## Clipboard not restored

**Normal behavior.** `automate_paste.py` snapshots your clipboard, writes the sanitized text into it, pastes, waits ~300 ms (`RESTORE_DELAY_S`), then restores the snapshot. End to end the clipboard is "borrowed" for roughly half a second.

**When the original is lost:**

- **You copied something else during the borrow window.** A `Cmd/Ctrl+C` in that ~600 ms beats the restore — your new copy wins and the snapshot is discarded. There's no recovery; just re-copy what you needed.
- **The paste was aborted by the focus guard (macOS).** In that path the original clipboard **is** restored, but the sanitized text was never pasted — so you may still see the sanitized prompt if you copied nothing else. Paste it where you intended.
- **`set_clipboard` failed at restore time** (clipboard tool flaked). `.last-error` may note a set-clipboard failure. Re-run your copy.

**To sidestep clipboard borrowing entirely**, run in manual mode (`KEYWARD_DISABLE_PASTE=1`). The hook then leaves the sanitized text in a tempfile and never touches your clipboard via the auto-paste path.

---

## False positives

**Symptom.** You're discussing a key format ("what does an `sk-ant-` token look like?") or pasting logs with dead tokens, and Keyward blocks the prompt.

**Why.** A value that matches a known pattern and has no placeholder token reads as a real secret. Keyward already ignores any matched value containing (case-insensitive) `EXAMPLE`, `PLACEHOLDER`, `XXX`, `YYY`, `REDACTED`, `FAKE`, `DUMMY`, `...`, or `***` — so `sk-ant-EXAMPLE...` won't trigger. But a realistic, placeholder-free string will.

**Fix — bypass detection for that one prompt with `/raw`:**

```text
/raw what's the structure of a ghp_ token vs a github_pat_ one?
```

`/raw ` strips the prefix and re-submits the remainder **with no scanning at all**. Use it only when you're certain the message has no real, live secret — `/raw ` disables protection for that prompt entirely. (Mechanically: `detect.py` returns `raw_mode: true` on a leading `/raw `, and `intercept.py` re-submits the stripped text.)

**Confirm whether a given string trips detection** without sending it to Claude:

```bash
echo '{"user_prompt": "PASTE THE TEXT HERE"}' \
  | python3 ~/.claude/plugins/keyward/scripts/detect.py
```

Empty `secrets` array → it would pass through untouched. Non-empty → it would be blocked/sanitized.

---

## False negatives

**Symptom.** A real key went through to the model / transcript untouched.

**Causes & fixes:**

1. **Custom or internal token with no known prefix.** The regex library covers ~20 well-known providers; a bespoke format won't match. **Force-tag it** with an explicit marker:
   ```text
   /key prod_db=postgres://u:p@host/db          ← slash form (named slot)
   deploy with KEY:internal_api=mytokenXYZ      ← inline named
   save this KEY=randomvalue123                 ← inline default slot
   ```
   Explicit markers are always treated as secrets (sources `explicit_slash` / `explicit_named` / `explicit_default`).
2. **The value contained a placeholder token.** If your real key happens to contain `XXX`, `FAKE`, etc., the discussion-safe filter skips it. Rename/rotate, or register it explicitly with `/key` (the placeholder filter applies to explicit markers too, so pick a name that doesn't embed a placeholder substring in the **value**).
3. **Broader coverage wanted.** Enable the optional **gitleaks** pass for high-entropy/generic keys and dozens more providers:
   ```bash
   export KEYWARD_USE_GITLEAKS=1     # requires the gitleaks binary on PATH; restart Claude Code
   ```
   Findings the regex layer missed are saved with `source: gitleaks`. Trade-off: ~50–150 ms per prompt and occasional noise on high-entropy strings (use `/raw` for those). Details in [[Configuration]].

**If a key already slipped through, rotate it.** Keyward is defense-in-depth, not a guarantee — see the transcript-ordering caveat in [[Security-Model]].

**Reproduce/inspect what would be detected:**

```bash
# regex-only (default)
echo '{"user_prompt": "tok glpat-xxxxxxxxxxxxxxxxxxxx"}' \
  | python3 ~/.claude/plugins/keyward/scripts/detect.py

# with gitleaks pass (must have gitleaks installed)
KEYWARD_USE_GITLEAKS=1 python3 ~/.claude/plugins/keyward/scripts/detect.py \
  <<<'{"user_prompt": "tok <some-generic-high-entropy-string>"}'
```

---

## Reading ~/.claude/secrets/.last-error

`automate_paste.py` (and some `intercept.py` paths) append a timestamped line here on failure. **It contains only error text — never secret values, never the sanitized prompt body.** The file is created lazily, so its absence means "no paste error has occurred."

```bash
cat ~/.claude/secrets/.last-error
# or just the most recent failures:
tail -n 20 ~/.claude/secrets/.last-error
```

**How to read common lines:**

| Log line (excerpt) | Meaning | Action |
|---|---|---|
| `macOS osascript exit=1: ...` | System Events keystroke rejected | Grant Accessibility, restart terminal — see [macOS](#macos--accessibility-permission) |
| `no usable backend (platform=...)` | Required tools not installed for the detected platform | Install per-platform deps — see [[Installation]] |
| `frontmost changed 'A' -> 'B' — paste aborted` | You switched focus mid-paste (macOS guard) | Don't switch windows after Enter — see [focus race](#paste-lands-in-the-wrong-window-focus-race) |
| `linux-x11 xdotool ... exit=...` | `xdotool` ran but the key event failed | Check the X session accepts synthetic input |
| `linux-wayland wtype ... exit=...` | Compositor rejected the virtual keystroke | Compositor unsupported — set `KEYWARD_DISABLE_PASTE=1` |
| `windows SendKeys exit=...` | PowerShell `SendKeys` blocked or errored | Check group policy — see [Windows](#windows--sendkeys-policy) |
| `failed to set clipboard` | Clipboard tool failed to write | Reinstall/verify the clipboard tool for your platform |

Clear it any time (it's just a log):

```bash
rm -f ~/.claude/secrets/.last-error
```

---

## Testing the engine standalone from the CLI

All of these work outside Claude Code and don't touch the network. Use absolute paths under `~/.claude/plugins/keyward/` (your install location).

**1. Detection only** — fastest signal that the engine works. Prints what _would_ be saved/sanitized; no files written, no paste:

```bash
echo '{"user_prompt": "deploy ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' \
  | python3 ~/.claude/plugins/keyward/scripts/detect.py
```

Expected: a `secrets` array with one `github_pat_classic` entry, `source: "regex"`, `raw_mode: false`.

**2. The orchestrator end-to-end, without triggering a real paste.** `KEYWARD_DISABLE_PASTE=1` makes `intercept.py` skip the detached `automate_paste.py` spawn, so this **does** write the secret to `~/.claude/secrets/` and emit the block JSON, but won't move your mouse/keyboard or clipboard:

```bash
KEYWARD_DISABLE_PASTE=1 python3 ~/.claude/plugins/keyward/hooks/intercept.py \
  <<<'{"user_prompt": "deploy ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
```

Expected stdout: `{"decision": "block", "reason": "[keyward] Intercepted 1 secret(s): github_pat_classic [regex]. ...", "suppressOriginalPrompt": true}`. Afterward, `ls -la ~/.claude/secrets/` shows `github_pat_classic.txt` (chmod 600). Use a throwaway value — this really does save it.

> **Important:** the env var must be set **for the `python3` process**. `KEYWARD_DISABLE_PASTE=1 python3 ... <<<'...'` (above) is correct because the assignment prefixes the command that's actually run. A form like `KEYWARD_DISABLE_PASTE=1 echo '...' | python3 ...` does **not** work — the var would apply to `echo`, not to the piped `python3`, and the real paste would fire. Prefer the here-string form shown above, or `export KEYWARD_DISABLE_PASTE=1` first.

**3. `/raw` bypass** — confirm raw mode short-circuits detection:

```bash
echo '{"user_prompt": "/raw show me a ghp_ token format"}' \
  | python3 ~/.claude/plugins/keyward/scripts/detect.py
# → {"secrets": [], "raw_mode": true}
```

**4. The paste backend in isolation** — exercise only `automate_paste.py` against a tempfile of harmless text. This will really paste into whatever's focused, so point it at a scratch editor:

```bash
printf 'keyward paste backend test\n' > /tmp/kv-test.txt
python3 ~/.claude/plugins/keyward/scripts/automate_paste.py /tmp/kv-test.txt
# focus a scratch text field immediately; check ~/.claude/secrets/.last-error if nothing pastes
```

**5. List / remove saved slots** (names, sizes, perms, mtimes — never values):

```bash
python3 ~/.claude/plugins/keyward/scripts/manage_secrets.py list
python3 ~/.claude/plugins/keyward/scripts/manage_secrets.py remove github_pat_classic
```

These are exactly what the `/key-list` and `/key-rm` slash commands invoke.

**6. The full test suite** (35 stdlib unittest cases; gitleaks cases self-skip if the binary is absent):

```bash
python3 -m unittest discover -s ~/keyward/tests -p 'test_*.py' -v
```

---

Still stuck? Open an issue at [github.com/AlbeMiglio/keyward/issues](https://github.com/AlbeMiglio/keyward/issues) with: your OS + (on Linux) `echo $XDG_SESSION_TYPE`, the output of the [standalone detect test](#testing-the-engine-standalone-from-the-cli), the relevant lines from `~/.claude/secrets/.last-error`, and whether the secret file _was_ created in `~/.claude/secrets/`. That distinguishes a detection problem from a paste problem immediately.

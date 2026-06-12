# FAQ

Honest answers about what Keyward does, what it doesn't, and the edge cases. If something here contradicts your experience, it's a bug — open an issue. For the full threat model see [[Security-Model]]; for the moving parts see [[Architecture]].

## Does the key still get sent to Anthropic?

No — that's the entire point. The `UserPromptSubmit` hook fires *before* the prompt is sent to the API. When Keyward detects a secret it returns a `block` decision with `suppressOriginalPrompt: true`, so the original prompt (the one containing the raw value) is discarded, and a sanitized version is pasted and submitted in its place. The model and the API only ever see the `<<secret:NAME stored at ~/.claude/secrets/NAME.txt>>` reference — never the value.

The one caveat is local, not network: depending on Claude Code's transcript write ordering, the raw value *may* still land in the local session `*.jsonl` file. See [What if the value ends up in the transcript anyway?](#what-if-the-value-ends-up-in-the-transcript-anyway) below.

## What if I forget and the hook misses my key?

Three layers reduce this, but none is a guarantee:

1. **Regex** (`scripts/detect.py`) catches ~20 well-known formats (Anthropic, OpenAI, GitHub, AWS, Stripe, Slack, etc.) with no marker needed — see [[Detection-Patterns]].
2. **Explicit markers** — force-tag anything, including custom/internal tokens, with `/key NAME=VALUE`, `KEY:NAME=VALUE`, or `KEY=VALUE`.
3. **Optional gitleaks pass** — set `KEYWARD_USE_GITLEAKS=1` (see [[Configuration]]) for a second pass with gitleaks' much larger rule library, including generic high-entropy keys.

If a value genuinely slips through — a custom format with gitleaks off — treat it like any other leak and **rotate it**. Keyward is defense-in-depth, not an absolute guarantee. Detection is also fail-open by design: if the detector itself errors, the hook lets your prompt through unchanged rather than silently eating your message, which means an edge-case crash can pass a raw value to the model. Better a rare leak you can rotate than a swallowed prompt.

## Will it trigger when I'm just *talking* about keys?

Usually not. The placeholder filter ignores any matched value containing `EXAMPLE`, `PLACEHOLDER`, `XXX`, `YYY`, `FAKE`, `DUMMY`, `REDACTED`, `...`, or `***` (case-insensitive). So `sk-ant-EXAMPLE...` or `ghp_XXXXXXXX` won't fire.

For anything else — say you're pasting a real-looking-but-dead token from a log — prefix the message with `/raw ` to bypass detection for that one prompt. False positives are possible for any sufficiently random string that matches a loose pattern (e.g. `sk-[A-Za-z0-9]{32,}`); `/raw` is the escape hatch. See [[Detection-Patterns]] for the exact patterns and the filter.

## Does Claude ever see the real value when it *uses* the key?

No, if the bundled `using-keyward` skill is doing its job. The skill teaches Claude to expand the secret inline inside a single shell command:

```bash
export OPENAI_API_KEY=$(cat ~/.claude/secrets/openai.txt) && curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```

The value flows **disk → process env → tool**, never through stdout and therefore never into the model's context. The skill explicitly **forbids** a bare `cat ~/.claude/secrets/x.txt` (or `head`, `echo $KEY`, or `print(f.read())` in Python), because anything printed to stdout is captured into the conversation and the transcript — which would defeat the vault. If you ever see Claude about to `cat` a secret file on its own, stop it; that's the one anti-pattern the whole design exists to prevent.

## Is my key encrypted at rest?

**No.** It's stored as a plaintext file at `~/.claude/secrets/<name>.txt` with `chmod 600` (readable only by your user; the directory is `chmod 700`). This is the same trust model as `~/.aws/credentials` or a `.env` file — local file permissions, not cryptography.

If you need encryption at rest, use a real secret manager (1Password CLI, macOS Keychain via `security`, HashiCorp Vault) and reference it by path. Keyward deliberately doesn't reinvent one — it solves the "don't let the ad-hoc paste reach the model" problem, not the "store this secret securely forever" problem. See [[Security-Model]] for the full list of what is and isn't in scope.

## What if the value ends up in the transcript anyway?

It can. Claude Code's transcript write order versus hook execution order is not formally documented. If the transcript is written *before* the hook runs, your raw value is in `~/.claude/projects/.../session_*.jsonl` even though the API call was blocked. **Treat the vault as defense-in-depth, not an absolute guarantee.**

Practical rule: if a key value appears visibly in a prior assistant message in the transcript, or you can grep it out of the `.jsonl`, **rotate it**. Keyward removes the API exposure and the clipboard residue reliably; the local transcript is best-effort.

## Why does the prompt flash red / get cancelled?

That's the `block` decision doing its job. The original prompt (with the raw value) is rejected — you see a brief cancelled/dimmed message — and then the sanitized version is pasted and submitted in its place ~350 ms later. The flash is the visible side effect of the value being suppressed before it could be sent. It's expected; nothing went wrong.

## It saved the key but didn't auto-paste. Why?

The **save always succeeds** (it's a plain file write). The **paste** needs OS-level automation, which has more ways to fail:

- **macOS** — your terminal app needs Accessibility permission (`System Settings → Privacy & Security → Accessibility`). Without it, `osascript` keystrokes fail silently.
- **Linux Wayland** — your compositor must implement `virtual-keyboard-v1`. Sway/Hyprland do; GNOME doesn't by default; KDE depends on version.
- **Linux X11** — `xdotool` and `xclip`/`xsel` must be installed.
- **Windows** — some enterprise group policies disable `SendKeys`.

When the paste fails, the sanitized text is still on your clipboard — just press `Cmd/Ctrl+V` then Enter. Check `~/.claude/secrets/.last-error` for the specific reason (it logs error messages only, never secret values). To always paste manually and skip the automation entirely, set `KEYWARD_DISABLE_PASTE=1` (see [[Configuration]]). More diagnostics in [[Troubleshooting]].

## There's a brief window where the paste could go wrong — is that safe?

The auto-paste runs detached, ~350 ms after the block, to let Claude Code render the cancelled message first. Two consequences:

- **Focus race (~350 ms):** if you alt-tab to another window in that window, `automate_paste.py` detects the frontmost-app change and aborts — the sanitized (secret-free) text just stays in your clipboard for you to paste. The aborted paste only ever involves the *sanitized* text, so a misfire can't leak the value.
- **Clipboard overwrite:** your previous clipboard contents are backed up before the paste and restored ~300 ms after. If you `Cmd+C` something else inside that window, your copy wins and the original backup is lost.

## Does this work in SSH / headless / Docker?

**Detection and saving:** yes. **Auto-paste:** no — it needs a display server and a focused GUI window, which SSH sessions, headless boxes, and most containers don't have.

In those environments set `KEYWARD_DISABLE_PASTE=1` (in your shell rc so Claude Code inherits it). The hook will still detect, save to `~/.claude/secrets/`, and produce the sanitized text; you paste it manually. On `automate_paste.py`'s side, a session with no `DISPLAY`/`WAYLAND_DISPLAY` is detected as `unknown` and no backend runs, so it degrades cleanly rather than hanging.

## Can I use it with other AI CLIs (Cursor, Codex, Gemini)?

**Not currently.** Keyward's entire mechanism hinges on Claude Code's `UserPromptSubmit` hook — the one extension point that fires *before* your prompt is sent, early enough to block it and substitute a sanitized version. Cursor, GitHub Copilot/Codex CLI, Gemini CLI, and similar tools don't expose an equivalent pre-submit hook today, so there's no point at which a plugin could intercept and suppress the original prompt before it reaches their model.

The only tool-agnostic alternative would be an OS-level text-expander watching the keyboard globally — far more invasive, far less reliable, and outside what Keyward sets out to be. If one of those CLIs adds a pre-submit hook, supporting it becomes straightforward; until then, Keyward is Claude Code-specific. (See also [[Contributing]] if you want to help.)

## How do I uninstall it?

```text
/plugin uninstall keyward@keyward
```

If you installed manually by symlinking into the plugins directory, remove the link:

```bash
rm ~/.claude/plugins/keyward          # remove the symlink/copy
```

Then restart Claude Code (hooks load at session start, so the interception stops only after a restart). Uninstalling the plugin does **not** delete your saved secrets — those live independently under `~/.claude/secrets/`. To remove them too:

```bash
/key-list                              # see what's there first
rm -rf ~/.claude/secrets              # delete every saved slot
```

`/key-rm NAME` removes individual slots (with a best-effort zero-overwrite before unlink).

## Where does Keyward store data on my machine?

| Path | Contents | Permissions |
|---|---|---|
| `~/.claude/secrets/<name>.txt` | One plaintext secret per file. | `chmod 600` |
| `~/.claude/secrets/` | The vault directory. | `chmod 700` |
| `~/.claude/secrets/.last-error` | Paste-automation error log — **error messages only, never values**. | — |
| `$TMPDIR/keyward/sanitized_<hex>.txt` | The sanitized prompt awaiting paste. | `chmod 600`, deleted by `automate_paste.py` after paste |

`$TMPDIR` resolves cross-platform via Python's `tempfile.gettempdir()` (honors `TMPDIR` on Unix, `TEMP`/`TMP` on Windows) — see [[Configuration]]. There are **no network calls, no telemetry, and no third-party runtime dependencies**; everything stays on your machine in those paths. List your slots any time (names, sizes, mtimes — never values) with `/key-list`.

## Is this a replacement for 1Password / Vault / Keychain?

No, and it doesn't try to be. Those are the right home for secrets you store deliberately and reference by name. Keyward fills the one gap they leave open: the key a colleague just DM'd you that you want to use *right now*, where a vault round-trip is too heavy and rotating after pasting is too annoying. Use both — Keyward catches the ad-hoc paste; the vault holds the long-lived secrets. The trade-offs are spelled out in [[Security-Model]].

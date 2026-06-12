# Architecture

This page describes how Keyward turns a `UserPromptSubmit` event into a saved secret and a re-submitted, sanitized prompt. It is accurate to the source in `hooks/intercept.py`, `scripts/detect.py`, `scripts/automate_paste.py`, `hooks/hooks.json`, and `.claude-plugin/plugin.json`.

The whole thing is pure-Python stdlib (no `pip install`), runs on macOS, Linux (X11 and Wayland), and Windows, and is built around one hard constraint: **a Claude Code hook cannot rewrite the prompt — it can only block it or add context.** Everything below follows from that.

See also: [[Detection-Patterns]] for the regex/marker layer, [[Security-Model]] for the threat model, [[Configuration]] for the environment switches, [[Troubleshooting]] when a step doesn't fire.

## The pipeline

```text
                          you press Enter in Claude Code
                                      │
                                      ▼
              ┌───────────────────────────────────────────────┐
              │  UserPromptSubmit hook  (hooks/hooks.json)      │
              │  python3 ${CLAUDE_PLUGIN_ROOT}/hooks/intercept.py │
              │  matcher "*", timeout 15s                        │
              └───────────────────────────────────────────────┘
                                      │  stdin = {"user_prompt": "...", ...}
                                      ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ intercept.py : main()                                          │
        │                                                                │
        │  1. ensure_dirs()      ~/.claude/secrets/  +  $TMPDIR/keyward/ │
        │                        (mkdir, then chmod 0700 best-effort)    │
        │  2. json.load(stdin)   → prompt = user_prompt | prompt | ""    │
        │  3. detect_secrets(prompt)  ── imported from scripts/detect.py │
        └──────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ detect.py : detect(prompt) → {"secrets": [...], "raw_mode": …} │
        │   /raw bypass · explicit markers · ~20 regex · opt-in gitleaks │
        │   each secret: {name, value, span:[start,end], source}         │
        └──────────────────────────────────────────────────────────────┘
                     │                       │                    │
        raw_mode=True│          secrets == []│        secrets = [s1, s2, …]
                     ▼                       ▼                    ▼
        ┌────────────────────┐   ┌────────────────┐   ┌────────────────────────────┐
        │ strip "/raw "      │   │ emit {}        │   │ for each secret:            │
        │ re-submit cleaned  │   │ → original     │   │   save_secret(name, value)  │
        │ prompt (block +    │   │   prompt passes │   │   → ~/.claude/secrets/      │
        │ suppressOriginal)  │   │   through       │   │      <name>.txt             │
        └────────────────────┘   └────────────────┘   │   (atomic write, chmod 600) │
                     │                                 └────────────────────────────┘
                     │                                              │
                     │                                              ▼
                     │                        ┌──────────────────────────────────────┐
                     │                        │ sanitize_prompt(prompt, secrets)       │
                     │                        │   replace each span (right-to-left)    │
                     │                        │   with <<secret:NAME stored at         │
                     │                        │        ~/.claude/secrets/NAME.txt>>    │
                     │                        └──────────────────────────────────────┘
                     │                                              │
                     ├──────────────────────────────────────────────┤
                     ▼                                              ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ write_tempfile(sanitized)                                      │
        │   → $TMPDIR/keyward/sanitized_<16 hex>.txt   (chmod 600)        │
        └──────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ spawn_detached([python3, automate_paste.py, <tmpfile>, <app>]) │
        │   detached / new session · stdio = DEVNULL · close_fds         │
        │   (skipped entirely if KEYWARD_DISABLE_PASTE=1)                │
        └──────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ emit hook JSON                                                  │
        │   {"decision":"block",                                         │
        │    "reason":"[keyward] Intercepted N secret(s): …",            │
        │    "suppressOriginalPrompt": true}                            │
        └──────────────────────────────────────────────────────────────┘
                                      │
              intercept.py exits 0; the detached child lives on
                                      │
                                      ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ automate_paste.py  (separate process, ~350 ms later)           │
        │   detect_platform() → macos | linux-x11 | linux-wayland | win  │
        │   original = backend.get_clipboard()      (back up clipboard)  │
        │   backend.set_clipboard(sanitized)                            │
        │   sleep(PASTE_DELAY_S = 0.35)   ← let "blocked" message render │
        │   optional frontmost-app check (abort if focus changed)       │
        │   backend.paste_and_enter()     (Cmd/Ctrl+V, then Enter)       │
        │   sleep(RESTORE_DELAY_S = 0.30)                               │
        │   backend.set_clipboard(original)         (restore clipboard) │
        │   tmpfile.unlink()                                            │
        └──────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                 Claude Code receives the sanitized prompt as a
                 brand-new submission. The model only ever sees:
                 <<secret:NAME stored at ~/.claude/secrets/NAME.txt>>
```

The raw value never reaches the API call, the model context, or (best-effort) the transcript — the original submission was blocked, and the value only ever lived in the prompt span, on disk at `chmod 600`, and briefly on the clipboard before being overwritten.

## Component / file map

| File | Owns | Key entry points |
|---|---|---|
| `hooks/hooks.json` | The `UserPromptSubmit` registration: `matcher: "*"`, command `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/intercept.py`, `timeout: 15`. | — |
| `hooks/intercept.py` | Orchestration. Reads stdin, calls detection, saves secrets, builds the sanitized prompt, writes the tempfile, spawns the paste process, emits the block JSON. Owns all fail-open behavior. | `main()`, `ensure_dirs()`, `save_secret()`, `sanitize_prompt()`, `strip_raw_prefix()`, `write_tempfile()`, `get_frontmost_app()`, `spawn_detached()`, `emit()` |
| `scripts/detect.py` | Pure detection logic. Regex pattern library, explicit-marker parsing, placeholder filter, span/overlap bookkeeping, the opt-in gitleaks pass, deterministic ordering. No filesystem writes, no clipboard, no paste — just `prompt → {"secrets":[…], "raw_mode":bool}`. Importable *and* runnable as a stdin/stdout CLI. | `detect()`, `gitleaks_enabled()`, `gitleaks_scan()`, `looks_like_placeholder()`, `sanitize_slot_name()`, `main()` |
| `scripts/automate_paste.py` | Cross-platform clipboard + keystroke automation, run detached. Per-platform backends, clipboard backup/restore, the timing constants, the focus check, and error logging (never logs secret values). | `main()`, `detect_platform()`, `MacOSBackend`, `LinuxX11Backend`, `LinuxWaylandBackend`, `WindowsBackend`, `log_err()` |
| `.claude-plugin/plugin.json` | Plugin manifest: name `keyward`, version, description, author, homepage/repository, keywords, MIT license. | — |
| `~/.claude/secrets/<name>.txt` | (Runtime, not in repo.) Where each secret value lands, `chmod 600`. Tool-agnostic location — see the design notes below. `.last-error` here logs paste failures, never values. | — |
| `$TMPDIR/keyward/sanitized_<hex>.txt` | (Runtime, not in repo.) The sanitized prompt handed to the paste process, `chmod 600`, deleted by `automate_paste.py` after paste. | — |

`PLUGIN_ROOT` is resolved from `CLAUDE_PLUGIN_ROOT` (set by Claude Code) or, as a fallback, by walking up two parents from `intercept.py`. `scripts/` is pushed onto `sys.path` so `from detect import detect` works in-process — no second Python interpreter is spawned just to detect.

## Key design decisions (with rationale)

### Block-and-resubmit instead of editing the prompt in place

This is the load-bearing decision. **Claude Code's `UserPromptSubmit` hook contract does not include "return a modified prompt."** A hook can:

- emit `{}` (or nothing) → the prompt passes through unchanged;
- emit `{"decision":"block", ...}` → the prompt is rejected;
- emit additional context that gets *appended*, not substituted.

There is no "here is the rewritten prompt, send this instead" return value. So to make the model see sanitized text and *not* the raw key, Keyward:

1. **blocks** the original (`decision: block` + `suppressOriginalPrompt: true`) so the raw value is dropped, then
2. **re-injects** the sanitized text as a fresh submission via OS-level paste automation (`automate_paste.py`).

The paste step is the only way to get edited text back into the input box from outside the model. It is deliberately a *separate, detached* process: the hook must return its JSON quickly (within the 15 s timeout) and exit, while the paste has to happen *after* Claude Code has finished rendering the "blocked" message — hence `spawn_detached()` plus the `PASTE_DELAY_S = 0.35` wait inside the child. If the paste ran inline in the hook, it would race the UI and the hook would block on it.

### Fail-open everywhere

Every failure path in `intercept.py` ends in `emit({})` and `return 0` — which means the original prompt passes through **unchanged**. Concretely, the hook fails open when:

- `detect.py` can't be imported (missing/broken) — caught at module load, prints `{}`, exits;
- `ensure_dirs()` raises `OSError`;
- stdin isn't valid JSON;
- the prompt is missing / not a string / empty;
- `detect_secrets()` throws (broad `except Exception`);
- any single `save_secret()` raises `OSError` (even mid-batch — it bails rather than blocking a half-handled prompt).

The rationale is in the module docstring: *"Better to leak a key in an edge case than to silently swallow the user's message."* A tool that occasionally eats your prompt is a tool you uninstall; a tool that occasionally misses a key is a tool you treat with appropriate caution (and back up with [[Security-Model]] hygiene). Failing open keeps Keyward unobtrusive enough to leave installed. The cost — a missed key in an edge case — is exactly the case the documentation is honest about.

### Atomic write + `chmod 600`

`save_secret()` never writes the final path directly. It writes to `<name>.txt.tmp`, `chmod 0600` on the temp file, then `tmp.replace(target)` — `os.replace`/`Path.replace` is atomic on POSIX and Windows. Two reasons:

- **No partial-file window.** A reader (you, `cat`, the `using-keyward` skill) never sees a half-written secret; the file either has the old contents or the complete new ones.
- **Permissions are set before the file is visible at its final name.** The value is never world-readable, not even for the microsecond between create and chmod.

The `chmod` is wrapped in `try/except OSError` because it's a no-op that can legitimately fail on Windows; the atomic rename still happens. The same pattern (`token_hex(8)` random name + `chmod 600`) guards `$TMPDIR/keyward/sanitized_*.txt`.

### gitleaks is opt-in (`KEYWARD_USE_GITLEAKS=1`)

The built-in regex library is fast and runs in-process. gitleaks ships a much larger, battle-tested rule set that catches formats the regex list doesn't — but invoking it means spawning a subprocess (~50–150 ms by the source's own estimate) and shelling out to a temp file on **every** prompt. That tax on every keystroke-to-Enter isn't worth it for most users, so it's behind a flag and additionally gated on the binary actually being present (`shutil.which("gitleaks")`). `gitleaks_enabled()` returns true only when both conditions hold. When on, its findings are *merged* with the regex/marker results rather than replacing them — details in [[Detection-Patterns]]. See [[Configuration]] to turn it on.

### `~/.claude/secrets/` is kept tool-agnostic

Secrets are written as plain `<name>.txt` files under `~/.claude/secrets/`, not into a Keyward-proprietary store, DB, or encrypted blob. That directory is a natural home (Claude Code's config root) but the *format* is deliberately boring: one secret per file, value verbatim, nothing else. So any tool — a shell one-liner, a Makefile, a different AI CLI, a plain `cat` — can consume a secret with `$(cat ~/.claude/secrets/NAME.txt)`. Keyward stores; it doesn't own. The trade-off (plaintext-at-rest, protected by file permissions rather than encryption) is documented head-on in [[Security-Model]].

### Cross-platform temp dir via `tempfile.gettempdir()`

The sanitized-prompt tempfile lives under `Path(tempfile.gettempdir()) / "keyward"`, never a hardcoded `/tmp`. `tempfile.gettempdir()` honors `TMPDIR` on Unix and `TEMP`/`TMP` on Windows (where `/tmp` doesn't exist at all). This is what lets the same `intercept.py` run unmodified on all four platforms, and it's what the test suite leans on — tests point `TMPDIR`/`TEMP`/`TMP` at a sandbox to keep runs hermetic. Similarly, `spawn_detached()` branches on `sys.platform`: Windows gets `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` creation flags, POSIX gets `start_new_session=True`.

### `/raw` escape hatch

When a prompt starts with `/raw ` (checked *first*, before any detection), `detect()` returns `{"secrets": [], "raw_mode": True}` and `intercept.py` strips exactly one leading `/raw ` prefix, then re-submits the remainder through the same block-and-paste path. This lets you legitimately discuss key formats or paste an example without interception — see [[Detection-Patterns]]. If stripping the prefix yields the same string (nothing to strip), it fails open with `{}`.

## The hook JSON contract

`intercept.py` writes exactly one JSON object to stdout and exits 0. There are three shapes.

**Pass-through (no action / any fail-open path):**

```json
{}
```

The original prompt is sent unchanged. This is emitted on every error condition and whenever no secrets are found.

**Secrets intercepted:**

```json
{
  "decision": "block",
  "reason": "[keyward] Intercepted 2 secret(s): anthropic [regex], stripe [explicit_named]. Saved to ~/.claude/secrets/ (chmod 600). Sanitized prompt queued for auto-paste.",
  "suppressOriginalPrompt": true
}
```

The `reason` lists each saved secret as `name [source]`, where `source` is one of `regex`, `explicit_slash`, `explicit_named`, `explicit_default`, or `gitleaks`. `suppressOriginalPrompt: true` is what keeps the raw value out of the transcript.

**`/raw` mode:**

```json
{
  "decision": "block",
  "reason": "[keyward] /raw mode — prompt re-submitted without prefix.",
  "suppressOriginalPrompt": true
}
```

In both `block` cases the actual sanitized/cleaned text reaches the input box out-of-band, via the detached `automate_paste.py`, not via this JSON. The JSON only blocks; the paste process re-submits.

# Configuration

Keyward has **no config file**. Everything is controlled by environment variables. The key thing to understand: the hook runs as a child of Claude Code, so it inherits Claude Code's environment — which means a variable only takes effect if Claude Code itself sees it. The reliable way to set one is to **export it in your shell rc and restart Claude Code** (details [below](#making-claude-code-inherit-an-env-var)).

For what each setting protects (or doesn't), see [[Security-Model]]. For per-platform install, see [[Installation]].

## Environment variables

| Variable | Effect | When to set it |
|---|---|---|
| `KEYWARD_DISABLE_PASTE=1` | Skips the detached auto-paste spawn entirely. The hook still detects, saves to `~/.claude/secrets/`, and writes the sanitized prompt — you just paste it yourself (it's on the clipboard if the backend ran, or readable from the tempfile). Checked in `intercept.py` `spawn_detached()`. | SSH / headless / Docker (no display server); WSL with the Windows-host crossing; any Wayland compositor that blocks synthetic input (GNOME by default); or if you simply prefer to paste manually. |
| `KEYWARD_USE_GITLEAKS=1` | Enables the **opt-in** second detection pass via the `gitleaks` binary, catching formats the built-in regex misses (generic high-entropy keys, private-key blocks, many more providers). Requires `gitleaks` on `PATH` — if the binary is absent the flag is a no-op (`gitleaks_enabled()` checks both the var *and* `shutil.which("gitleaks")`). Findings are saved with `source: gitleaks`. **Off by default.** | When you want broader coverage than the ~20 built-in providers and accept a per-prompt latency cost. See the [walkthrough below](#optional-deeper-detection-with-gitleaks). |
| `TMPDIR` / `TEMP` / `TMP` | Overrides where the sanitized tempfile is written. Keyward uses Python's `tempfile.gettempdir()` and appends `/keyward`, so it honors `TMPDIR` on Unix and `TEMP`/`TMP` on Windows automatically — it never hardcodes `/tmp` (which doesn't exist on Windows). The tempfile is `chmod 600` and deleted after the paste. | Rarely needed. Set it if your OS temp dir is on a noexec/odd mount, if you want sanitized tempfiles on a specific volume, or to sandbox the path in tests. |
| `CLAUDE_PLUGIN_ROOT` | Tells the hook where the plugin lives, so it can find `scripts/detect.py`, `scripts/automate_paste.py`, etc. **Set automatically by Claude Code.** If unset (e.g. manual/standalone invocation), `intercept.py` falls back to walking up from the script's own location (`Path(__file__).resolve().parent.parent`). | You normally never set this. Set it only when invoking `intercept.py` directly outside Claude Code — e.g. in tests, where the suite sets it to the repo root. |

> Note: there is no env var to *change the vault path*. Secrets always go to `~/.claude/secrets/` (resolved from `Path.home()`), and only the **temp** location is overridable.

## Making Claude Code inherit an env var

Because the hook is a subprocess of Claude Code, set the variable in the shell rc that launches Claude Code, then restart it (hooks and environment are read at session start — a running session won't pick up a change).

**macOS / Linux** — add to `~/.zshrc`, `~/.bashrc`, or `~/.profile` (whichever your login shell reads):

```bash
export KEYWARD_USE_GITLEAKS=1
# and/or
export KEYWARD_DISABLE_PASTE=1
```

Then open a fresh terminal (or `source` the file) and start Claude Code:

```bash
claude
```

**Windows (PowerShell)** — set a persistent user-level variable:

```powershell
[Environment]::SetEnvironmentVariable("KEYWARD_DISABLE_PASTE", "1", "User")
```

Then open a **new** PowerShell window and start Claude Code. (A `$env:VAR = "1"` set in an existing window only affects that window's child processes.)

**Verify it took effect.** After restarting, exercise the orchestrator directly with the paste disabled — this confirms detection + save work without firing the real automation:

```bash
KEYWARD_DISABLE_PASTE=1 \
  python3 ~/.claude/plugins/keyward/hooks/intercept.py <<<'{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
```

You should get a `{"decision":"block", ...}` JSON back and a new `~/.claude/secrets/github_pat_classic.txt`. (Delete it afterward with `/key-rm github_pat_classic` or `rm`.)

## Optional: deeper detection with gitleaks

The built-in regex library (see [[Detection-Patterns]]) covers ~20 well-known providers. Enabling the gitleaks pass adds a second, broader sweep — generic high-entropy strings, private-key blocks, and dozens of additional providers from gitleaks' battle-tested rule set — for anything the regex layer missed.

**1. Install gitleaks.**

```bash
brew install gitleaks            # macOS
# or grab a release binary: https://github.com/gitleaks/gitleaks#installing
```

Confirm it's on `PATH`:

```bash
gitleaks version
```

**2. Export the env var** (so Claude Code inherits it — see the section above):

```bash
export KEYWARD_USE_GITLEAKS=1
```

**3. Restart Claude Code.** New sessions now run the gitleaks pass on every prompt.

### How it runs (and why it's a separate pass)

When enabled, after the regex and explicit-marker passes, `detect.py` writes the prompt to a private temp dir and shells out to `gitleaks detect --no-git --report-format json ...`. It locates each reported secret's span by `str.find()` (rather than trusting gitleaks' line/column reporting, which has varied across versions), de-duplicates against spans already claimed by the regex layer, and tags new findings with `source: gitleaks`. The placeholder filter still applies — values containing `EXAMPLE`, `PLACEHOLDER`, `XXX`, `FAKE`, `DUMMY`, etc. are ignored even when gitleaks flags them.

### The trade-offs (this is why it's off by default)

- **Per-prompt latency.** gitleaks runs as a subprocess on **every** prompt, adding roughly **50–150 ms** each time. The regex-only default stays fast and adds nothing measurable. If you don't need the extra coverage, leave it off.
- **`generic-api-key` noise.** gitleaks' generic high-entropy rule is powerful but can fire on innocuous random-looking strings (hashes, UUIDs, base64 blobs). When it false-positives on a prompt you didn't mean to sanitize, prefix that one message with **`/raw `** to bypass detection entirely for that prompt:

  ```text
  /raw here is a random hash a1b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5 just discussing it
  ```

  `/raw` is checked first and short-circuits all detection (regex, markers, and gitleaks), then re-submits the prompt with the `/raw ` prefix stripped. Don't use `/raw` for a message that contains a *real, live* key — it turns Keyward off for that prompt.

---

See also: [[Detection-Patterns]] (what the regex/markers catch), [[Security-Model]] (no-network guarantee, what gitleaks does and doesn't change), [[Troubleshooting]] (detection-works-but-paste-doesn't), [[Installation]], [[Home]].

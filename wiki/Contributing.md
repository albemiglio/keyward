# Contributing

Issues and PRs are welcome. Keyward is deliberately small and dependency-free — pure Python 3.9+ stdlib, no `pip install` — so the contributor loop is fast and the same on every platform. This page covers dev setup, running the tests, exercising the parts that need extra binaries, the project layout, where help is wanted, and what CI checks.

For the runtime design see [[Architecture]]; for detection internals see [[Detection-Patterns]]; for the threat model you should respect when changing anything security-relevant see [[Security-Model]].

## Dev setup

```bash
git clone https://github.com/albemiglio/keyward.git
cd keyward
```

That's it — there's nothing to install for the core (stdlib only). Two optional binaries unlock optional test paths: `gitleaks` (for the gitleaks integration tests) and `vhs` (to re-render the demo GIF). Both are covered below.

## Running the test suite

The suite is 35 stdlib-only `unittest` cases covering detection, the hook end-to-end (in a sandboxed `HOME`/`TMPDIR`), and slot management. Run it from the repo root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The hook tests (`TestIntercept`) shell out to `intercept.py` in a throwaway temp dir with `KEYWARD_DISABLE_PASTE=1`, so **no real paste automation fires** during tests and your actual `~/.claude/secrets/` is never touched. The gitleaks integration tests **self-skip** when the `gitleaks` binary isn't on `PATH`, so a plain checkout runs green everywhere without extra setup.

### Exercising the gitleaks tests

To actually run the gitleaks-dependent cases (`test_gitleaks_catches_what_regex_misses`) instead of skipping them, install the binary first:

```bash
brew install gitleaks          # macOS
# or a release binary: https://github.com/gitleaks/gitleaks#installing
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

With `gitleaks` present, the previously-skipped cases activate automatically (`HAS_GITLEAKS = shutil.which("gitleaks") is not None`); the test sets `KEYWARD_USE_GITLEAKS=1` itself for the duration of that case.

### Testing detection standalone

`scripts/detect.py` is pure, side-effect-free, and reads a JSON prompt on stdin — ideal for poking at new patterns:

```bash
echo '{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' \
  | python3 scripts/detect.py
```

Expected output (a JSON object with the detected slot, its value, span, and `source`):

```json
{"secrets": [{"name": "github_pat_classic", "value": "ghp_...", "span": [5, 45], "source": "regex"}], "raw_mode": false}
```

### Testing the orchestrator standalone

To exercise the full hook (detect → save → sanitize → emit JSON) **without** triggering the real paste, run `intercept.py` directly with the paste disabled:

```bash
KEYWARD_DISABLE_PASTE=1 \
  python3 hooks/intercept.py <<<'{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
```

This writes a real secret to `~/.claude/secrets/` (unlike the sandboxed test suite, which redirects `HOME`), so clean up afterward with `/key-rm github_pat_classic` or `rm ~/.claude/secrets/github_pat_classic.txt`.

### Re-rendering the demo GIF

The demo GIF is produced from a [VHS](https://github.com/charmbracelet/vhs) tape that drives `demo/demo.py` (the real detection engine, with a fake key, fully sandboxed — it never touches your vault). To re-render after changing the demo:

```bash
vhs demo/demo.tape          # run from the repo root
```

This regenerates `demo/keyward-demo.gif` (output path and terminal settings are defined inside `demo/demo.tape`).

## Project layout

| Path | What it owns |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest (name, version, author). |
| `hooks/hooks.json` | Hook registration: `UserPromptSubmit` → `intercept.py`. |
| `hooks/intercept.py` | **Orchestrator.** Reads the prompt, calls `detect`, saves each secret (`chmod 600`, atomic write), builds the sanitized prompt, spawns the detached paste, emits the block JSON. Fails open on any error. |
| `scripts/detect.py` | **Pure detection.** Regex providers + explicit markers (`/key`, `KEY:NAME=`, `KEY=`) + placeholder filter + opt-in gitleaks pass. No side effects — start here for new patterns. |
| `scripts/automate_paste.py` | **Per-platform paste backends** (osascript / xdotool / wtype / PowerShell SendKeys): clipboard backup, focus re-check, paste+Enter, clipboard restore, tempfile cleanup. Add compositor support here. |
| `scripts/manage_secrets.py` | `/key-list` and `/key-rm` (cross-platform, no bash). Lists names/sizes/mtimes (never values); remove does zero-overwrite-then-unlink. |
| `commands/key.md`, `key-list.md`, `key-rm.md`, `raw.md` | The four slash commands. |
| `skills/using-keyward/SKILL.md` | Teaches Claude to consume a saved secret via `export VAR=$(cat ...)` and to never `cat` it bare. |
| `tests/test_keyward.py` | The whole suite. **Add a case alongside any change.** |
| `demo/demo.py`, `demo/demo.tape`, `demo/keyward-demo.gif` | Narration driver + VHS script + rendered GIF. |
| `.github/workflows/ci.yml` | CI (see below). |
| `CHANGELOG.md` | Keep-a-Changelog history. |

## Where help is wanted

These are the open areas the maintainers have flagged. PRs in any of them are especially welcome:

- **More providers.** Additional regex patterns in `scripts/detect.py` for less-common services. Patterns are anchored on prefix + length + charset; add a unit test in the same PR.
- **Wayland compositor compatibility.** Real-world testing and fixes for `wtype` across **Sway / Hyprland / KDE Plasma / GNOME**. Synthetic input depends on the compositor implementing `virtual-keyboard-v1`; coverage is currently uneven.
- **Windows-native edge cases.** `SendKeys` behavior under different focus models and enterprise group policies (some disable `SendKeys` outright).
- **`detect-secrets` (Yelp) backend.** An alternative to gitleaks for the optional pass — same opt-in/placeholder-filter contract, different engine.
- **`/key-rotate` command.** A slash command that calls provider-specific rotation APIs to rotate a saved key in place.

When adding security-relevant behavior, keep the existing invariants: **never print a secret value** (not in logs, not in `/key-list`, not in the demo), keep the hook **fail-open**, and preserve the **placeholder filter** so discussing key formats doesn't trigger detection. See [[Security-Model]] for the guarantees you must not break.

## Continuous integration

CI (`.github/workflows/ci.yml`) runs on push and PR to `main`, plus manual `workflow_dispatch`. Two jobs:

**`test` — the cross-platform matrix.** Ubuntu, macOS, and Windows × Python **3.9** and **3.12** (`fail-fast: false`, so one failing cell doesn't cancel the rest). Each cell:

1. Byte-compiles all sources (`python -m compileall hooks scripts tests`).
2. Validates the JSON manifests (`.claude-plugin/plugin.json`, `hooks/hooks.json`) parse.
3. Runs the full suite (`python -m unittest discover -s tests -p "test_*.py" -v`) — the gitleaks cases self-skip here since the binary isn't installed in this job.

**`test-with-gitleaks` — the gitleaks path (Ubuntu).** Installs a pinned gitleaks release, confirms `gitleaks version`, then runs the same suite with the gitleaks integration **active** so the opt-in pass is actually exercised in CI.

A green CI therefore means: the plugin byte-compiles and the suite passes on all three OSes across both Python versions, the manifests are valid JSON, **and** the gitleaks integration works on at least one platform.

---

See also: [[Architecture]] (the pipeline you're modifying), [[Detection-Patterns]] (adding regex providers), [[Configuration]] (the env vars under test), [[Security-Model]] (invariants to preserve), [[Home]].

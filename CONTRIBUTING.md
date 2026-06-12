[Issues]: https://github.com/AlbeMiglio/keyward/issues
[Issue]: https://github.com/AlbeMiglio/keyward/issues
[Discussions]: https://github.com/AlbeMiglio/keyward/discussions
[wiki]: https://github.com/AlbeMiglio/keyward/wiki

# Contributing to Keyward

Thanks for your interest in contributing to Keyward — the Claude Code plugin that
keeps API keys out of your prompts.

All kinds of contributions are welcome: bug reports, new provider patterns,
platform fixes, docs, and code. Please read the relevant section below before you
start — it makes things easier for everyone.

> Short on time but like the project? You can still help:
> - ⭐ Star the repo.
> - Share it on social media or with your team.
> - Add a detection pattern or a platform note — they're small, high-value PRs.

## Table of contents

- [Questions](#questions)
- [Reporting bugs](#reporting-bugs)
- [Suggesting features](#suggesting-features)
- [Contributing code](#contributing-code)
  - [Project layout](#project-layout)
  - [Running the tests](#running-the-tests)
  - [Adding a detection pattern](#adding-a-detection-pattern)
  - [Adding platform support](#adding-platform-support)
- [Style guide](#style-guide)

## Questions

First, search existing [Issues] and [Discussions] — your question may already be
answered. The [wiki] also covers installation, architecture, security model, and
troubleshooting in depth.

If you still need help, open a [Discussion](https://github.com/AlbeMiglio/keyward/discussions/new/choose)
and give as much context as you can (OS, terminal, what you ran, what happened).

## Reporting bugs

A good bug report saves a round-trip. Before opening one:

- Make sure you're on the latest version (`claude plugin update keyward`).
- Check `~/.claude/secrets/.last-error` — paste automation failures are logged there.
- Search [Issues] to avoid duplicates.

Then open a bug report with: your OS + terminal, whether Accessibility is granted
(macOS), the prompt/key format that triggered it, what happened vs. what you
expected, and the `.last-error` line if relevant. **Never paste a real secret** —
use a fake key like `ghp_aaaa…`.

## Suggesting features

Open a feature request describing the problem first, then the proposed solution.
Good candidates: new provider regexes, Wayland compositor support, a `/key-rotate`
command, `detect-secrets` as an alternative to gitleaks.

## Contributing code

For anything non-trivial, open an issue first so we can align on the approach.

### Project layout

| Path | What it does |
|---|---|
| `scripts/detect.py` | Pure detection: regex + explicit markers + optional gitleaks. No side effects — start here for new patterns. |
| `hooks/intercept.py` | Orchestrator: detect → save → sanitize → spawn paste → emit hook JSON. |
| `scripts/automate_paste.py` | Per-platform paste backends (osascript / xdotool / wtype / SendKeys). |
| `scripts/manage_secrets.py` | `/key-list` and `/key-rm`. |
| `skills/using-keyward/` | Teaches Claude to consume secrets safely. |
| `commands/` | Slash commands (`/key`, `/key-list`, `/key-rm`, `/raw`). |
| `tests/test_keyward.py` | The whole test suite. |

Keyward is **stdlib-only** — no third-party runtime dependencies, no network calls,
no telemetry. Please keep it that way.

### Running the tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

35 cases, no `pip install` needed. The gitleaks integration tests self-skip unless
`gitleaks` is installed (`brew install gitleaks` to exercise them). **Add a test
alongside any change.**

Test detection on a single input:

```bash
echo '{"user_prompt": "test ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' | python3 scripts/detect.py
```

### Adding a detection pattern

Add a `(name, compiled_regex)` entry to `REGEX_PATTERNS` in `scripts/detect.py`,
then add a test case. Prefer prefix + length + charset patterns (low false-positive
rate). Avoid anything that could match ordinary high-entropy strings without a
distinctive prefix.

### Adding platform support

Per-platform paste backends live in `scripts/automate_paste.py`. Each must: save
the clipboard, set the sanitized text, verify focus hasn't changed, send paste +
Enter, then restore the clipboard. Log failures to `~/.claude/secrets/.last-error`.

## Style guide

- Match the surrounding code — naming, comment density, idioms.
- Comments explain *why*, not *what*. Keep them minimal and human.
- No new runtime dependencies.
- Conventional, human commit messages.

By contributing, you agree your contributions are licensed under the project's
[MIT License](LICENSE).

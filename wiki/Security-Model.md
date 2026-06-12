# Security Model

This page is the honest threat model. Keyward is **defense-in-depth for the ad-hoc paste**, not a secret manager and not a guarantee. Read it before trusting Keyward with anything that matters, and skim ["When to use a real secret manager instead"](#when-to-use-a-real-secret-manager-instead) if you're deciding whether Keyward is enough.

For the install steps see [[Installation]]; for the env vars referenced below see [[Configuration]]; for the pipeline mechanics see [[Architecture]].

## What Keyward protects against

Two concrete leaks, in the common case where you paste a key into Claude Code chat:

1. **The key reaching the API and the model context.** The leak happens at prompt submission, *upstream of any tool*. Keyward's `UserPromptSubmit` hook (`hooks/intercept.py`) fires before the prompt is sent, returns `{"decision":"block","suppressOriginalPrompt":true}`, and re-submits a sanitized version where the value is replaced with `<<secret:NAME stored at ~/.claude/secrets/NAME.txt>>`. The raw value never appears in the API call or the model's context. This is the part Keyward does reliably — it's pure local logic, no automation, no race.

2. **The key leaking into stdout when it's later *used*.** Saving the key out of band is only half the job; the other half is consuming it without printing it back into the context. The bundled `using-keyward` skill teaches Claude to expand the secret inline in a single shell command — `export VAR=$(cat ~/.claude/secrets/x.txt) && cmd` — so the value flows disk → process env → tool, never through stdout. The skill explicitly **forbids** a bare `cat ~/.claude/secrets/x.txt`, which would print the value straight into Claude's context and defeat the whole point.

3. **The key persisting in the clipboard after paste.** The auto-paste backend (`scripts/automate_paste.py`) backs up your existing clipboard, writes the sanitized text, pastes it, and restores the original ~600 ms later. The raw value is never placed on the clipboard at all — only the sanitized reference is.

## What Keyward explicitly does NOT protect against

Be candid with yourself about these. Several are inherent to the design; none are bugs.

### Plaintext at rest — same trust model as `~/.aws/credentials`

Saved secrets are **plaintext files**. `~/.claude/secrets/<name>.txt`, `chmod 600`, readable only by your user. There is **no encryption at rest**. This is deliberate and it is the same trust model as `~/.aws/credentials`, a `.env` file, or `~/.netrc`: the protection is filesystem permissions and the assumption that your user account isn't already compromised. If you need encryption at rest, Keyward is the wrong tool — use a real secret manager and reference it by path.

### The transcript write-ordering caveat is defense-in-depth, not a guarantee

This is the most important caveat. Claude Code's transcript write order versus hook execution order **is not formally documented**. The API call is reliably blocked, but if the local session transcript (`~/.claude/projects/.../session_*.jsonl`) is written *before* the hook runs, your raw value can land in that `.jsonl` even though the model never saw it. Keyward cannot control this — it only controls the hook's return value.

**Treat the transcript protection as best-effort defense-in-depth, not an absolute guarantee.** If a key value ever appears visibly in a prior message in the transcript, rotate it. This is also why the README's threat-model table marks "key reaching the live transcript" as best-effort rather than guaranteed.

### Not protection against a hostile local environment

Keyward defends the *prompt-submission* path. It does nothing against an adversary who is already inside your machine or your trust boundary:

- **Malware / other plugins.** Any process — or any other Claude Code plugin — running as your user with filesystem access can read `~/.claude/secrets/`. The `chmod 600` keeps *other users* out; it does nothing against code running *as you*.
- **Keyloggers.** A keylogger sitting between your keyboard and the terminal sees the keystrokes as you type the key, before the hook ever runs.
- **Memory-resident attacks / memory dumps.** The value lives in the hook process's memory and in the target process's environment when used. Anything that can read process memory can read it.
- **Backup tools that ignore permissions.** A backup agent, cloud-sync daemon, or disk imager that doesn't honor POSIX permissions will happily copy your plaintext `~/.claude/secrets/` off the machine.
- **Physical or SSH access.** Someone at the keyboard, or with a shell as your user, reads the files directly.

### The auto-paste race window

There is a ~350 ms gap between the hook returning and the detached `automate_paste.py` performing the paste. The backend re-checks the frontmost app and **aborts if focus changed** (the sanitized text stays on the clipboard for you to paste manually), so this fails safe rather than pasting into the wrong window. But it is a moving part: if you alt-tab in that window the auto-submit won't happen. The *save and sanitize* are already done by then — only the convenience of the auto-paste is at stake, never the protection.

## File permissions

| Path | Permission | Set by |
|---|---|---|
| `~/.claude/secrets/` (vault dir) | `chmod 700` | `intercept.py` `ensure_dirs()` |
| `~/.claude/secrets/<name>.txt` (each secret) | `chmod 600` | `intercept.py` `save_secret()` (atomic write: write to `.tmp` → `chmod` → `replace`) |
| `$TMPDIR/keyward/sanitized_<hex>.txt` (sanitized prompt) | `chmod 600` | `intercept.py` `write_tempfile()`; deleted by `automate_paste.py` after paste |
| `~/.claude/secrets/.last-error` | error log | only error strings, **never** secret values |

Permission tightening is wrapped in `try/except OSError` and is a **best-effort no-op on Windows**, which has no POSIX mode bits — on Windows the files inherit the user-profile ACL instead. The test suite asserts `0o600` on files and `0o700` on the dir, and skips those two assertions on Windows (`@unittest.skipIf(IS_WINDOWS, ...)`).

## Secure-ish delete via `manage_secrets`

`/key-rm NAME` (backed by `scripts/manage_secrets.py` `cmd_remove`) does an **overwrite-then-unlink**: it opens the file `r+b`, writes `b"\x00" * size` over the contents, `flush()` + `fsync()`, then `unlink()`s it.

This is **best-effort, not guaranteed.** The docstring says so plainly. On modern storage the overwrite often does **not** physically destroy the old bytes:

- **SSDs with wear-leveling** remap writes to fresh cells; the original block can survive untouched until garbage-collected.
- **Copy-on-write filesystems** — APFS (macOS default), Btrfs, ZFS — may write the zeros to a new extent and keep the old one until it's reclaimed.
- Snapshots, Time Machine, and other backups may already hold a copy (see "backup tools" above).

So `/key-rm` reliably removes the *name* from the vault and makes casual recovery harder, but do not treat it as cryptographic erasure. If a secret was truly sensitive, **rotate it** rather than relying on the overwrite.

## When to use a real secret manager instead

Keyward fills a narrow gap: *"a colleague just DM'd me this key and I want to use it once, in chat, now, without a vault round-trip and without having to rotate it afterward."* For that, it's the right amount of tool.

Reach for a real secret manager — `1Password` CLI, macOS Keychain via `security`, HashiCorp Vault, AWS Secrets Manager, `direnv` + an encrypted store — when **any** of these is true:

- The secret is **long-lived or high-stakes** (production database credentials, signing keys, a root token).
- You need **encryption at rest**, audit logging, access policies, or rotation workflows.
- The secret is **shared across a team** or needs to be provisioned to CI/servers.
- Your **threat model includes the local machine itself** — untrusted plugins, backups leaving the host, multi-tenant access.

Keyward deliberately does not reinvent any of that. It is the safe on-ramp for getting an ad-hoc key *out of the chat box*, not the system of record.

## No network, no telemetry, no dependencies

By design, and easy to verify by reading the source:

- **No network calls.** Nothing in `intercept.py`, `detect.py`, or `manage_secrets.py` opens a socket or makes an HTTP request. The optional gitleaks pass shells out to a **local** `gitleaks` binary you installed yourself — still no network from Keyward.
- **No telemetry.** Nothing is reported anywhere. The only file Keyward writes outside the vault is the local `.last-error` log, which contains error strings only, never secret values.
- **No third-party runtime dependencies.** Pure Python 3.9+ stdlib — no `pip install`. The whole runtime is auditable in a few hundred lines across `hooks/` and `scripts/`.

## Fail-open by design

One more honesty note about the trust model: the hook **fails open**. Any unexpected error — bad stdin JSON, a missing `detect.py`, a failed save — causes `intercept.py` to emit empty JSON (`{}`) so your **original prompt passes through unchanged**. The maintainers chose "better to leak a key in a rare edge case than to silently swallow the user's message." Practically: if Keyward ever malfunctions, it gets out of the way rather than blocking you — which means a malfunction can let a paste through. If something looks off, assume the key wasn't intercepted and rotate it.

---

See also: [[Configuration]] (the env vars), [[Architecture]] (the full pipeline), [[Detection-Patterns]] (what gets caught), [[FAQ]] (encryption at rest, what-if-it-misses), [[Home]].

# Security Policy

Keyward is a security tool, so we take its own security seriously. Thank you for
helping keep it and its users safe.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately via either:

- **GitHub Security Advisories** — [Report a vulnerability](https://github.com/AlbeMiglio/keyward/security/advisories/new) (preferred), or
- **Email** — albertomigliorato@gmail.com

Please include:

- a description of the issue and its impact,
- steps to reproduce (a minimal proof of concept if possible),
- affected version and platform.

You'll get an acknowledgement as soon as possible, and a fix or mitigation plan
once the report is triaged. Please give a reasonable window for a fix before any
public disclosure.

## Scope

Keyward intercepts API keys in prompts, stores them under `~/.claude/secrets/`
(`chmod 600`), and re-submits a sanitized message. In-scope concerns include:

- a detected secret reaching the model / transcript despite interception,
- secret files written with weaker permissions than `chmod 600`,
- the sanitized tempfile or clipboard leaking the value,
- the paste automation injecting into the wrong window.

## What Keyward is — and isn't

Keyward is **defense-in-depth**, not a guarantee. Secrets are stored as plaintext
`chmod 600` files (the same trust model as `~/.aws/credentials` or a `.env` file),
not encrypted at rest. Depending on Claude Code's write ordering, the transcript
may still capture a value in edge cases. For high-value production secrets, use a
dedicated secret manager and reference it by path. See the
[Security Model](https://github.com/AlbeMiglio/keyward/wiki/Security-Model) for the
full threat model.

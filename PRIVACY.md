# Privacy

Keyward runs entirely on your machine. It collects nothing, sends nothing, and
has no servers, accounts, analytics, or telemetry.

## What Keyward does with your data

- **No network calls.** Keyward never connects to the internet. There is nothing
  to opt out of because nothing leaves your computer.
- **Secrets stay local.** Detected keys are written only to
  `~/.claude/secrets/<name>.txt` with `chmod 600` permissions. They are read back
  only when you (or Claude, via the bundled skill) reference them by path.
- **Clipboard.** During the cross-platform paste step Keyward briefly uses the
  system clipboard to insert the sanitized message, then restores its previous
  contents. The clipboard value is never stored or transmitted.
- **Optional gitleaks.** If you set `KEYWARD_USE_GITLEAKS=1`, detection shells out
  to your locally installed `gitleaks` binary. That, too, runs offline.

## What Keyward does not do

- No data collection of any kind.
- No tracking, fingerprinting, or usage reporting.
- No third-party services.

Because no personal data is processed or shared, there is nothing for this policy
to disclose beyond the above. Questions: albertomigliorato@gmail.com.

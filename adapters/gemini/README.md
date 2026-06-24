# keyward — Gemini CLI adapter

Gemini's `BeforeAgent` hook can **deny** a prompt but **cannot rewrite** it
(`additionalContext` only appends, it doesn't redact). So on Gemini, keyward is
fail-safe rather than transparent (same as the Codex adapter):

- Secret detected → value saved to `~/.claude/secrets/<NAME>.txt` (chmod 600), and
  the prompt is **denied** so the raw secret never reaches the model.
- Re-send referencing the saved path, or prefix `/raw ` to send as-is.

Detection logic is shared verbatim with the Claude hook (`scripts/detect.py`).

## Install

Add to Gemini's `settings.json` (`~/.config/gemini-cli/settings.json`) or an
extension's `hooks/hooks.json`:

```json
{ "hooks": { "BeforeAgent": [ { "hooks": [
  { "type": "command", "command": "python3 /ABSOLUTE/PATH/TO/keyward/adapters/gemini/gemini_hook.py", "timeout": 15000 }
] } ] } }
```

`hooks.json` here uses `${GEMINI_PLUGIN_ROOT}`; if your Gemini version doesn't set
that variable, use the absolute path to `gemini_hook.py`.

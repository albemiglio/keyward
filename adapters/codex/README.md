# keyward — Codex CLI adapter

Codex's `UserPromptSubmit` hook can **block** a prompt but **cannot rewrite** it
(unlike Claude Code). So on Codex, keyward is fail-safe rather than transparent:

- Secret detected → value saved to `~/.claude/secrets/<NAME>.txt` (chmod 600), and
  the prompt is **blocked** so the raw secret never reaches the model.
- You then re-send the prompt referencing the saved path, or prefix `/raw ` to send as-is.

Detection logic is shared verbatim with the Claude hook (`scripts/detect.py`).

## Install

Point Codex at this hook config (user- or project-level `hooks.json`, or bundle
via the plugin manifest):

```json
{ "hooks": { "UserPromptSubmit": [ { "hooks": [
  { "type": "command", "command": "python3 /ABSOLUTE/PATH/TO/keyward/adapters/codex/codex_hook.py", "timeout": 15 }
] } ] } }
```

`hooks.json` here uses `${CODEX_PLUGIN_ROOT}`; if your Codex version doesn't set
that variable, use the absolute path to `codex_hook.py`.

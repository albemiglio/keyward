---
description: List all secrets currently saved by key-vault (names only, never values).
allowed-tools: Bash(python3:*)
---

# /key-list — show saved secret slots

List names + ages + permissions of secret files in `~/.claude/secrets/`. Values
are never printed.

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/manage_secrets.py" list`

To remove a slot, use `/key-rm <name>`.

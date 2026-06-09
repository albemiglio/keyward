---
description: Delete a saved secret slot from ~/.claude/secrets/.
argument-hint: <name>
allowed-tools: Bash(python3:*)
---

# /key-rm — delete a saved secret

Removes `~/.claude/secrets/<name>.txt` if it exists. The file is overwritten
with zeros before deletion (best-effort; not guaranteed on SSDs with
wear-leveling or copy-on-write filesystems).

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/manage_secrets.py" remove "$ARGUMENTS"`

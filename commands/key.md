---
description: Save an API key to ~/.claude/secrets/<name>.txt. The hook intercepts the value before it reaches the model.
argument-hint: <name>=<value>
---

# /key — explicit secret registration

Syntax: `/key NAME=VALUE`

When you type this, the **key-vault `UserPromptSubmit` hook** detects the
`NAME=VALUE` pair, saves the value to `~/.claude/secrets/<NAME>.txt` (chmod
600), blocks the original prompt, and re-submits a sanitized version where the
value is replaced with `<<secret:NAME stored at ~/.claude/secrets/NAME.txt>>`.

The value never reaches the model context or the session transcript.

## Examples

```
/key openai=sk-proj-abc...   then use it to call gpt-5
/key stripe=sk_live_xyz...   then process the test charge
```

The auto-detection regex also catches well-known key formats (sk-ant-, ghp_,
AIza..., etc.) even without the `/key` prefix — explicit registration is only
needed for custom or internal tokens not in the regex library.

## Using a saved key

Reference it by path. Claude should always source it via:

```bash
export OPENAI_API_KEY=$(cat ~/.claude/secrets/openai.txt) && curl ...
```

…not `cat` alone (which prints the value into the bash output → model context).

Arguments: $ARGUMENTS

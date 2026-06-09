---
name: using-key-vault
description: Use when a prompt references a file path under ~/.claude/secrets/, or contains a `<<secret:NAME stored at ...>>` reference, or asks to use a saved API key. Teaches the correct pattern for reading vaulted secrets WITHOUT leaking them into bash output, the model context, or the session transcript.
---

# Using key-vault secrets safely

The `key-vault` plugin saves intercepted API keys to `~/.claude/secrets/<name>.txt`
with chmod 600 permissions. When the user's prompt references one of these
files — directly or via a `<<secret:NAME stored at ~/.claude/secrets/NAME.txt>>`
reference — you must read and use the value WITHOUT printing it.

## The rule

**Never `cat` a secret file as a top-level command, never echo its contents,
never paste its value into your reply, never write it into a file the user can
read alongside their code.**

The contents of bash stdout are added to your context window and persist in the
transcript. If you `cat ~/.claude/secrets/openai.txt`, the value is now in the
conversation — defeating the entire purpose of the vault.

## The pattern

Always **inline-expand the secret as a shell variable** in the same command
that uses it. The value flows from disk → process env → tool, never appearing
in your stdout.

### ✅ Correct

```bash
export OPENAI_API_KEY=$(cat ~/.claude/secrets/openai.txt) && curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```

```bash
GITHUB_TOKEN=$(cat ~/.claude/secrets/github_pat_classic.txt) gh api /user
```

```bash
ANTHROPIC_API_KEY=$(cat ~/.claude/secrets/anthropic.txt) python3 my_script.py
```

### ❌ Wrong

```bash
cat ~/.claude/secrets/openai.txt              # value into stdout → context
KEY=$(cat ~/.claude/secrets/openai.txt); echo $KEY  # explicit echo
head ~/.claude/secrets/openai.txt             # value into stdout
```

```python
with open(os.path.expanduser("~/.claude/secrets/openai.txt")) as f:
    print(f.read())                           # printed → captured by stdout
```

## When the user asks you to use a key

1. Identify which slot to use (look for `<<secret:NAME ...>>` in the prompt,
   or ask if ambiguous).
2. Choose the env-var name expected by the tool/SDK you're calling
   (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, etc.).
3. Use the inline-expansion pattern in a SINGLE bash command.
4. In your reply, refer to "the saved key" — never repeat the value even if
   you accidentally observed it.

## When you must verify a key exists

If you need to check whether a slot is populated WITHOUT reading the value:

```bash
test -s ~/.claude/secrets/openai.txt && echo "openai slot OK" || echo "openai slot empty/missing"
```

## If the user pastes a new key inline

The hook handles it automatically: detection → save → sanitized re-paste.
You'll see a `<<secret:NAME ...>>` reference in the sanitized prompt instead
of the raw value. Treat that reference exactly like a slot path.

## What NOT to do

- Do not suggest the user rotate the key just because it was saved. The vault
  is the safe place — only suggest rotation if the value actually leaked
  (e.g., it appeared in a prior assistant reply, was committed to git, or was
  pasted into a non-`/raw` prompt before key-vault was installed).
- Do not write the secret value into config files, `.env` files, or anywhere
  on disk outside `~/.claude/secrets/`. If the user needs an `.env`, write a
  reference like `OPENAI_API_KEY=$(cat ~/.claude/secrets/openai.txt)` into
  their shell rc, not the raw value into `.env`.
- Do not pass the secret through chained commands that buffer or log
  (e.g., `tee`, `set -x` mode, verbose curl).

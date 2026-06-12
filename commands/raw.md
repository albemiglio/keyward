---
description: Bypass Keyward detection for this single prompt — useful for discussing key formats, pasting example tokens, or sharing logs that contain dummy secrets.
argument-hint: <text>
---

# /raw — bypass secret detection

Syntax: `/raw <anything>`

When you prefix a message with `/raw `, the Keyward hook strips the prefix
and re-submits the remainder **without scanning for secrets**. Use this when:

- You want to discuss key formats with Claude (e.g., "what does a sk-ant-
  token look like?")
- You're pasting log output that contains dummy/expired/example tokens
- A false positive is blocking a legitimate prompt

⚠️  This bypass disables all protection. Only use it when you're sure the
content does NOT contain a real, live secret.

Arguments: $ARGUMENTS

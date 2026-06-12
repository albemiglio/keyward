# Detection Patterns

Everything Keyward decides to treat as a secret is decided in `scripts/detect.py`. Detection is pure: it takes the prompt string and returns `{"secrets": [{"name", "value", "span": [start, end], "source"}], "raw_mode": bool}` — no disk, no clipboard, no network. This page documents every pattern, marker, and filter exactly as they appear in the source.

`detect.py` runs four detection layers, in this order: **explicit markers** (three syntaxes), then **regex auto-detection**, then an **opt-in gitleaks pass**. A `/raw ` prefix short-circuits all of it. See [[Architecture]] for how the results flow into save/sanitize/paste, and [[Configuration]] for the gitleaks switch.

## Regex pattern library

These are the high-confidence, prefix-anchored patterns in `REGEX_PATTERNS` (matched via `pattern.finditer`; the full match, group 0, is the secret value). The "example shape" column shows the *structure* the regex requires — not a real key.

| Provider (slot name) | Pattern | Example shape |
|---|---|---|
| `anthropic` | `sk-ant-(?:api\|admin)\d+-[A-Za-z0-9_\-]{80,}` | `sk-ant-api03-` + 80+ chars |
| `openai_project` | `sk-proj-[A-Za-z0-9_\-]{40,}` | `sk-proj-` + 40+ chars |
| `openai` | `sk-(?!ant-\|proj-)[A-Za-z0-9]{32,}` | `sk-` + 32+ chars (excludes `ant-`/`proj-`) |
| `github_pat_classic` | `ghp_[A-Za-z0-9]{36}` | `ghp_` + exactly 36 chars |
| `github_pat_fine` | `github_pat_[A-Za-z0-9_]{82}` | `github_pat_` + exactly 82 chars |
| `github_oauth` | `gho_[A-Za-z0-9]{36}` | `gho_` + exactly 36 chars |
| `github_server` | `ghs_[A-Za-z0-9]{36}` | `ghs_` + exactly 36 chars |
| `github_user` | `ghu_[A-Za-z0-9]{36}` | `ghu_` + exactly 36 chars |
| `gitlab_pat` | `glpat-[A-Za-z0-9_\-]{20}` | `glpat-` + exactly 20 chars |
| `slack_token` | `xox[baprs]-[A-Za-z0-9\-]{10,}` | `xoxb-` / `xoxa-` / … + 10+ chars |
| `google_api` | `AIza[A-Za-z0-9_\-]{35}` | `AIza` + exactly 35 chars |
| `aws_access_key` | `(?:AKIA\|ASIA)[A-Z0-9]{16}` | `AKIA`/`ASIA` + 16 upper/digits |
| `hugging_face` | `hf_[A-Za-z0-9]{34,}` | `hf_` + 34+ chars |
| `stripe_live_secret` | `sk_live_[A-Za-z0-9]{24,}` | `sk_live_` + 24+ chars |
| `stripe_test_secret` | `sk_test_[A-Za-z0-9]{24,}` | `sk_test_` + 24+ chars |
| `stripe_live_pub` | `pk_live_[A-Za-z0-9]{24,}` | `pk_live_` + 24+ chars |
| `stripe_webhook` | `whsec_[A-Za-z0-9]{32,}` | `whsec_` + 32+ chars |
| `sendgrid` | `SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}` | `SG.` + 22 + `.` + 43 chars |
| `replicate` | `r8_[A-Za-z0-9]{40}` | `r8_` + exactly 40 chars |
| `npm_token` | `npm_[A-Za-z0-9]{36}` | `npm_` + exactly 36 chars |
| `digitalocean` | `dop_v1_[a-f0-9]{64}` | `dop_v1_` + 64 hex chars |
| `mailgun` | `key-[a-f0-9]{32}` | `key-` + 32 hex chars |
| `linear` | `lin_api_[A-Za-z0-9]{40}` | `lin_api_` + exactly 40 chars |
| `jwt` | `eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}` | `eyJ…`.`eyJ…`.`…` (three dot-separated b64url segments) |

Notes that matter in practice:

- **`openai` excludes Anthropic and OpenAI-project keys** with a negative lookahead `(?!ant-|proj-)`, so a `sk-ant-…` or `sk-proj-…` is never double-claimed by the generic `sk-` rule. The more specific patterns also sit earlier in the list and win on span ordering (below).
- **Fixed-length vs. open-ended.** GitHub, Google, AWS, GitLab, Replicate, npm, DigitalOcean, Mailgun, Linear, and SendGrid require an exact tail length; the rest use `{N,}` (at least N). This is what the test suite exercises — e.g. `ghp_` + 36 `a`s, `AIza` + 35 chars, `AKIA` + 16 chars.
- **Duplicate providers are auto-indexed.** If two keys match the same slot name, the first keeps the bare name and subsequent ones get a numeric suffix starting at `_2` (`github_pat_classic`, then `github_pat_classic_2`). The index is `existing_same_provider + 1` where the first match already counted as 0.

## Explicit markers

When the regex library doesn't cover your token, you tag it yourself. All three forms produce a named slot and set `source` accordingly. Crucially, **only the *value* span is claimed and replaced** — the marker text itself (`/key`, `KEY:name=`, `KEY=`) stays in the prompt so the model still understands what happened.

| Syntax | Regex (`detect.py`) | `source` | Slot name |
|---|---|---|---|
| `/key NAME=VALUE` | `/key\s+([A-Za-z][A-Za-z0-9_\-]{0,63})=(\S+)` | `explicit_slash` | `NAME` (sanitized) |
| `KEY:NAME=VALUE` | `\bKEY:([A-Za-z][A-Za-z0-9_\-]{0,63})=(\S+)` | `explicit_named` | `NAME` (sanitized) |
| `KEY=VALUE` | `\bKEY=(\S+)` | `explicit_default` | `default` |

Examples (drawn from `tests/test_keyward.py`):

```text
/key openai=mysupersecretvalue123 go
        → name "openai",  value "mysupersecretvalue123",  source explicit_slash

deploy KEY:stripe=sk_custom_xyz now
        → name "stripe",  value "sk_custom_xyz",  source explicit_named

save KEY=randomvalue here
        → name "default", value "randomvalue",   source explicit_default
```

Details:

- **The value is `\S+`** — it runs to the next whitespace. So `/key db=p@ss w0rd` captures `p@ss` only; quote or strip spaces if your secret contains them.
- **The name is `[A-Za-z][A-Za-z0-9_\-]{0,63}`** — must start with a letter, up to 64 chars, letters/digits/underscore/hyphen only. A name containing other characters means the marker simply won't match at that position (e.g. `/key prod/db=…` does not match, because `/` can't appear in the name and `=` doesn't follow `prod`). Whatever name *is* captured is then run through `sanitize_slot_name()` (any stray char → `_`, truncated to 64, empty → `default`) before becoming the filename.
- **Markers are checked before regex** (slash, then named, then default), so an explicitly-tagged value is claimed first and a later regex pattern won't re-claim the same span.

`/key NAME=VALUE` is also surfaced as a slash command in the plugin — see the table in [[Home]].

## Placeholder / example filter

To avoid triggering when you're *talking about* key formats rather than pasting a real one, any candidate value that contains a placeholder token (case-insensitive substring) is skipped at every layer — markers, regex, and gitleaks. The tokens are:

```text
EXAMPLE   PLACEHOLDER   XXX   YYY   REDACTED   FAKE   DUMMY   ...   ***
```

(`looks_like_placeholder()` upper-cases the value and checks `any(tok in upper for tok in PLACEHOLDER_TOKENS)`.) So `sk-ant-api03-EXAMPLE…` and `ghp_XXXXXXXX…` are both ignored — verified by the suite's `test_placeholder_filtered` / `test_placeholder_xxx`. The filter applies at every layer, explicit markers included, and it checks the *value* — so if you have a real secret that genuinely contains one of these substrings, neither `/key` nor a renamed slot will save it. Send it with the `/raw` bypass (below) instead.

## `/raw` bypass

If the prompt (after left-strip) starts with `/raw `, `detect()` returns `{"secrets": [], "raw_mode": True}` immediately — **no detection layer runs at all**. This is the deliberate escape hatch for discussing key shapes, pasting documentation examples, or any prompt you want sent verbatim. `intercept.py` then strips one leading `/raw ` and re-submits the remainder unchanged (see [[Architecture]] and [[Troubleshooting]]).

## Opt-in gitleaks pass

The built-in regex list is fast but finite. [gitleaks](https://github.com/gitleaks/gitleaks) ships a large, maintained rule set that catches formats Keyward's regex doesn't (generic high-entropy assignments, dozens of additional providers). It runs **only when `KEYWARD_USE_GITLEAKS=1` and the `gitleaks` binary is on `PATH`** — `gitleaks_enabled()` requires both. It's off by default because it adds a subprocess spawn (~50–150 ms by the source's estimate) to every prompt. Turn it on via [[Configuration]].

How `gitleaks_scan()` works:

1. Writes the prompt to a temp file in a fresh `mkdtemp` dir (gitleaks v8 has no clean stdin-string mode).
2. Runs `gitleaks detect --no-git --source <dir> --report-format json --report-path <report> --exit-code 0 --no-banner` (10 s timeout). `--exit-code 0` means findings don't make the process "fail"; `--no-git` treats the input as plain files.
3. Parses the JSON report, taking `Secret` (or `Match`) as the value and `RuleID` (or `Rule`, default `gitleaks`) as the slot name, run through `sanitize_slot_name()`.
4. Removes the temp dir (`finally`). **Any** failure along the way — binary missing, subprocess error, no report, bad JSON, non-list payload — returns `[]`. gitleaks never breaks detection; worst case it contributes nothing.

How findings **merge** with the regex/marker results (this is the important part):

- gitleaks runs **last**, after explicit markers and regex have already claimed their spans.
- For each `(rule_id, secret_value)` gitleaks reports, `detect()` locates **every** occurrence of that value in the prompt via `str.find` in a loop — it does *not* trust gitleaks' own line/column numbers (those have drifted across versions; this is version-independent).
- Each occurrence is checked against `claimed_spans`; **overlapping spans are skipped**, so gitleaks only adds secrets the earlier layers missed. No double-counting, no fighting over the same bytes.
- Survivors get `source: "gitleaks"`, a name of `rule_id` (or `rule_id_2`, `rule_id_3`, … for repeats), and are added to the result.

The suite's `test_gitleaks_catches_what_regex_misses` demonstrates the point: a bare 32-hex assignment (`const apiKey = "a1b9…";`) isn't in `REGEX_PATTERNS`, but with the env var set, gitleaks flags it and the span still points exactly at the value. `test_gitleaks_off_by_default` asserts `gitleaks_enabled()` is false without the var.

## Span, overlap, and ordering

A few mechanics that affect what you get back:

- **`claimed_spans` prevents overlap.** Each layer records the `[start, end)` it took; `overlaps()` rejects any later candidate that intersects an already-claimed span. This is why a `sk-ant-…` isn't claimed twice and why an explicit-marker value isn't re-grabbed by regex.
- **Right-to-left replacement.** `sanitize_prompt()` in `intercept.py` replaces spans sorted by start **descending**, so earlier replacements don't shift the indices of spans yet to be processed.
- **Deterministic output.** Before returning, `detect()` sorts `found` by `span[0]` ascending. Output order is stable regardless of which layer found what — which is what makes the tests (and the sanitized prompt) reproducible.

## How to add a new pattern

If you hit a provider Keyward should recognize out of the box, add it to the regex library. The flow:

1. **Edit `REGEX_PATTERNS` in `scripts/detect.py`.** Append a `(slot_name, re.compile(r"…"))` tuple. Anchor on the provider's fixed prefix and constrain length/charset tightly — prefer `{N}` (exact) or `{N,}` (floor) over open-ended `+` so you don't over-match. Pick a clear lowercase `slot_name`; it becomes both the disambiguation key and the on-disk filename stem. If your prefix could be shadowed by a broader existing rule (the way `sk-` would swallow `sk-ant-`), either place the specific rule earlier or add a negative lookahead like the `openai` pattern's `(?!ant-|proj-)`.

2. **Add a test in `tests/test_keyward.py`.** Follow the existing `TestDetect` style — build a synthetic value (`prefix + "a" * N`) and assert via the `assert_single(prompt, expected_name, expected_value, "regex")` helper, which also checks that the returned span slices back to exactly your value:

   ```python
   def test_myprovider(self):
       v = "myp_" + "a" * 40
       self.assert_single(f"use {v} now", "myprovider", v, "regex")
   ```

   Add a placeholder/negative case too if your prefix is short enough to risk false positives.

3. **Run the suite** (stdlib `unittest`, no third-party deps; gitleaks tests self-skip when the binary is absent):

   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py' -v
   # or
   python3 tests/test_keyward.py
   ```

   Green across macOS/Linux/Windows is the bar — see [[Contributing]] for the CI matrix and PR conventions. For formats too numerous or fast-moving to bake into regex, prefer pointing users at the opt-in gitleaks pass rather than growing the list unboundedly.

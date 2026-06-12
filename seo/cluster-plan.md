# Keyward — keyword cluster & content architecture

Methodology: SERP-overlap clustering (which pages Google already ranks together)
across 6 seed searches. Brand-new site, no volume data — priorities are by
SERP density + intent, not absolute volume.

## Pillar (the landing page — `/`)

**Primary:** stop leaking API keys into Claude Code · keep secrets out of Claude Code
**Secondary:** hide api keys from AI coding assistant · claude code secrets plugin ·
redact secrets claude code · stop pasting api keys into claude code
**Intent:** informational (problem) + transactional (the product)
**Shared SERP:** houtini.com, dev.to/sensitive-canary, strongly.ai, mintmcp, bdtechtalks,
gitguardian — tight cluster, all one topic.

## Spoke 1 — Alternatives / comparison (`/alternatives`)

**Primary:** claude code secrets plugin alternatives · keyward vs sensitive-canary
**Targets:** sensitive-canary (direct competitor, also UserPromptSubmit), nopeek,
cc-redact, claude-secrets, vaultbix
**Intent:** commercial (comparison). Captures competitor-aware searchers.
**Angle:** keyward = inbound *paste* interception + auto re-submit + cross-platform;
most rivals handle Claude *reading* .env files, or are browser extensions.

## Spoke 2 — How it works / the hook (folded into `/` + the article)

**Primary:** claude code UserPromptSubmit hook secrets · prevent api key leak hook
**Intent:** informational (technical). Shared SERP: morphllm, claudefa.st hooks guide,
code.claude.com/docs, sensitive-canary.

## Spoke 3 — Off-site article (dev.to / blog) → backlink + top-of-funnel

**Title:** "Stop leaking API keys into Claude Code" (the sensitive-canary playbook)
**Intent:** informational. Doubles as a backlink to the landing + repo.

## Listicle targets (be *included*, not built)

best claude code security plugins / best claude code plugins 2026 →
claude-codex.fr, buildtolaunch, firecrawl, composio, claudedirectory.
Lever: the awesome-list PRs + community marketplace listing.

## On-page primary map

| URL | Title tag | H1 |
|-----|-----------|-----|
| `/` | Keyward — Stop leaking API keys into Claude Code | Keep API keys out of your Claude Code prompts. |
| `/alternatives` | Keyward vs sensitive-canary, nopeek & cc-redact | Claude Code secret-redaction plugins, compared |

## GEO (AI search)

`llms.txt` + a citable FAQ block (short, declarative answers). The audience asks
ChatGPT/Perplexity "how do I stop leaking secrets to Claude Code" — be the
quotable source.

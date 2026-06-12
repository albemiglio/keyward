#!/bin/bash
# publish-wiki.sh — sync the versioned /wiki pages to the GitHub wiki.
#
# ONE-TIME PREREQUISITE (GitHub limitation — no API exists for this):
#   Open  https://github.com/albemiglio/keyward/wiki  →  "Create the first page"
#   →  type anything  →  "Save page".  This initializes the wiki git repo.
#
# After that, run this from the repo root anytime you edit /wiki:
#   ./scripts/publish-wiki.sh
#
# It clones the wiki repo, copies every /wiki/*.md over it, and pushes.

set -euo pipefail

WIKI_REMOTE="https://github.com/albemiglio/keyward.wiki.git"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)/wiki"

if [ ! -d "$SRC_DIR" ]; then
  echo "error: $SRC_DIR not found (run from the keyward repo)" >&2
  exit 1
fi

if ! git ls-remote "$WIKI_REMOTE" >/dev/null 2>&1; then
  echo "error: the wiki repo isn't initialized yet." >&2
  echo "       Create the first page once via the web UI, then re-run:" >&2
  echo "       https://github.com/albemiglio/keyward/wiki" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --quiet "$WIKI_REMOTE" "$TMP"
cp "$SRC_DIR"/*.md "$TMP"/
cd "$TMP"

if git diff --quiet && git diff --cached --quiet && [ -z "$(git status --porcelain)" ]; then
  echo "wiki already up to date — nothing to publish."
  exit 0
fi

git add -A
git commit --quiet -m "Sync wiki from /wiki"
git push --quiet
echo "✓ published $(ls -1 "$SRC_DIR"/*.md | wc -l | tr -d ' ') pages to the Keyward wiki."

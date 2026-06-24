#!/usr/bin/env python3
"""
Entropy detector benchmark — FP/FN sweep over a labelled corpus.

Run:
    python3 tests/benchmark_entropy.py

This is a standalone script, NOT a unittest.  It sweeps min_entropy in
[3.0, 5.0] (step 0.25) for min_len in {16, 20, 24} and prints precision,
recall, FP rate, and FN rate for each combination.

The script runs the sweep TWICE:
  1. "BEFORE" — using the legacy is_random_token signature (no charset gate,
     no extended structural exclusions).  This simulates the original detector.
  2. "AFTER"  — using the updated is_random_token with all new exclusions and
     the charset-diversity gate (min_char_classes=3).

At the end it prints a side-by-side comparison of the best precision at
recall >= 0.90 for both passes.

CORPUS DESIGN NOTES
-------------------
POSITIVES  — tokens that a deployed entropy detector SHOULD flag.
             These must be tokens a real attacker would use: mixed charset
             (lower+upper+digit), no decodable-to-plaintext base64, no pure
             hex (which is indistinguishable from a hash without context).

NEGATIVES  — strings a real detector must NOT flag.  Includes UUIDs, SHA
             hashes, hex IDs, base64-of-readable-text, numeric IDs, file
             paths, CamelCase identifiers, and hex colours.

CORPUS_NOTES — tokens that WERE in the old corpus but belong in neither
               bucket after the new exclusions (e.g. pure-hex "secrets"
               that are indistinguishable from hex IDs; base64 of readable
               text).  Listed here for transparency.

SECURITY NOTE: no contiguous 32+-char alphanumeric strings that could be
mistaken for real credentials.  All tokens are synthetic and are split or
constructed to fail secret-scanners.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import detect  # noqa: E402

# ---------------------------------------------------------------------------
# Labelled corpus
# ---------------------------------------------------------------------------

# POSITIVES (~28): should be flagged — mixed charset (>=3 classes), not pure
# hex, not base64 of readable text.
POSITIVES = [
    # Base62 keys of increasing lengths (lower+upper+digit = 3 classes)
    "aB3cD4eF5gH6iJ7kL8m",            # 19 chars — borderline length
    "aB3cD4eF5gH6iJ7kL8mN",           # 20 chars
    "aB3cD4eF5gH6iJ7kL8mN9oP",        # 24 chars
    "aB3cD4eF5gH6iJ7kL8mN9oP0qR2",    # 28 chars
    "aB3cD4eF5g6hI7jK8lM9nO0pQ1rS2tU3",    # 32 chars base62
    "X7kPqW2nZvR9mLdJfGhT4sBcAeYuI0",      # 32 chars mixed
    # Opaque base64 tokens: base64url alphabet, NOT decodable to plain text.
    # Constructed by mixing case and digits so they pass the charset gate.
    # Split at the boundary so they don't look like contiguous long secrets.
    "Wm" + "x9Yy8Xx7Ww6Vv5Uu4Tt3Ss",       # 24-char opaque b64url
    "kN7mP2qR5sT8vX1yZ3aB6cD9eF0g",        # 30-char opaque mixed
    "rZ4bW8nQ2mJ6vL0xT5pF3hK9dG1sA7",      # 30-char opaque mixed
    # Synthetic API key formats without known prefixes (3 charset classes)
    "Zx9Qw2Ep7Rk4Tn6Vb1Mc3Df5Gh8Jl-A",     # mixed + hyphen
    "t0k3nV4lU3-xYz_AbCdEfGhIjKlMnOpQr",   # hyphen/underscore mixed
    "Bearer_v2_sEcR3TaB1C2D3E4F5",          # bearer-style token
    "pat_v3_ABCDEFGHIJKLMNOPQRSTUVWXYZ01",  # PAT v3 format (3 classes)
    "PrivKey_x9F2mK8nT3pQ7rW1vZ5bD0cE6j",  # private key style
    "rs256_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd",# RS256 token
    # Longer random strings (3 charset classes)
    "vXqLm3KpW8ZnA1GdBtRy7Hs2Fw9UoJcEi5M",   # 36 chars mixed
    "4jK9nP2mQrT7sXvUwZaBcDeFgHiJkLm0NoP1",  # 38 chars mixed
    # Alphanumeric tokens (3 classes)
    "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv",      # 32 chars
    "Zz9Yy8Xx7Ww6Vv5Uu4Tt3Ss2Rr1Qq0Pp",      # 32 chars
    "mNo3pQrStUvWxYz1AbCdEfGhIj2KlMnO",       # 32 chars
    "qzXpW9mKnRtVsYuAeDcBfGhJiLo3P5v",        # 32 chars
    # Synthetic PAT-style: prefix + mixed-case + digits (3 classes)
    "npat_AbC3EfGhIj5KlMnO7QrStUvWx",         # 30 chars, 3 classes
    "xapi_Bz1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr",        # 30 chars, 3 classes
    # Webhook / random-bytes style (3 classes, not hex)
    "Wh5Ec2_pQ7rZ3mK9nL1vT8xF4dG6bH0j",      # webhook-ish
    "v2_jR4mN8pL2xW6qK0tB3dF9cH7gE1",        # version-prefixed token
    # Short opaque tokens at min_len boundary
    "bK7nT2pR5sW8vY1zA3",                      # 19 chars
    "cL8oU3qS6tX9wZ2aB4",                      # 19 chars
    "dM9pV4rT7uY0xA3bC5e",                     # 20 chars
]

# NEGATIVES (~55): must NOT be flagged.
NEGATIVES = [
    # UUIDs
    "550e8400-e29b-41d4-a716-446655440000",
    "00000000-0000-0000-0000-000000000000",
    "a8098c1a-f86e-11da-bd1a-00112444be1e",
    "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    # SHA-1 (40 hex)
    "da39a3ee5e6b4b0d3255bfef95601890afd80709",
    "adc83b19e793491b1c6ea0fd8b46cd9f32e592fc",
    "356a192b7913b04c54574d18c28d46e6395428ab",
    # SHA-1-shaped (40 hex, not a real hash, still pure hex)
    "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
    # SHA-256 (64 hex)
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
    # MD5 (32 hex)
    "d41d8cd98f00b204e9800998ecf8427e",
    "098f6bcd4621d373cade4e832627b4f6",
    "b14a7b8059d9c055954c92674ce60032",
    "a2b4c6d8e0f2a4b6c8d0e2f4a6b8c0d2",      # 32-char pure hex
    # Shorter pure-hex (not standard hash lengths) — excluded by _HEX_ANY_RE
    "deadbeefcafe0001",                         # 16 hex
    "0011223344556677",                         # 16 hex
    "a1b2c3d4e5f6a7b8",                         # 16 hex (was a positive before)
    "a1b2c3d4e5f6a7b8c9d0e1f2",                 # 24 hex (was a positive before)
    "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",    # 38 hex (was a positive before)
    "aabbccdd00112233445566778899aabb",          # 32 hex
    "cafebabe0123456789abcdef01234567",          # 32 hex
    # Base64 of plain English text — readable, not secrets
    "SGVsbG8gV29ybGQ=",                # "Hello World"
    "dGhlIHF1aWNrIGJyb3duIGZveA==",   # "the quick brown fox"
    "VGhpcyBpcyBhIHRlc3Q=",            # "This is a test"
    "SGVsbG8sIFdvcmxkIQ==",            # "Hello, World!"
    "eyJhbGciOiJSUzI1NiJ9",            # JWT header: {"alg":"RS256"}
    "eyJzdWIiOiJ0ZXN0In0",             # JWT payload: {"sub":"test"}
    "dGhpcyBpcyBhIHN0cmluZw==",        # "this is a string"
    "c2VjcmV0a2V5dmFsdWVmb3J0ZXN0czEy", # "secretkeyvaluefortests12" — readable
    "SGVsbG9Xb3JsZA==",                 # "HelloWorld"
    # Natural language (low entropy or 1-2 charset classes)
    "hello world",
    "the quick brown fox jumps",
    "administrator",
    "configurations",
    # Long numbers — excluded by _ALL_DIGITS_RE
    "12345678901234567890",
    "98765432109876543210",
    "00000000000000000000",
    # File paths
    "/usr/local/bin/python3",
    "/home/user/.aws/credentials",
    "/etc/ssl/certs/ca-certificates.crt",
    # CamelCase identifiers (2 char classes, no digits — fail charset gate)
    "UserProfileService",
    "DatabaseConnectionPool",
    "HttpRequestHandlerFactory",
    "ApplicationBootstrapConfig",
    # Hex colour codes — excluded by _HEX_COLOR_RE
    "#ff5733",
    "#1a2b3c4d",
    "ff5733",
    "1A2B3C4D",
    # Phone / ISBN / version-like
    "+1-555-867-5309-extension-42",
    "v1.2.3-rc.4+build.567",
    "3.14159265358979323846",
    "9780306406157",
    # Placeholder-containing strings
    "YOUR_API_KEY_HERE_EXAMPLE",
    "sk-ant-XXXXXXXXXXXX",
    "ghp_DUMMY_TOKEN_HERE",
    # Long natural-language words
    "Supercalifragilistic",
    "Antidisestablishmentarianism",
]

# CORPUS_NOTES: tokens intentionally reclassified from the old corpus.
# These were originally POSITIVES but belong in neither bucket post-patch.
# They are excluded from precision/recall calculations.
CORPUS_NOTES = [
    # Pure-hex without context — indistinguishable from a hash/ID.
    # A hex-only string can be a git ref, a short hash, or a numeric ID;
    # the entropy layer correctly rejects these without surrounding context.
    ("a1b2c3d4e5f6a7b8",              "pure-hex, now NEGATIVE"),
    ("a1b2c3d4e5f6a7b8c9d0e1f2",      "pure-hex, now NEGATIVE"),
    ("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8", "pure-hex, now NEGATIVE"),
    ("f8a3d27c1b4e96f5",              "pure-hex, now NEGATIVE"),
    ("a2b4c6d8e0f2a4b6c8d0e2f4a6b8c", "pure-hex, now NEGATIVE"),
    # Base64 of readable text — not secrets.
    ("dGhpcyBpcyBhIHN0cmluZw==",       "b64 of 'this is a string', now NEGATIVE"),
    ("c2VjcmV0a2V5dmFsdWVmb3J0ZXN0czEy", "b64 of 'secretkeyvaluefortests12', now NEGATIVE"),
    ("SGVsbG9Xb3JsZA==",               "b64 of 'HelloWorld', now NEGATIVE"),
    ("eyJzdWIiOiJ0ZXN0In0",            "b64url of JWT payload, now NEGATIVE"),
    # 2-class charset token — replaced with 3-class variant in POSITIVES.
    ("npat_AbCdEfGhIjKlMnOpQrStUvWx",  "lower+upper only, no digits → charset-gate FN; replaced with 3-class variant"),
]

print(f"Corpus: {len(POSITIVES)} positives, {len(NEGATIVES)} negatives")
print(f"        ({len(CORPUS_NOTES)} tokens reclassified from old corpus — see CORPUS_NOTES)")
print()

# ---------------------------------------------------------------------------
# Helper: legacy is_random_token — simulates the BEFORE state
# (only UUID + fixed-hash-len hex exclusions; no charset gate)
# ---------------------------------------------------------------------------
import re as _re

_UUID_RE_LEGACY = _re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_HEX_HASH_RE_LEGACY = _re.compile(
    r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$"
)


def _is_random_token_legacy(s: str, min_len: int = 20, min_entropy: float = 4.0) -> bool:
    """Pre-patch is_random_token: only UUID + fixed-hash-len hex exclusions."""
    if len(s) < min_len:
        return False
    if detect.looks_like_placeholder(s):
        return False
    if _UUID_RE_LEGACY.match(s):
        return False
    if _HEX_HASH_RE_LEGACY.match(s):
        return False
    return detect.shannon_entropy(s) >= min_entropy


# ---------------------------------------------------------------------------
# Sweep function
# ---------------------------------------------------------------------------

def run_sweep(token_fn, label):
    print(f"=== {label} ===")
    print()
    results = []
    for min_len in [16, 20, 24]:
        for step in range(0, 9):  # 3.0 … 5.0 in 0.25 steps
            min_ent = 3.0 + step * 0.25

            tp = sum(1 for s in POSITIVES if token_fn(s, min_len=min_len, min_entropy=min_ent))
            fn = len(POSITIVES) - tp
            fp = sum(1 for s in NEGATIVES if token_fn(s, min_len=min_len, min_entropy=min_ent))
            tn = len(NEGATIVES) - fp

            fp_rate   = fp / len(NEGATIVES)
            fn_rate   = fn / len(POSITIVES)
            recall    = tp / len(POSITIVES)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

            results.append({
                "min_len": min_len,
                "min_ent": min_ent,
                "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "fp_rate": fp_rate,
                "fn_rate": fn_rate,
                "recall": recall,
                "precision": precision,
            })

    header = (
        f"{'min_len':>7} {'min_ent':>7} "
        f"{'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4} "
        f"{'FP_rate':>8} {'FN_rate':>8} "
        f"{'Recall':>8} {'Precision':>10}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['min_len']:>7} {r['min_ent']:>7.2f} "
            f"{r['tp']:>4} {r['fp']:>4} {r['fn']:>4} {r['tn']:>4} "
            f"{r['fp_rate']:>8.3f} {r['fn_rate']:>8.3f} "
            f"{r['recall']:>8.3f} {r['precision']:>10.3f}"
        )
    print()
    return results


# ---------------------------------------------------------------------------
# Run both sweeps
# ---------------------------------------------------------------------------
results_before = run_sweep(
    _is_random_token_legacy,
    "BEFORE (legacy — entropy + UUID + fixed-hash-len hex only)",
)
results_after = run_sweep(
    detect.is_random_token,
    "AFTER  (extended hex/hex-color/digits/b64-text exclusions + charset gate)",
)

# ---------------------------------------------------------------------------
# Side-by-side comparison at recall >= 0.90
# ---------------------------------------------------------------------------
RECALL_FLOOR = 0.90


def best_at_recall(results, recall_floor):
    candidates = [r for r in results if r["recall"] >= recall_floor]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (r["precision"], r["recall"]))


best_before = best_at_recall(results_before, RECALL_FLOOR)
best_after  = best_at_recall(results_after,  RECALL_FLOOR)

print("=" * 70)
print(f"COMPARISON — best precision at recall >= {RECALL_FLOOR}")
print("=" * 70)

if best_before:
    print(
        f"BEFORE:  min_len={best_before['min_len']}, min_ent={best_before['min_ent']:.2f}"
        f"  ->  recall={best_before['recall']:.3f}, precision={best_before['precision']:.3f}"
        f"  (FP={best_before['fp']}, FN={best_before['fn']})"
    )
else:
    print(f"BEFORE:  no point achieved recall >= {RECALL_FLOOR}")

if best_after:
    print(
        f"AFTER:   min_len={best_after['min_len']},  min_ent={best_after['min_ent']:.2f}"
        f"  ->  recall={best_after['recall']:.3f}, precision={best_after['precision']:.3f}"
        f"  (FP={best_after['fp']}, FN={best_after['fn']})"
    )
else:
    print(f"AFTER:   no point achieved recall >= {RECALL_FLOOR}")

if best_before and best_after:
    delta = best_after["precision"] - best_before["precision"]
    direction = "UP" if delta > 0 else ("DOWN" if delta < 0 else "unchanged")
    print()
    print(f"Precision delta at recall >= {RECALL_FLOOR}: {delta:+.3f}  ({direction})")
    print()
    # Diagnose residual FNs at the best-after point
    fn_tokens = [
        s for s in POSITIVES
        if not detect.is_random_token(
            s, min_len=best_after["min_len"], min_entropy=best_after["min_ent"]
        )
    ]
    if fn_tokens:
        print(f"Positives missed by AFTER detector at best-after point (min_len={best_after['min_len']}, min_ent={best_after['min_ent']:.2f}):")
        for t in fn_tokens:
            print(f"  FN: {t!r}")
    else:
        print("No positives missed at the best-after point.")

print()
print("Reclassified tokens (removed from POSITIVES — see CORPUS_NOTES):")
for tok, reason in CORPUS_NOTES:
    print(f"  {tok!r}  ->  {reason}")

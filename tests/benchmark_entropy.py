#!/usr/bin/env python3
"""
Entropy detector benchmark — FP/FN sweep over a labelled corpus.

Run:
    python3 tests/benchmark_entropy.py

This is a standalone script, NOT a unittest.  It sweeps min_entropy in
[3.0, 5.0] (step 0.25) for min_len in {16, 20, 24} and prints precision,
recall, FP rate, and FN rate for each combination.

At the end it recommends the combination that maximises recall while keeping
FP rate ≤ 0.25 (one false positive in four negatives), since the brief states
"FP is the minor problem".
"""
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import detect from the scripts directory
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import detect  # noqa: E402

# ---------------------------------------------------------------------------
# Labelled corpus
# ---------------------------------------------------------------------------

# POSITIVES (~30): real-looking secrets / random tokens of various formats.
# These SHOULD be flagged as random tokens.
POSITIVES = [
    # Base62 keys of increasing lengths
    "aB3cD4eF5gH6iJ7kL8m",          # 19 chars  — borderline length
    "aB3cD4eF5gH6iJ7kL8mN",         # 20 chars
    "aB3cD4eF5gH6iJ7kL8mN9oP",      # 24 chars
    "aB3cD4eF5gH6iJ7kL8mN9oP0qR2",  # 28 chars
    "aB3cD4eF5g6hI7jK8lM9nO0pQ1rS2tU3",  # 32 chars base62
    "X7kPqW2nZvR9mLdJfGhT4sBcAeYuI0",    # 32 chars mixed case + digits
    # Base64 keys (not plain English, so high entropy)
    "dGhpcyBpcyBhIHN0cmluZw==",          # 24 chars base64 of random bytes-ish
    "c2VjcmV0a2V5dmFsdWVmb3J0ZXN0czEy",  # 34 chars base64
    "SGVsbG9Xb3JsZA==",                   # 16 chars base64 (short but base64)
    # Prefix-less random hex of lengths NOT in the hash exclusion list (not 32/40/64)
    "a1b2c3d4e5f6a7b8",                   # 16 hex chars
    "a1b2c3d4e5f6a7b8c9d0e1f2",           # 24 hex chars
    "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",  # 38 hex chars (not 40=sha1)
    # Typical API key formats without known prefixes
    "Zx9Qw2Ep7Rk4Tn6Vb1Mc3Df5Gh8Jl-A",   # synthetic mixed token (no real key)
    "t0k3nV4lU3-xYz_AbCdEfGhIjKlMnOpQr",  # hyphen/underscore mixed
    "eyJzdWIiOiJ0ZXN0In0",                 # JWT-segment-ish (shorter base64url)
    "Bearer_v2_sEcR3TaB1C2D3E4F5",        # bearer-style token
    "npat_AbCdEfGhIjKlMnOpQrStUvWx",      # GitHub-like but without exact ghp_ prefix
    "pat_v3_ABCDEFGHIJKLMNOPQRSTUVWXYZ01", # PAT v3 format
    "PrivKey_x9F2mK8nT3pQ7rW1vZ5bD0cE6j", # private key style
    "rs256_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd", # RS256 token
    # Longer random strings
    "vXqLm3KpW8ZnA1GdBtRy7Hs2Fw9UoJcEi5M",  # 36 chars mixed
    "4jK9nP2mQrT7sXvUwZaBcDeFgHiJkLm0NoP1", # 38 chars mixed
    # Plain random looking values commonly found in .env files
    "f8a3d27c1b4e96f5",                     # 16-char hex (not hash length)
    "a2b4c6d8e0f2a4b6c8d0e2f4a6b8c",       # 29 hex chars (not 32=md5)
    "qzXpW9mKnRtVsYuAeDcBfGhJiLo3P5v",     # 32 chars mixed case but not pure hex
    # Some with special chars (URL-safe base64)
    "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv",    # 32 chars alphanumeric
    "Zz9Yy8Xx7Ww6Vv5Uu4Tt3Ss2Rr1Qq0Pp",    # 32 chars alphanumeric
    "mNo3pQrStUvWxYz1AbCdEfGhIj2KlMnO",    # 32 chars alphanumeric
]

# NEGATIVES (~40): things that look random-ish but are NOT secrets.
# These should NOT be flagged.
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
    # SHA-256 (64 hex)
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
    # MD5 (32 hex)
    "d41d8cd98f00b204e9800998ecf8427e",
    "098f6bcd4621d373cade4e832627b4f6",
    "b14a7b8059d9c055954c92674ce60032",
    "a2b4c6d8e0f2a4b6c8d0e2f4a6b8c0d2",    # 32-char pure hex — MD5-shaped, excluded
    # SHA-1 shaped (40 hex) — excluded
    "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",  # 40-char pure hex — SHA1-shaped
    # Base64 of plain English text (high entropy, but not a secret)
    "SGVsbG8gV29ybGQ=",            # "Hello World"
    "dGhlIHF1aWNrIGJyb3duIGZveA==",  # "the quick brown fox"
    "VGhpcyBpcyBhIHRlc3Q=",        # "This is a test"
    # Normal English sentences / words (low entropy)
    "hello world",
    "the quick brown fox jumps",
    "password123",                  # common weak password — but under min_len=20 → excluded anyway
    "administrator",
    "configurations",
    # Long numbers
    "12345678901234567890",
    "98765432109876543210",
    "00000000000000000000",
    # File paths
    "/usr/local/bin/python3",
    "/home/user/.aws/credentials",
    "/etc/ssl/certs/ca-certificates.crt",
    # CamelCase identifiers
    "UserProfileService",
    "DatabaseConnectionPool",
    "HttpRequestHandlerFactory",
    "ApplicationBootstrapConfig",
    # Hex color codes (short, but let's add longer ones)
    "#ff5733",
    "#1a2b3c4d",                   # short 8-hex
    "rgba(255,128,64,0.5)",
    # ISBN / phone-like
    "9780306406157",               # ISBN-13
    "+1-555-867-5309-extension-42",
    # Version strings
    "v1.2.3-rc.4+build.567",
    "3.14159265358979323846",
    # Placeholder-containing strings (should be caught by looks_like_placeholder)
    "YOUR_API_KEY_HERE_EXAMPLE",
    "sk-ant-XXXXXXXXXXXX",
    "ghp_DUMMY_TOKEN_HERE",
    # A real word that happens to be 20+ chars
    "Supercalifragilistic",
    "Antidisestablishmentarianism",
    # JWT header/payload part alone (just base64url, not the full token)
    "eyJhbGciOiJSUzI1NiJ9",       # only 20 chars, looks like b64
]

print(f"Corpus: {len(POSITIVES)} positives, {len(NEGATIVES)} negatives")
print()

# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------
import math

results = []

for min_len in [16, 20, 24]:
    for step in range(0, 9):  # 0..8 → 3.0, 3.25, ..., 5.0
        min_ent = 3.0 + step * 0.25

        tp = sum(1 for s in POSITIVES if detect.is_random_token(s, min_len=min_len, min_entropy=min_ent))
        fn = len(POSITIVES) - tp
        fp = sum(1 for s in NEGATIVES if detect.is_random_token(s, min_len=min_len, min_entropy=min_ent))
        tn = len(NEGATIVES) - fp

        fp_rate  = fp / len(NEGATIVES)
        fn_rate  = fn / len(POSITIVES)
        recall   = tp / len(POSITIVES)
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

# ---------------------------------------------------------------------------
# Print table
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Recommendation: maximise recall, FP_rate ≤ 0.25
# ---------------------------------------------------------------------------
FP_BUDGET = 0.25
candidates = [r for r in results if r["fp_rate"] <= FP_BUDGET]

if candidates:
    best = max(candidates, key=lambda r: (r["recall"], -r["fn_rate"]))
    print("=== RECOMMENDATION ===")
    print(f"Best combination within FP_rate ≤ {FP_BUDGET:.2f}:")
    print(
        f"  min_len={best['min_len']}, min_entropy={best['min_ent']:.2f}  →  "
        f"recall={best['recall']:.3f}, FP_rate={best['fp_rate']:.3f}, "
        f"precision={best['precision']:.3f}"
    )
    print()
    print(
        "Rationale: FP is the minor problem (users can /raw a false positive).\n"
        "The recommended point gives the highest recall within the FP budget,\n"
        f"meaning it catches {best['tp']}/{len(POSITIVES)} real tokens while\n"
        f"falsely flagging {best['fp']}/{len(NEGATIVES)} benign strings."
    )
else:
    print(f"No combination achieved FP_rate ≤ {FP_BUDGET:.2f}.")
    print("Consider relaxing the FP budget or enriching the corpus.")

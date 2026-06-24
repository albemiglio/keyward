#!/usr/bin/env python3
"""Entropy layer — URL false-positive exclusion + unique slots. stdlib-only."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import detect  # noqa: E402

# Split literals so the repo stays clean of scanner-tripping contiguous tokens.
T1 = "Xy9Qw2Ep7Rk4Tn6" "Vb1Mc3Df5Gh8Jl0A"   # 31-char base62, 3 classes
T2 = "Zk4Tn6Vb1Mc3Df5" "Gh8Jl0AXy9Qw2Ep7R"  # 32-char base62, 3 classes


class TestEntropyFP(unittest.TestCase):
    def test_url_not_random_token(self):
        self.assertFalse(detect.is_random_token("https://www.example.com/blog/some-long-slug-abc123def"))

    def test_path_not_random_token(self):
        self.assertFalse(detect.is_random_token("/usr/local/share/" + T1))

    def test_bare_token_still_random(self):
        self.assertTrue(detect.is_random_token(T1))

    def test_entropy_layer_skips_urls(self):
        os.environ["KEYWARD_ENTROPY"] = "1"
        try:
            r = detect.detect("see https://www.example.com/articles/2026/some-long-entropic-slug-abc123def here")
        finally:
            os.environ.pop("KEYWARD_ENTROPY", None)
        self.assertEqual([s for s in r["secrets"] if s["source"] == "entropy"], [])

    def test_entropy_layer_unique_slots(self):
        os.environ["KEYWARD_ENTROPY"] = "1"
        try:
            r = detect.detect(f"{T1} and {T2}")
        finally:
            os.environ.pop("KEYWARD_ENTROPY", None)
        names = [s["name"] for s in r["secrets"] if s["source"] == "entropy"]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(names), len(set(names)))  # no clobber


if __name__ == "__main__":
    unittest.main()

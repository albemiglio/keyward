#!/usr/bin/env python3
"""Gemini adapter — deny-on-secret behaviour. stdlib-only (unittest)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "adapters" / "gemini"))
import gemini_hook  # noqa: E402

SECRETS = Path.home() / ".claude" / "secrets"


class TestGeminiAdapter(unittest.TestCase):
    def tearDown(self):
        (SECRETS / "GEMINITEST_API_KEY.txt").unlink(missing_ok=True)

    def test_secret_denies_and_saves(self):
        out = gemini_hook.handle({"prompt": "GEMINITEST_API_KEY=Secret1234abcd"})
        self.assertIsNotNone(out)
        self.assertEqual(out["decision"], "deny")
        self.assertIn("keyward", out["reason"])
        self.assertTrue((SECRETS / "GEMINITEST_API_KEY.txt").exists())

    def test_clean_prompt_allows(self):
        self.assertIsNone(gemini_hook.handle({"prompt": "hello how are you"}))

    def test_raw_bypass_allows(self):
        self.assertIsNone(gemini_hook.handle({"prompt": "/raw GEMINITEST_API_KEY=Secret1234abcd"}))


if __name__ == "__main__":
    unittest.main()

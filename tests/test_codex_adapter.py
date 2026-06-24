#!/usr/bin/env python3
"""Codex adapter — block-on-secret behaviour. stdlib-only (unittest)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "adapters" / "codex"))
import codex_hook  # noqa: E402

SECRETS = Path.home() / ".claude" / "secrets"


class TestCodexAdapter(unittest.TestCase):
    def tearDown(self):
        (SECRETS / "CODEXTEST_API_KEY.txt").unlink(missing_ok=True)

    def test_secret_blocks_and_saves(self):
        out = codex_hook.handle({"prompt": "CODEXTEST_API_KEY=Secret1234abcd"})
        self.assertIsNotNone(out)
        self.assertEqual(out["decision"], "block")
        self.assertIn("keyward", out["reason"])
        self.assertTrue((SECRETS / "CODEXTEST_API_KEY.txt").exists())

    def test_clean_prompt_allows(self):
        self.assertIsNone(codex_hook.handle({"prompt": "hello how are you"}))

    def test_raw_bypass_allows(self):
        self.assertIsNone(codex_hook.handle({"prompt": "/raw CODEXTEST_API_KEY=Secret1234abcd"}))


if __name__ == "__main__":
    unittest.main()

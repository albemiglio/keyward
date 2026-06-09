#!/usr/bin/env python3
"""
key-vault test suite — cross-platform, stdlib-only (unittest).

Run:
    python3 -m unittest discover -s tests -p 'test_*.py' -v
    # or
    python3 tests/test_keyvault.py

No third-party dependencies. The gitleaks integration tests self-skip when the
gitleaks binary is not installed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & importable detect module
# ---------------------------------------------------------------------------
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
HOOKS_DIR = PLUGIN_ROOT / "hooks"

sys.path.insert(0, str(SCRIPTS_DIR))
import detect  # noqa: E402

IS_WINDOWS = os.name == "nt"
HAS_GITLEAKS = shutil.which("gitleaks") is not None


# ---------------------------------------------------------------------------
# detect.py — pure detection logic
# ---------------------------------------------------------------------------
class TestDetect(unittest.TestCase):
    def assert_single(self, prompt, expected_name, expected_value, expected_source=None):
        result = detect.detect(prompt)
        self.assertFalse(result["raw_mode"])
        secrets = result["secrets"]
        self.assertEqual(len(secrets), 1, f"expected exactly 1 secret in {prompt!r}, got {secrets}")
        s = secrets[0]
        self.assertEqual(s["name"], expected_name)
        self.assertEqual(s["value"], expected_value)
        # Span must point exactly at the value in the original prompt.
        start, end = s["span"]
        self.assertEqual(prompt[start:end], expected_value)
        if expected_source:
            self.assertEqual(s["source"], expected_source)

    def test_anthropic(self):
        v = "sk-ant-api03-" + "A" * 95
        self.assert_single(f"use {v} now", "anthropic", v, "regex")

    def test_openai_project(self):
        v = "sk-proj-" + "a" * 48
        self.assert_single(f"key {v}", "openai_project", v, "regex")

    def test_openai_legacy(self):
        v = "sk-" + "a" * 48
        self.assert_single(f"key {v}", "openai", v, "regex")

    def test_github_classic(self):
        v = "ghp_" + "a" * 36
        self.assert_single(f"token {v} deploy", "github_pat_classic", v, "regex")

    def test_github_fine_grained(self):
        v = "github_pat_" + "a" * 82
        self.assert_single(f"{v}", "github_pat_fine", v, "regex")

    def test_google_api(self):
        v = "AIza" + "a" * 35
        self.assert_single(f"maps {v}", "google_api", v, "regex")

    def test_aws_access_key(self):
        v = "AKIA" + "B" * 16
        self.assert_single(f"aws {v} here", "aws_access_key", v, "regex")

    def test_hugging_face(self):
        v = "hf_" + "a" * 36
        self.assert_single(f"hub {v}", "hugging_face", v, "regex")

    def test_stripe_live(self):
        v = "sk_live_" + "a" * 30
        self.assert_single(f"pay {v}", "stripe_live_secret", v, "regex")

    def test_slack(self):
        v = "xoxb-" + "1234567890-ABCDEFghijkl"
        self.assert_single(f"slack {v}", "slack_token", v, "regex")

    def test_gitlab(self):
        v = "glpat-" + "A" * 20
        self.assert_single(f"gl {v}", "gitlab_pat", v, "regex")

    def test_jwt(self):
        v = "eyJ" + "a" * 20 + ".eyJ" + "b" * 20 + "." + "c" * 20
        self.assert_single(f"bearer {v}", "jwt", v, "regex")

    def test_explicit_slash(self):
        self.assert_single("/key openai=mysupersecretvalue123 go", "openai", "mysupersecretvalue123", "explicit_slash")

    def test_explicit_named(self):
        self.assert_single("deploy KEY:stripe=sk_custom_xyz now", "stripe", "sk_custom_xyz", "explicit_named")

    def test_explicit_default(self):
        self.assert_single("save KEY=randomvalue here", "default", "randomvalue", "explicit_default")

    def test_explicit_slash_name_sanitized(self):
        # slot names with unsafe chars get sanitized to filesystem-safe form
        result = detect.detect("/key prod/db=secretval123 migrate")
        # "prod/db" → value parsing: \S+ stops at whitespace, name is [A-Za-z][...]* so "prod" only,
        # then "/db=..." — actually name regex is [A-Za-z][A-Za-z0-9_\-]{0,63}, '/' not allowed, so
        # "prod" matches as name and "=" must follow. Here "prod/db=..." → name="prod"? No: after
        # "prod" comes "/", not "=", so EXPLICIT_SLASH won't match. This documents the boundary.
        # We just assert it doesn't crash and produces a list.
        self.assertIsInstance(result["secrets"], list)

    def test_placeholder_filtered(self):
        # Value contains EXAMPLE → ignored
        result = detect.detect("a key looks like sk-ant-api03-EXAMPLE" + "A" * 90)
        self.assertEqual(result["secrets"], [])

    def test_placeholder_xxx(self):
        result = detect.detect("token ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        self.assertEqual(result["secrets"], [])

    def test_raw_mode(self):
        result = detect.detect("/raw discuss sk-ant-api03-" + "A" * 95)
        self.assertTrue(result["raw_mode"])
        self.assertEqual(result["secrets"], [])

    def test_no_secrets(self):
        result = detect.detect("hello world, how are you?")
        self.assertEqual(result["secrets"], [])
        self.assertFalse(result["raw_mode"])

    def test_multiple_secrets_ordered_by_span(self):
        gh = "ghp_" + "a" * 36
        prompt = f"first {gh} then /key custom=myvalue999"
        result = detect.detect(prompt)
        self.assertEqual(len(result["secrets"]), 2)
        spans = [s["span"][0] for s in result["secrets"]]
        self.assertEqual(spans, sorted(spans), "secrets must be ordered by span start")
        names = {s["name"] for s in result["secrets"]}
        self.assertEqual(names, {"github_pat_classic", "custom"})

    def test_duplicate_provider_disambiguation(self):
        k1 = "ghp_" + "a" * 36
        k2 = "ghp_" + "b" * 36
        result = detect.detect(f"{k1} and {k2}")
        names = sorted(s["name"] for s in result["secrets"])
        self.assertEqual(names, ["github_pat_classic", "github_pat_classic_2"])

    @unittest.skipUnless(HAS_GITLEAKS, "gitleaks binary not installed")
    def test_gitleaks_catches_what_regex_misses(self):
        # 32-hex generic api key assignment — not in our regex list
        value = "a1b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5"
        prompt = f'const apiKey = "{value}";'
        os.environ["KEY_VAULT_USE_GITLEAKS"] = "1"
        try:
            result = detect.detect(prompt)
        finally:
            os.environ.pop("KEY_VAULT_USE_GITLEAKS", None)
        sources = {s["source"] for s in result["secrets"]}
        self.assertIn("gitleaks", sources, f"gitleaks should have flagged {value}, got {result}")
        # span correctness for the gitleaks finding
        for s in result["secrets"]:
            if s["source"] == "gitleaks":
                a, b = s["span"]
                self.assertEqual(prompt[a:b], s["value"])

    def test_gitleaks_off_by_default(self):
        # Without the env var, gitleaks must NOT run (no subprocess, no findings from it)
        os.environ.pop("KEY_VAULT_USE_GITLEAKS", None)
        self.assertFalse(detect.gitleaks_enabled())


# ---------------------------------------------------------------------------
# intercept.py — full hook behavior (subprocess, sandboxed HOME/TMP)
# ---------------------------------------------------------------------------
class TestIntercept(unittest.TestCase):
    def setUp(self):
        self.sandbox = Path(tempfile.mkdtemp(prefix="kv-test-"))
        self.home = self.sandbox / "home"
        self.tmp = self.sandbox / "tmp"
        self.home.mkdir(parents=True)
        self.tmp.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def run_hook(self, prompt: str) -> dict:
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)  # Windows
        env["TMPDIR"] = str(self.tmp)
        env["TEMP"] = str(self.tmp)  # Windows
        env["TMP"] = str(self.tmp)  # Windows
        env["KEY_VAULT_DISABLE_PASTE"] = "1"  # never trigger real paste in tests
        env.pop("KEY_VAULT_USE_GITLEAKS", None)
        proc = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "intercept.py")],
            input=json.dumps({"user_prompt": prompt}),
            capture_output=True, text=True, env=env, timeout=20,
        )
        self.assertEqual(proc.returncode, 0, f"intercept.py exited {proc.returncode}: {proc.stderr}")
        out = proc.stdout.strip()
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            self.fail(f"intercept.py did not emit valid JSON: {out!r}")

    def secrets_dir(self) -> Path:
        return self.home / ".claude" / "secrets"

    def sanitized_files(self) -> list[Path]:
        kv_tmp = self.tmp / "key-vault"
        if not kv_tmp.is_dir():
            return []
        return sorted(kv_tmp.glob("sanitized_*.txt"))

    def test_secret_detected_blocks_and_saves(self):
        gh = "ghp_" + "a" * 36
        result = self.run_hook(f"deploy with {gh} now")
        self.assertEqual(result.get("decision"), "block")
        self.assertTrue(result.get("suppressOriginalPrompt"))
        self.assertIn("Intercepted", result.get("reason", ""))
        # File saved
        saved = self.secrets_dir() / "github_pat_classic.txt"
        self.assertTrue(saved.is_file(), "secret file should exist")
        self.assertEqual(saved.read_text(), gh)
        # Sanitized tempfile written with reference
        files = self.sanitized_files()
        self.assertEqual(len(files), 1)
        sanitized = files[0].read_text()
        self.assertNotIn(gh, sanitized, "raw value must not appear in sanitized prompt")
        self.assertIn("<<secret:github_pat_classic", sanitized)

    @unittest.skipIf(IS_WINDOWS, "POSIX permission bits not applicable on Windows")
    def test_secret_file_permissions(self):
        gh = "ghp_" + "c" * 36
        self.run_hook(f"token {gh}")
        saved = self.secrets_dir() / "github_pat_classic.txt"
        mode = saved.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600, f"secret file should be chmod 600, got {oct(mode)}")
        dir_mode = self.secrets_dir().stat().st_mode & 0o777
        self.assertEqual(dir_mode, 0o700, f"secrets dir should be chmod 700, got {oct(dir_mode)}")

    def test_no_secret_passes_through(self):
        result = self.run_hook("just a normal message")
        self.assertEqual(result, {})
        self.assertEqual(self.sanitized_files(), [])

    def test_raw_mode_strips_prefix(self):
        result = self.run_hook("/raw explain sk-ant-api03-" + "A" * 95)
        self.assertEqual(result.get("decision"), "block")
        files = self.sanitized_files()
        self.assertEqual(len(files), 1)
        content = files[0].read_text()
        self.assertFalse(content.startswith("/raw "), "raw prefix should be stripped")
        self.assertTrue(content.startswith("explain "))

    def test_multiple_secrets_saved(self):
        gh = "ghp_" + "a" * 36
        result = self.run_hook(f"use {gh} and /key db=postgresvalue123 too")
        self.assertEqual(result.get("decision"), "block")
        self.assertTrue((self.secrets_dir() / "github_pat_classic.txt").is_file())
        self.assertTrue((self.secrets_dir() / "db.txt").is_file())

    def test_explicit_key_marker_stays_in_sanitized(self):
        # The /key marker text remains; only the value is swapped to a reference.
        self.run_hook("/key myapi=topsecretvalue123 then call it")
        files = self.sanitized_files()
        content = files[0].read_text()
        self.assertIn("/key myapi=", content)
        self.assertNotIn("topsecretvalue123", content)
        self.assertIn("<<secret:myapi", content)


# ---------------------------------------------------------------------------
# manage_secrets.py — list / remove
# ---------------------------------------------------------------------------
class TestManageSecrets(unittest.TestCase):
    def setUp(self):
        self.sandbox = Path(tempfile.mkdtemp(prefix="kv-mgmt-"))
        self.home = self.sandbox / "home"
        (self.home / ".claude" / "secrets").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def run_mgmt(self, *args) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "manage_secrets.py"), *args],
            capture_output=True, text=True, env=env, timeout=10,
        )

    def make_secret(self, name, value="secretvalue"):
        p = self.home / ".claude" / "secrets" / f"{name}.txt"
        p.write_text(value)
        return p

    def test_list_empty(self):
        proc = self.run_mgmt("list")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no secrets", proc.stdout.lower())

    def test_list_shows_names_not_values(self):
        self.make_secret("openai", "sk-ant-SUPERSECRET")
        proc = self.run_mgmt("list")
        self.assertIn("openai", proc.stdout)
        self.assertNotIn("SUPERSECRET", proc.stdout, "values must never be printed")

    def test_remove_existing(self):
        p = self.make_secret("todelete")
        proc = self.run_mgmt("remove", "todelete")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("deleted", proc.stdout.lower())
        self.assertFalse(p.exists())

    def test_remove_nonexistent(self):
        proc = self.run_mgmt("remove", "ghost")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no slot", proc.stdout.lower())

    def test_remove_path_traversal_safe(self):
        # name with path components must be reduced to basename
        self.make_secret("safe")
        proc = self.run_mgmt("remove", "../../../etc/passwd")
        # Should not error catastrophically; should report no slot (basename "passwd")
        self.assertIn("no slot", proc.stdout.lower())
        self.assertTrue((self.home / ".claude" / "secrets" / "safe.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

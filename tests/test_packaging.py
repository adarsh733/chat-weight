#!/usr/bin/env python3
"""GATE for AG-012 (make it installable). Claude owns this file; AG MUST NOT edit it.

Run:  python tests/test_packaging.py

RED right now: none of README.md / LICENSE / install.py / the plugin manifest
exist yet. Antigravity turns these green without editing this file.

Contract these gates pin:

  ROOT/README.md           exists; leads with the value ("save"/"less"/"without"
                           needing to do anything) and shows an install command.
  ROOT/LICENSE             MIT ("Permission is hereby granted", "MIT").
  a plugin manifest        a plugin.json (at ROOT or ROOT/.claude-plugin/) that is
                           valid JSON with name == "token-diet".
  ROOT/install.py          resolves the target from os.path.expanduser("~") so it
                           can be sandboxed with HOME/USERPROFILE. Running it:
                             * writes <home>/.claude/settings.json (valid JSON),
                             * sets statusLine.command -> statusline.py,
                             * registers hooks for session_guard.py AND
                               savings_note.py,
                             * PRESERVES pre-existing unrelated settings keys,
                             * is IDEMPOTENT: run twice, no duplicated hook entry.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def find(*rels):
    for r in rels:
        p = os.path.join(ROOT, r)
        if os.path.exists(p):
            return p
    return None


class TestFilesPresent(unittest.TestCase):
    def test_readme_leads_with_usp(self):
        p = os.path.join(ROOT, "README.md")
        self.assertTrue(os.path.isfile(p), "a README.md is required to ship")
        head = open(p, encoding="utf-8").read()[:600].lower()
        self.assertRegex(head, r"sav|less|without",
                         "the README must open with the USP, not internals")
        full = open(p, encoding="utf-8").read().lower()
        self.assertIn("install", full, "the README must tell a stranger how to install it")

    def test_license_is_mit(self):
        p = find("LICENSE", "LICENSE.md", "LICENSE.txt")
        self.assertIsNotNone(p, "an MIT LICENSE file is required")
        body = open(p, encoding="utf-8").read()
        self.assertIn("MIT", body)
        self.assertIn("Permission is hereby granted", body)

    def test_manifest_valid(self):
        p = find("plugin.json", os.path.join(".claude-plugin", "plugin.json"))
        self.assertIsNotNone(p, "a plugin manifest (plugin.json) is required")
        data = json.load(open(p, encoding="utf-8"))
        self.assertEqual(data.get("name"), "token-diet")


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.installer = os.path.join(ROOT, "install.py")

    def _run_in(self, home):
        env = dict(os.environ)
        env["HOME"] = home
        env["USERPROFILE"] = home            # Windows expanduser reads this
        return subprocess.run([sys.executable, self.installer],
                              capture_output=True, text=True, env=env)

    def test_installer_exists(self):
        self.assertTrue(os.path.isfile(self.installer),
                        "install.py is the actual shipping blocker; it must exist")

    def test_wires_settings_and_preserves_existing(self):
        if not os.path.isfile(self.installer):
            self.skipTest("install.py not built yet")
        home = tempfile.mkdtemp(prefix="td-home-")
        os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
        settings = os.path.join(home, ".claude", "settings.json")
        with open(settings, "w", encoding="utf-8") as fh:
            json.dump({"model": "opus", "keepme": True}, fh)   # pre-existing keys

        self._run_in(home)
        data = json.load(open(settings, encoding="utf-8"))
        self.assertTrue(data.get("keepme"), "unrelated existing settings must be preserved")
        blob = json.dumps(data)
        self.assertIn("statusline.py", blob, "status line must be wired")
        self.assertIn("session_guard.py", blob, "the turn guard hook must be wired")
        self.assertIn("savings_note.py", blob, "the savings hook must be wired")

    def test_idempotent(self):
        if not os.path.isfile(self.installer):
            self.skipTest("install.py not built yet")
        home = tempfile.mkdtemp(prefix="td-home2-")
        self._run_in(home)
        self._run_in(home)                    # twice
        settings = os.path.join(home, ".claude", "settings.json")
        blob = json.dumps(json.load(open(settings, encoding="utf-8")))
        self.assertEqual(blob.count("savings_note.py"), 1,
                         "running the installer twice must not duplicate a hook")


if __name__ == "__main__":
    unittest.main(verbosity=2)

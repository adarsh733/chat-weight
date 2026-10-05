#!/usr/bin/env python3
"""What ships is what a stranger can use: no leftovers, nothing personal, nothing missing."""
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

PERSONAL = re.compile(r"adarsh|war-mode|war mode|health & medicine|adi20|antigravity|"
                      r"active-work|worklog|boot\.md|one-go|[a-z]:[\\/]users", re.I)


REPO = "github.com/adarsh733/token-diet"   # the project's own address is fine


def shipped():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in (".git", "__pycache__", ".pytest_cache")]
        for f in files:
            yield os.path.join(d, f)


class TestPackaging(unittest.TestCase):
    def test_no_leftover_files(self):
        bad = [p for p in shipped() if re.search(r"\.(bak|retired|tmp|orig)\b|\.bak-", p)]
        self.assertEqual(bad, [])

    def test_nothing_personal(self):
        hits = []
        for p in shipped():
            if os.path.basename(p) in ("LICENSE", "test_packaging.py"):
                continue
            with open(p, encoding="utf-8", errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    if PERSONAL.search(line.replace(REPO, "")):
                        hits.append("%s:%d: %s" % (os.path.relpath(p, ROOT), n, line.strip()[:80]))
        self.assertEqual(hits, [])

    def test_installer_wires_files_that_ship(self):
        for rel in ("scripts/statusline.py", "hooks/on_prompt.py", "reference/handoff.md", "config.json"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)
        src = open(os.path.join(ROOT, "install.py"), encoding="utf-8").read()
        self.assertIn('"scripts", "statusline.py"', src)
        self.assertIn('"hooks", "on_prompt.py"', src)

    def test_default_config_is_valid_json(self):
        cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        self.assertLess(cfg["wrap_up_pct"], cfg["fresh_chat_pct"])

    def test_every_command_in_the_docs_exists(self):
        for doc in ("README.md", "SKILL.md"):
            text = open(os.path.join(ROOT, doc), encoding="utf-8").read()
            for rel in re.findall(r"(?:scripts|hooks|reference)/[\w./-]+\.(?:py|md)", text):
                self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), "%s names %s" % (doc, rel))

    def test_audit_runs_with_no_history(self):
        env = dict(os.environ, HOME=ROOT + "-nohome", USERPROFILE=ROOT + "-nohome")
        res = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "audit.py")],
                             capture_output=True, env=env, cwd=ROOT)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(b"No chat logs found", res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

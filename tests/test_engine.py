#!/usr/bin/env python3
"""GATE for AG-011 (the engine). Claude owns this file; Antigravity MUST NOT edit it.

Run:  python -m pytest tests/test_engine.py -q      (pytest optional)
  or: python tests/test_engine.py                   (plain unittest)

These tests drive the REAL cli (scripts/diet.py) in a throwaway project, so they
test the seam, not an isolated function. They are RED right now: none of the
commands below exist yet. Antigravity's whole job is to turn them green WITHOUT
editing this file.

Contract these gates pin (build to this exactly):

  codemap    `diet.py codemap --root=DIR`
             writes DIR/.claude/CODE-MAP.md. For every source file (file_health
             source_exts, minus ignore dirs), one line PER top-level symbol
             giving the symbol NAME and its 1-based line number ON THE SAME LINE.

  dupes      `diet.py dupes --root=DIR`
             lists every assigned string literal of length >= 8 that appears as
             a right-hand-side value in >= 2 DISTINCT files. Prints the value and
             the files. A value in only one file, or a trivial/short value, is
             NOT listed.

  loadaudit  `diet.py loadaudit --root=DIR`
             sums the bytes of the configured startup_files ("loads before you
             type"), prints a total line containing "KB", and flags each startup
             file that is over its cap.

  movement   `diet.py movement --baseline=N --current=N`
             pure math, no logs: prints "better" when current < baseline,
             "worse" when current > baseline, "same" when equal. (Lower
             per-turn cost is better.) This pins the sign; Claude hand-checks the
             log-driven wiring in review.

  tidy       `diet.py tidy --root=DIR`            -> DRY RUN. Changes NOTHING.
             `diet.py tidy --apply --root=DIR`    -> executes Tier-0 ONLY.
             Tier-0 = trim finished items (lines matching "- [x]" or starting
             "OK ")  from files listed under efficiency.json "trackers".
             Rules the gates below enforce and you may not break:
               * dry run (no --apply) mutates no file and creates no archive.
               * --apply NEVER modifies a source file (Tier-2), even oversized.
               * --apply archives the ORIGINAL byte-for-byte under .claude/archive/
                 BEFORE trimming (never delete; always reversible).
               * --apply SKIPS any file named in the Active claims table of
                 .claude/ACTIVE-WORK.md.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

DIET = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "diet.py"))

DONE_LINE = "- [x] finished thing"      # a Tier-0 "done" item that tidy should trim
TODO_A = "- [ ] todo one"
TODO_B = "- [ ] todo two"


def run(*args, env_extra=None):
    env = dict(os.environ)
    # Isolate all skill state into the temp tree so a real machine is untouched.
    env.setdefault("TOKEN_DIET_STATE", tempfile.mkdtemp(prefix="td-state-"))
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, DIET, *args],
        capture_output=True, text=True, env=env)


def tree_hash(root):
    """A stable fingerprint of every file under root (path + content)."""
    h = hashlib.sha1()
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h.update(os.path.relpath(p, root).replace("\\", "/").encode())
            try:
                with open(p, "rb") as fh:
                    h.update(fh.read())
            except OSError:
                pass
    return h.hexdigest()


class Project:
    """A throwaway project dir with a helper to write files and config."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="td-proj-")
        os.makedirs(os.path.join(self.root, ".claude"), exist_ok=True)

    def write(self, rel, content):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        return p

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
            return fh.read()

    def config(self, obj):
        self.write(".claude/efficiency.json", json.dumps(obj))

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.addCleanup(self.p.cleanup)

    def rootarg(self):
        return "--root=%s" % self.p.root


# --------------------------------------------------------------------------- S5
class TestCodeMap(Base):
    def test_symbols_and_line_numbers(self):
        self.p.write("src/app.py",
                     "import os\n\n\ndef alpha():\n    return 1\n\n\nclass Beta:\n    pass\n")
        # alpha is line 4, Beta is line 8.
        r = run("codemap", self.rootarg())
        mapfile = os.path.join(self.p.root, ".claude", "CODE-MAP.md")
        self.assertTrue(os.path.isfile(mapfile),
                        "codemap must write .claude/CODE-MAP.md\n%s" % r.stderr)
        text = self.p.read(".claude/CODE-MAP.md")
        self.assertIn("src/app.py", text.replace("\\", "/"))
        self.assertRegex(text, r"alpha[^\n]*\b4\b",
                         "symbol 'alpha' and its line number 4 must share a line")
        self.assertRegex(text, r"Beta[^\n]*\b8\b",
                         "symbol 'Beta' and its line number 8 must share a line")


# --------------------------------------------------------------------------- S6a
class TestDupes(Base):
    def test_flags_repeated_value_only(self):
        shared = "https://example.com/api/v1"
        self.p.write("a.py", 'API_URL = "%s"\n' % shared)
        self.p.write("b.py", 'API_URL = "%s"\n' % shared)
        self.p.write("c.py", 'SOLO = "https://only.example.com/unique"\n')
        self.p.write("d.py", "COUNT = 1\n")
        out = run("dupes", self.rootarg()).stdout
        self.assertIn(shared, out, "the duplicated value must be reported")
        self.assertIn("a.py", out)
        self.assertIn("b.py", out)
        self.assertNotIn("only.example.com", out, "a value in one file is not a duplicate")
        # A trivial numeric literal must never be flagged as a duplicate constant.
        self.assertNotRegex(out, r"\bCOUNT\b")


# --------------------------------------------------------------------------- S6b
class TestLoadAudit(Base):
    def test_totals_and_flags_over_cap(self):
        self.p.write("BIG.md", "x" * 3072)                 # 3 KB
        self.p.config({"startup_files": [{"path": "BIG.md", "kb": 1}]})
        out = run("loadaudit", self.rootarg()).stdout
        self.assertIn("BIG.md", out)
        self.assertIn("KB", out, "must print a total footprint in KB")
        self.assertRegex(out.lower(), r"over|flag|too big|heavy",
                         "a startup file over its cap must be flagged")


# --------------------------------------------------------------------------- S7
class TestMovement(unittest.TestCase):
    def test_sign_is_correct(self):
        better = run("movement", "--baseline=300000", "--current=200000").stdout.lower()
        worse = run("movement", "--baseline=200000", "--current=300000").stdout.lower()
        same = run("movement", "--baseline=200000", "--current=200000").stdout.lower()
        self.assertIn("better", better, "lower current cost is better")
        self.assertIn("worse", worse)
        self.assertIn("same", same)


# --------------------------------------------------------------------------- S4
class TestTidySafety(Base):
    """The crown jewels. A file-touching feature that green-washes here is exactly
    the failure the whole framework exists to stop."""

    def _tracker(self):
        self.p.write("NOTES.md", "\n".join([DONE_LINE, TODO_A, TODO_B]) + "\n")
        self.p.config({"trackers": ["NOTES.md"]})

    def test_dry_run_changes_nothing(self):
        self._tracker()
        before = tree_hash(self.p.root)
        out = run("tidy", self.rootarg()).stdout            # no --apply
        # Non-vacuous: it must have SEEN the action (names the file) but not done it.
        self.assertIn("NOTES.md", out,
                      "a dry run must still report the action it would take")
        self.assertEqual(before, tree_hash(self.p.root),
                         "a dry run must not modify a single byte")
        self.assertFalse(os.path.isdir(os.path.join(self.p.root, ".claude", "archive")),
                         "a dry run must not create an archive")

    def test_apply_trims_done_but_keeps_todos(self):
        self._tracker()
        run("tidy", "--apply", self.rootarg())
        notes = self.p.read("NOTES.md")
        self.assertNotIn(DONE_LINE, notes, "finished item must be trimmed")
        self.assertIn(TODO_A, notes, "unfinished items must survive")
        self.assertIn(TODO_B, notes)

    def test_apply_archives_original_verbatim(self):
        self._tracker()
        run("tidy", "--apply", self.rootarg())
        adir = os.path.join(self.p.root, ".claude", "archive")
        self.assertTrue(os.path.isdir(adir), "the original must be archived before trimming")
        found = False
        for dp, _dn, fn in os.walk(adir):
            for f in fn:
                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                    if DONE_LINE in fh.read():
                        found = True
        self.assertTrue(found, "the archived copy must contain the original, unmodified content")

    def test_apply_never_touches_source_files(self):
        self._tracker()
        self.p.write("big.py", "".join("line_%d = %d\n" % (i, i) for i in range(900)))
        before = hashlib.sha1(self.p.read("big.py").encode()).hexdigest()
        run("tidy", "--apply", self.rootarg())
        after = hashlib.sha1(self.p.read("big.py").encode()).hexdigest()
        # Prove tidy actually ran (trimmed the tracker) so a no-op can't pass this.
        self.assertNotIn(DONE_LINE, self.p.read("NOTES.md"),
                         "tidy must have run its Tier-0 job in this scenario")
        self.assertEqual(before, after,
                         "a source file (Tier-2) must NEVER be auto-modified, even oversized")

    def test_apply_skips_claimed_files(self):
        # NOTES.md is claimed (must be skipped); FREE.md is not (proves tidy ran).
        self.p.write("NOTES.md", "\n".join([DONE_LINE, TODO_A]) + "\n")
        self.p.write("FREE.md", "\n".join([DONE_LINE, TODO_B]) + "\n")
        self.p.config({"trackers": ["NOTES.md", "FREE.md"]})
        self.p.write(".claude/ACTIVE-WORK.md",
                     "## Active claims\n\n| Claim ID | Started | Heartbeat | Files | Task |\n"
                     "|---|---|---|---|---|\n"
                     "| C-x | now | now | `NOTES.md` | someone else is editing it |\n")
        run("tidy", "--apply", self.rootarg())
        self.assertNotIn(DONE_LINE, self.p.read("FREE.md"),
                         "an unclaimed tracker must still be tidied (proves tidy ran)")
        self.assertIn(DONE_LINE, self.p.read("NOTES.md"),
                      "a file under an active claim must be skipped entirely")


if __name__ == "__main__":
    unittest.main(verbosity=2)

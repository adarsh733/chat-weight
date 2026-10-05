#!/usr/bin/env python3
"""The number, the bar, the model names, and the hook, against fake chat logs."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
HOOK = os.path.join(ROOT, "hooks", "on_prompt.py")
STATUS = os.path.join(ROOT, "scripts", "statusline.py")

import td_common  # noqa: E402

START = 20000          # what a fresh chat holds at its first reply
WIN = 200000


def reply(tokens, model="claude-haiku-4-5", sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "timestamp": "2026-10-01T10:00:00Z",
            "message": {"model": model, "usage": {"input_tokens": 10,
                        "cache_read_input_tokens": tokens - 10, "output_tokens": 50}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="td-engine-")
        self.home = os.path.join(self.tmp, "home")
        self.project = os.path.join(self.tmp, "project")
        os.makedirs(os.path.join(self.project, ".git"))
        os.makedirs(self.home)
        self.env = dict(os.environ, HOME=self.home, USERPROFILE=self.home,
                        CHAT_WEIGHT_STATE=os.path.join(self.tmp, "state"))
        os.environ["CHAT_WEIGHT_STATE"] = self.env["CHAT_WEIGHT_STATE"]
        self.cfg = td_common.load_config(self.project)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def chat(self, *entries, name="s1"):
        path = os.path.join(self.tmp, name + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
            for e in entries:
                fh.write(json.dumps(e) + "\n")
        return path

    def at(self, pct, model="claude-haiku-4-5"):
        """A reply at exactly `pct` chat weight: by default the fresh-chat point is
        4 x 30k = 120k of growth, which reads 60%, so 1% = 2,000 tokens."""
        return reply(START + pct * 2000, model)

    def hook(self, transcript, sid="s1", prompt="next"):
        data = {"session_id": sid, "transcript_path": transcript, "cwd": self.project, "prompt": prompt}
        res = subprocess.run([sys.executable, HOOK], input=json.dumps(data).encode("utf-8"),
                             capture_output=True, env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = res.stdout.decode("utf-8")
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


class TestNumber(Base):
    def test_fresh_chat_reads_zero(self):
        r = td_common.measure(self.chat(reply(START)), "s1", self.cfg)
        self.assertTrue(r["measured"])
        self.assertEqual(r["pct"], 0)

    def test_no_reply_yet_is_zero_not_unmeasured(self):
        r = td_common.measure(self.chat(), "s1", self.cfg)
        self.assertEqual((r["measured"], r["pct"]), (True, 0))

    def test_weight_is_growth_against_four_restart_costs(self):
        r = td_common.measure(self.chat(reply(START), reply(START + 120000, "claude-opus-5-5")), "s1", self.cfg)
        self.assertEqual((r["pct"], r["fresh_at"]), (60, 120000))

    def test_a_small_model_hits_its_memory_limit_first(self):
        # 200k memory, 70% cap = 140k, minus a 100k start = 40k of growth allowed
        r = td_common.measure(self.chat(reply(100000), reply(120000)), "s1", self.cfg)
        self.assertEqual((r["fresh_at"], r["pct"]), (40000, 30))

    def test_helper_agents_and_placeholder_models_are_ignored(self):
        r = td_common.measure(self.chat(reply(START), self.at(30), reply(190000, sidechain=True),
                                        dict(self.at(30), message=dict(self.at(30)["message"], model="<synthetic>"))),
                              "s1", self.cfg)
        self.assertEqual((r["pct"], r["model"]), (30, "claude-haiku-4-5"))

    def test_missing_log_is_unmeasured(self):
        self.assertFalse(td_common.measure(os.path.join(self.tmp, "nope.jsonl"), "x", self.cfg)["measured"])

    def test_an_interrupted_first_reply_is_zero_not_unreadable(self):
        stub = {"type": "assistant", "message": {"model": "<synthetic>",
                "usage": {"input_tokens": 0, "output_tokens": 0}}}
        r = td_common.measure(self.chat(stub), "s1", self.cfg)
        self.assertEqual((r["measured"], r["unreadable"], r["pct"]), (True, False, 0))

    def test_a_log_format_change_says_unreadable_instead_of_zero(self):
        new = {"type": "assistant", "message": {"model": "claude-opus-9",
               "tokenCounts": {"prompt": 90000, "completion": 50}}}
        r = td_common.measure(self.chat(new, new), "s1", self.cfg)
        self.assertEqual((r["measured"], r["unreadable"]), (False, True))

    def test_one_huge_tool_result_does_not_hide_the_last_reply(self):
        path = self.chat(reply(START), self.at(30))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "x" * 5000}}) + "\n")
        old = td_common.TAIL_BYTES
        td_common.TAIL_BYTES = 1000
        try:
            r = td_common.measure(path, "s1", self.cfg)
        finally:
            td_common.TAIL_BYTES = old
        self.assertEqual((r["measured"], r["pct"]), (True, 30))


class TestOldName(Base):
    def test_notes_and_settings_under_the_old_name_carry_over(self):
        old = os.path.join(self.home, ".claude", "token-diet")
        os.makedirs(os.path.join(old, "state"))
        with open(os.path.join(old, "config.json"), "w") as fh:
            json.dump({"fresh_chat_pct": 70}, fh)
        with open(os.path.join(old, "state", "restart-costs.json"), "w") as fh:
            json.dump({"samples": [1, 2, 3]}, fh)
        prev = os.environ.get("USERPROFILE"), os.environ.get("HOME")
        os.environ["USERPROFILE"] = os.environ["HOME"] = self.home
        try:
            cfg = td_common.load_config(self.project)
        finally:
            for k, v in zip(("USERPROFILE", "HOME"), prev):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        new = os.path.join(self.home, ".claude", "chat-weight")
        self.assertEqual(cfg["fresh_chat_pct"], 70)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isfile(os.path.join(new, "state", "restart-costs.json")))

    def test_a_project_file_under_the_old_name_still_works(self):
        os.makedirs(os.path.join(self.project, ".claude"))
        with open(os.path.join(self.project, ".claude", "token-diet.json"), "w") as fh:
            json.dump({"wrap_up_pct": 25}, fh)
        self.assertEqual(td_common.load_config(self.project)["wrap_up_pct"], 25)


class TestHousekeeping(Base):
    def test_old_chat_notes_are_deleted_once_a_day_and_shared_ones_kept(self):
        d = td_common.state_dir()
        now = time.time()
        for name, age in (("plan-old.json", 40), ("start-new.json", 2), ("restart-costs.json", 400)):
            p = os.path.join(d, name)
            td_common.write_json(p, {})
            os.utime(p, (now - age * 86400, now - age * 86400))
        td_common.prune_state(now)
        self.assertEqual(sorted(os.listdir(d)), ["pruned.json", "restart-costs.json", "start-new.json"])
        p = os.path.join(d, "plan-old2.json")
        td_common.write_json(p, {})
        os.utime(p, (now - 50 * 86400, now - 50 * 86400))
        td_common.prune_state(now + 3600)              # same day: nothing runs
        self.assertTrue(os.path.exists(p))


class TestWindow(Base):
    def test_table_by_longest_prefix(self):
        self.assertEqual(td_common.window_for(self.cfg, "a", "claude-opus-5-5"), 1000000)
        self.assertEqual(td_common.window_for(self.cfg, "a", "claude-haiku-4-5"), 200000)
        self.assertEqual(td_common.window_for(self.cfg, "a", "claude-new-9"), 200000)

    def test_the_size_claude_code_reports_wins(self):
        td_common.remember_window("b", 500000)
        self.assertEqual(td_common.window_for(self.cfg, "b", "claude-haiku-4-5"), 500000)

    def test_a_chat_bigger_than_the_table_says_is_never_over_100(self):
        self.assertEqual(td_common.window_for(self.cfg, "c", "claude-new-9", 350000), 1000000)

    def test_user_and_project_files_override_defaults(self):
        os.makedirs(os.path.join(self.home, ".claude", "chat-weight"))
        with open(os.path.join(self.home, ".claude", "chat-weight", "config.json"), "w") as fh:
            json.dump({"fresh_chat_pct": 70}, fh)
        os.makedirs(os.path.join(self.project, ".claude"))
        with open(os.path.join(self.project, ".claude", "chat-weight.json"), "w") as fh:
            json.dump({"wrap_up_pct": 30}, fh)
        old = os.environ.get("USERPROFILE"), os.environ.get("HOME")
        os.environ["USERPROFILE"] = os.environ["HOME"] = self.home
        try:
            cfg = td_common.load_config(self.project)
        finally:
            for k, v in zip(("USERPROFILE", "HOME"), old):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual((cfg["fresh_chat_pct"], cfg["wrap_up_pct"]), (70, 30))
        self.assertIn("claude-opus", cfg["context_windows"])       # defaults kept

    def test_models_newer_than_the_table_fall_under_their_family(self):
        for model, size in (("claude-opus-7", 1000000), ("claude-sonnet-6-1", 1000000),
                            ("claude-fable-6", 1000000), ("claude-opus-4-1-20250805", 200000),
                            ("claude-opus-4-8", 1000000), ("claude-haiku-5", 200000)):
            self.assertEqual(td_common.window_for(self.cfg, "f", model), size, model)

    def test_provider_spellings_of_a_model_id(self):
        self.assertEqual(td_common.model_id("us.anthropic.claude-sonnet-5-5-v1:0"), "claude-sonnet-5-5-v1:0")
        self.assertIsNone(td_common.model_id("<synthetic>"))
        r = td_common.measure(self.chat(reply(START), reply(START + 1000, "us.anthropic.claude-opus-6")), "p", self.cfg)
        self.assertEqual(r["model"], "claude-opus-6")


class TestLearning(Base):
    def resumed(self, name, edit_at):
        path = os.path.join(self.tmp, name + ".jsonl")
        edit = reply(edit_at)
        edit["message"]["content"] = [{"type": "tool_use", "name": "Edit", "input": {}}]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content":
                "Continuing: x\nNote: C:\\p\\.claude\\handoffs\\2026-10-01-x.md\nRead that note"}}) + "\n")
            for e in (reply(START), reply(START + 5000), edit, reply(edit_at + 9000)):
                fh.write(json.dumps(e) + "\n")
        return path

    def test_restart_cost_is_learned_from_fresh_chats_and_locked_per_chat(self):
        live = self.chat(reply(START), self.at(10), name="live")
        td_common.measure(live, "live", self.cfg)
        self.assertEqual(td_common.measure(live, "live", self.cfg)["fresh_at"], 120000)
        for i, cost in enumerate((20000, 24000, 22000)):
            td_common.measure(self.resumed("r%d" % i, START + cost), "r%d" % i, self.cfg)
        self.assertEqual(td_common.restart_cost(self.cfg), 22000)
        new = self.chat(reply(START), self.at(10), name="new2")
        self.assertEqual(td_common.measure(new, "new2", self.cfg)["fresh_at"], 88000)   # 4 x 22k
        self.assertEqual(td_common.measure(live, "live", self.cfg)["fresh_at"], 120000)  # locked

    def test_a_fresh_chat_is_counted_once_even_when_measured_twice(self):
        costs = os.path.join(td_common.state_dir(), "restart-costs.json")
        path = self.resumed("twice", START + 26000)
        td_common.measure(path, "twice", self.cfg)
        td_common.measure(path, "twice", self.cfg)
        self.assertEqual(td_common.read_json(costs)["samples"], [26000])
        # The race: a second reader has created the marker but not yet filled it in.
        open(td_common.state_file("learned", "race"), "w").close()
        td_common.learn_restart_cost(self.resumed("race", START + 9000), "race", START, self.cfg)
        self.assertEqual(td_common.read_json(costs)["samples"], [26000])

    def test_a_chat_with_no_early_edit_stops_being_scanned(self):
        old = td_common.HEAD_BYTES
        td_common.HEAD_BYTES = 500
        try:
            path = self.resumed("noedit", START + 1)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "user", "message": {"content":
                    "Note: C:/p/.claude/handoffs/2026-10-01-x.md"}}) + "\n")
                for _ in range(20):
                    fh.write(json.dumps(reply(START)) + "\n")
            td_common.learn_restart_cost(path, "noedit", START, self.cfg)
        finally:
            td_common.HEAD_BYTES = old
        self.assertEqual(td_common.read_json(td_common.state_file("learned", "noedit")), {"sample": None})

    def test_an_ordinary_chat_teaches_nothing(self):
        td_common.measure(self.chat(reply(START), self.at(10)), "plain", self.cfg)
        self.assertEqual(td_common.restart_cost(self.cfg), 30000)


class TestBar(Base):
    def test_colours_follow_the_two_lines(self):
        self.assertTrue(td_common.bar_line(10, self.cfg).startswith(td_common.GREEN))
        self.assertTrue(td_common.bar_line(45, self.cfg).startswith(td_common.YELLOW))
        self.assertTrue(td_common.bar_line(61, self.cfg).startswith(td_common.RED))

    def test_ten_squares_and_the_number(self):
        line = td_common.bar_line(23, self.cfg)
        squares = line.split("  ")[0]
        self.assertEqual(len(squares), 10)
        self.assertIn("***🟢 chat weight 23% — fresh chat at 60% — all good***", line)


class TestModels(Base):
    def test_claude_code_short_names_never_go_stale(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["models"]["checked"] = "2020-01-01"
        text = "\n".join(td_common.model_lines(cfg))
        self.assertIn("top = opus", text)
        self.assertNotIn("opus (or newer)", text)

    def test_other_tools_get_or_newer_when_the_list_is_old(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["models"]["tools"]["Other"] = {"top": "big-1", "middle": "mid-1", "small": "tiny-1"}
        cfg["models"]["checked"] = (date.today() - timedelta(days=200)).isoformat()
        self.assertIn("big-1 (or newer)", "\n".join(td_common.model_lines(cfg)))
        cfg["models"]["checked"] = date.today().isoformat()
        self.assertNotIn("(or newer)", "\n".join(td_common.model_lines(cfg)))


class TestHook(Base):
    def test_below_the_line_only_the_bar(self):
        text = self.hook(self.chat(reply(START), self.at(20)))
        self.assertIn("chat weight 20%", text)
        self.assertNotIn("HANDOFF", text)

    def test_first_message_shows_an_empty_bar(self):
        self.assertIn("chat weight 0%", self.hook(self.chat()))

    def test_past_the_line_asks_for_the_handoff_with_rules_and_models(self):
        text = self.hook(self.chat(reply(START), self.at(65)))
        self.assertIn("HANDOFF", text)
        self.assertIn("NEXT CHAT — SETUP", text)          # the rules file travels with it
        self.assertIn("Claude Code: top = opus", text)
        self.assertIn(os.path.join(self.project, ".claude", "handoffs"), text)

    def test_once_the_note_exists_only_a_reminder(self):
        t = self.chat(reply(START), self.at(65))
        self.assertIn("HANDOFF", self.hook(t))
        folder = os.path.join(self.project, ".claude", "handoffs")
        os.makedirs(folder)
        time.sleep(1.1)
        with open(os.path.join(folder, "2026-10-01-x.md"), "w") as fh:
            fh.write("note")
        text = self.hook(t)
        self.assertIn("handoff note is written", text)
        self.assertNotIn("--- rules ---", text)

    def test_full_request_once_then_one_short_nudge(self):
        t = self.chat(reply(START), self.at(65))
        first = self.hook(t)
        self.assertIn("just above the paste block", first)
        second = self.hook(t)
        self.assertIn("Still no handoff note", second)
        self.assertNotIn("--- rules ---", second)
        self.assertLess(len(second), 600)

    def test_project_additions_are_included(self):
        os.makedirs(os.path.join(self.project, ".claude"))
        with open(os.path.join(self.project, ".claude", "handoff-extra.md"), "w", encoding="utf-8") as fh:
            fh.write("Also release your file claims.")
        self.assertIn("Also release your file claims.", self.hook(self.chat(reply(START), self.at(65))))

    def test_a_sub_project_can_use_its_parents_notes_and_rules(self):
        parent = os.path.join(self.tmp, ".claude")
        os.makedirs(os.path.join(self.project, ".claude"))
        os.makedirs(parent)
        with open(os.path.join(self.project, ".claude", "chat-weight.json"), "w") as fh:
            json.dump({"handoff_folder": "../.claude/handoffs",
                       "handoff_extra": "../.claude/handoff-extra.md"}, fh)
        with open(os.path.join(parent, "handoff-extra.md"), "w", encoding="utf-8") as fh:
            fh.write("Parent rule.")
        text = self.hook(self.chat(reply(START), self.at(65)))
        self.assertIn(os.path.join(self.tmp, ".claude", "handoffs", ""), text)
        self.assertNotIn("..", text.split("Save the note as:")[1].splitlines()[1])
        self.assertIn("this project's additions ---\nParent rule.", text)

    def test_an_unreadable_log_is_said_once_then_silence(self):
        new = {"type": "assistant", "message": {"model": "claude-opus-9", "tokenCounts": {"prompt": 1}}}
        t = self.chat(new)
        self.assertIn("could not measure this chat", self.hook(t))
        self.assertEqual(self.hook(t), "")

    def test_garbage_in_is_silent_and_safe(self):
        res = subprocess.run([sys.executable, HOOK], input=b"not json", capture_output=True, env=self.env)
        self.assertEqual((res.returncode, res.stdout), (0, b""))


class TestStatusLine(Base):
    def test_draws_and_remembers_the_real_window(self):
        t = self.chat(reply(START), reply(START + 48000, "claude-new-9"))
        data = {"session_id": "sl", "transcript_path": t, "cwd": self.project,
                "context_window": {"context_window_size": 500000}}
        res = subprocess.run([sys.executable, STATUS], input=json.dumps(data).encode("utf-8"),
                             capture_output=True, env=self.env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("chat weight 24%", res.stdout.decode("utf-8"))   # 48k of 120k -> 24

    def test_says_paused_when_the_log_cannot_be_read(self):
        new = {"type": "assistant", "message": {"model": "claude-opus-9", "tokenCounts": {"prompt": 1}}}
        data = {"session_id": "sl2", "transcript_path": self.chat(new), "cwd": self.project}
        res = subprocess.run([sys.executable, STATUS], input=json.dumps(data).encode("utf-8"),
                             capture_output=True, env=self.env)
        self.assertIn("chat-weight paused", res.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

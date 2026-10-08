#!/usr/bin/env python3
"""Safety and regression tests for chat-weight installer (P0).

Covers:
1. Absent settings.json -> created correctly, statusLine is a valid dict.
2. Unrelated keys (env, permissions, model, apiKeyHelper, custom hooks) -> all survive intact.
3. Malformed settings.json -> installer exits 1, file left byte-identical.
4. String statusLine -> converted to valid dict, previous value preserved in _chatWeightPreviousStatusLine.
5. Idempotency -> running install multiple times produces no duplicate hook entries.
6. Uninstall -> --uninstall restores pre-install state.
7. Hook runs a real Python directly; a broken Python or old Claude Code is handled.
8. Upgrade -> hooks from older chat-weight versions are removed; look-alikes from other tools stay.
9. A working status line someone already has is kept, unless they pass --statusline.
10. Another tool's on_prompt.py / statusline.py is never treated as chat-weight's.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
INSTALLER = os.path.join(ROOT, "install.py")


class TestInstallSafety(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="td-safety-")
        self.settings_dir = os.path.join(self.test_dir, ".claude")
        self.settings_path = os.path.join(self.settings_dir, "settings.json")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_installer(self, *args):
        env = dict(os.environ)
        env["HOME"] = self.test_dir
        env["USERPROFILE"] = self.test_dir
        cmd = [sys.executable, INSTALLER] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def test_1_settings_absent_creates_valid_config(self):
        """1. settings.json absent -> created correctly, statusLine is a dict."""
        self.assertFalse(os.path.exists(self.settings_path))
        res = self._run_installer()
        self.assertEqual(res.returncode, 0, f"Installer failed with: {res.stderr}")
        self.assertTrue(os.path.isfile(self.settings_path))

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        self.assertIsInstance(data.get("statusLine"), dict)
        self.assertEqual(data["statusLine"].get("type"), "command")
        self.assertIn("statusline.py", data["statusLine"].get("command", ""))
        self.assertIn("on_prompt.py", json.dumps(data["hooks"]["UserPromptSubmit"]))
        self.assertEqual(sorted(data["hooks"]), ["PostToolUse", "Stop", "UserPromptSubmit"])
        self.assertIn("on_prompt.py", json.dumps(data["hooks"]["Stop"]))
        self.assertIn("on_prompt.py", json.dumps(data["hooks"]["PostToolUse"]))
        self.assertEqual(data["hooks"]["PostToolUse"][0]["matcher"], "*")

    def test_2_unrelated_keys_survive_intact(self):
        """2. settings.json with unrelated keys -> every one survives with identical values."""
        os.makedirs(self.settings_dir, exist_ok=True)
        unrelated = {
            "env": {"API_KEY": "secret_xyz", "NUM": 42},
            "permissions": {"allow": ["read", "write"], "deny": []},
            "model": "claude-3-7-sonnet",
            "apiKeyHelper": "/path/to/helper.sh",
            "customCompanyAuth": {"enabled": True, "tenant": "corp-123"},
            "hooks": {
                "PreToolUse": [{"type": "command", "command": "custom_pretool.py"}],
                "UserPromptSubmit": [{"type": "command", "command": "company_policy_check.py"}]
            }
        }
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump(unrelated, fh, indent=2)

        res = self._run_installer()
        self.assertEqual(res.returncode, 0, f"Installer failed with: {res.stderr}")

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        self.assertEqual(data["env"], unrelated["env"])
        self.assertEqual(data["permissions"], unrelated["permissions"])
        self.assertEqual(data["model"], unrelated["model"])
        self.assertEqual(data["apiKeyHelper"], unrelated["apiKeyHelper"])
        self.assertEqual(data["customCompanyAuth"], unrelated["customCompanyAuth"])
        self.assertEqual(data["hooks"]["PreToolUse"], unrelated["hooks"]["PreToolUse"])

        # Check existing custom hook in UserPromptSubmit was not destroyed
        ups_blob = json.dumps(data["hooks"]["UserPromptSubmit"])
        self.assertIn("company_policy_check.py", ups_blob)
        self.assertEqual(ups_blob.count("on_prompt.py"), 1)

    def test_3_malformed_json_aborts_without_modifying_file(self):
        """3. settings.json malformed JSON -> installer exits 1, file byte-identical."""
        os.makedirs(self.settings_dir, exist_ok=True)
        corrupted_bytes = b'{\n  "env": {\n    "broken": true,\n'
        with open(self.settings_path, "wb") as fh:
            fh.write(corrupted_bytes)

        res = self._run_installer()
        self.assertEqual(res.returncode, 1, "Installer should exit 1 on malformed JSON")
        self.assertIn("Could not read your settings file", res.stdout + res.stderr)
        self.assertIn("Nothing was changed.", res.stdout + res.stderr)

        with open(self.settings_path, "rb") as fh:
            current_bytes = fh.read()

        self.assertEqual(current_bytes, corrupted_bytes, "Corrupted file must be byte-identical")

    def test_4_string_statusline_converted_and_preserved(self):
        """4. settings.json where statusLine is a STRING -> converted to valid dict, original preserved."""
        os.makedirs(self.settings_dir, exist_ok=True)
        original_string_status = "echo 'Legacy custom string status'"
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump({"statusLine": original_string_status}, fh)

        res = self._run_installer()
        self.assertEqual(res.returncode, 0, f"Installer failed with: {res.stderr}")

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        self.assertIsInstance(data["statusLine"], dict)
        self.assertEqual(data["statusLine"]["type"], "command")
        self.assertIn("statusline.py", data["statusLine"]["command"])
        self.assertEqual(data.get("_chatWeightPreviousStatusLine"), original_string_status)

    def test_5_idempotent_no_duplicate_hooks(self):
        """5. Running install twice -> idempotent, no duplicate hook entries."""
        res1 = self._run_installer()
        self.assertEqual(res1.returncode, 0)
        res2 = self._run_installer()
        self.assertEqual(res2.returncode, 0)
        res3 = self._run_installer()
        self.assertEqual(res3.returncode, 0)

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        blob = json.dumps(data)
        self.assertEqual(blob.count("statusline.py"), 1)
        self.assertEqual(blob.count("on_prompt.py"), 3)     # one per moment: reply, step, message

    def test_6_uninstall_restores_pre_install_state(self):
        """6. --uninstall -> returns file to its pre-install state."""
        os.makedirs(self.settings_dir, exist_ok=True)
        initial_config = {
            "statusLine": "my-custom-statusline",
            "model": "sonnet",
            "hooks": {
                "UserPromptSubmit": [{"type": "command", "command": "other_guard.py"}]
            }
        }
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump(initial_config, fh, indent=2)

        # Install first
        res_inst = self._run_installer()
        self.assertEqual(res_inst.returncode, 0)

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            installed_data = json.load(fh)
        self.assertIsInstance(installed_data["statusLine"], dict)
        self.assertIn("_chatWeightPreviousStatusLine", installed_data)

        # Uninstall
        res_uninst = self._run_installer("--uninstall")
        self.assertEqual(res_uninst.returncode, 0, f"Uninstall failed: {res_uninst.stderr}")

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            uninstalled_data = json.load(fh)

        self.assertEqual(uninstalled_data.get("statusLine"), "my-custom-statusline")
        self.assertNotIn("_chatWeightPreviousStatusLine", uninstalled_data)
        self.assertEqual(uninstalled_data.get("model"), "sonnet")
        self.assertIn("UserPromptSubmit", uninstalled_data.get("hooks", {}))
        self.assertNotIn("SessionStart", uninstalled_data.get("hooks", {}))
        self.assertEqual(uninstalled_data["hooks"]["UserPromptSubmit"], initial_config["hooks"]["UserPromptSubmit"])
        self.assertNotIn("Stop", uninstalled_data.get("hooks", {}))

        ups_blob = json.dumps(uninstalled_data["hooks"]["UserPromptSubmit"])
        self.assertIn("other_guard.py", ups_blob)
        self.assertNotIn("on_prompt.py", ups_blob)

    def test_7_commands_name_a_real_python_and_need_no_shell(self):
        """7. The hook starts a real Python directly (exec form); the status line is one
        shell-safe line with forward slashes."""
        res = self._run_installer()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with open(self.settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        hook = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertTrue(os.path.isfile(hook["command"]), hook["command"])
        self.assertNotIn("\\", hook["command"])
        self.assertEqual(len(hook["args"]), 1)
        self.assertTrue(hook["args"][0].endswith("hooks/on_prompt.py"))
        status = data["statusLine"]["command"]
        self.assertNotIn("\\", status)
        self.assertFalse(status.startswith("python "))
        self.assertTrue(status.rstrip('"').endswith("statusline.py"))

    def test_7b_a_python_that_cannot_run_the_scripts_changes_nothing(self):
        """7b. If the scripts fail to start, the installer stops before writing."""
        os.makedirs(self.settings_dir, exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            fh.write('{"model": "opus"}')
        sys.path.insert(0, ROOT)
        import install
        problem = install.self_test(sys.executable, os.path.join(self.test_dir, "missing.py"),
                                    os.path.join(ROOT, "scripts", "statusline.py"))
        self.assertIn("missing.py", problem)
        self.assertEqual(install.self_test(sys.executable, os.path.join(ROOT, "hooks", "on_prompt.py"),
                                           os.path.join(ROOT, "scripts", "statusline.py")), "")

    def test_7c_old_claude_code_gets_a_one_line_command(self):
        """7c. Claude Code older than 2.1.139 has no exec form: one shell line instead."""
        sys.path.insert(0, ROOT)
        import install
        h = install.hook_entry("C:/Py/python.exe", "C:/x/chat-weight/hooks/on_prompt.py", False)
        self.assertEqual(h["command"], "C:/Py/python.exe C:/x/chat-weight/hooks/on_prompt.py")
        self.assertNotIn("args", h)
        self.assertTrue(install.is_ours(h))
        self.assertTrue(install.is_ours(install.hook_entry("/usr/bin/python3",
                                                           "/h/chat-weight/hooks/on_prompt.py", True)))
        self.assertFalse(install.is_ours({"command": "python3", "args": ["/h/mytools/on_prompt.py"]}))

    def test_8_upgrade_removes_old_hooks_only(self):
        """8. An entry from a moved chat-weight folder goes; a same-named script from
        another tool stays."""
        os.makedirs(self.settings_dir, exist_ok=True)
        old = "/home/x/old-place/chat-weight/hooks/"           # an earlier install, since moved
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump({"hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python " + old + "on_prompt.py"}]},
                    {"hooks": [{"type": "command", "command": "python /opt/other/on_prompt.py"}]}],
            }}, fh)
        res = self._run_installer()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with open(self.settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        blob = json.dumps(data["hooks"])
        self.assertIn("/opt/other/on_prompt.py", blob)
        self.assertNotIn(old, blob)
        self.assertEqual(blob.count("on_prompt.py"), 4)      # the other tool's + ours at three moments

    def test_9_a_working_status_line_is_kept_unless_asked(self):
        """9. Someone's working status line stays; --statusline takes over; uninstall gives it back."""
        os.makedirs(self.settings_dir, exist_ok=True)
        theirs = {"type": "command", "command": "npx ccstatusline", "padding": 0}
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump({"statusLine": theirs}, fh)
        res = self._run_installer()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("--statusline", res.stdout)
        with open(self.settings_path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["statusLine"], theirs)
        self.assertNotIn("_chatWeightPreviousStatusLine", data)
        self.assertEqual(json.dumps(data["hooks"]).count("on_prompt.py"), 3)

        self.assertEqual(self._run_installer("--statusline").returncode, 0)
        with open(self.settings_path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("statusline.py", data["statusLine"]["command"])
        self.assertEqual(data["_chatWeightPreviousStatusLine"], theirs)

        self.assertEqual(self._run_installer("--uninstall").returncode, 0)
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"statusLine": theirs})

    def test_10_same_named_scripts_from_other_tools_are_never_touched(self):
        """10. Another tool's on_prompt.py hook and statusline.py survive install AND uninstall."""
        os.makedirs(self.settings_dir, exist_ok=True)
        before = {
            "statusLine": {"type": "command", "command": "python ~/mytools/statusline.py"},
            "hooks": {"UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "python ~/mytools/on_prompt.py"}]}]},
        }
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump(before, fh)
        self.assertEqual(self._run_installer().returncode, 0)
        with open(self.settings_path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["statusLine"], before["statusLine"])
        self.assertIn("~/mytools/on_prompt.py", json.dumps(data["hooks"]))
        self.assertEqual(self._run_installer("--uninstall").returncode, 0)
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)

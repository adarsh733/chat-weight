#!/usr/bin/env python3
"""Safety and regression tests for token-diet installer (P0).

Covers:
1. Absent settings.json -> created correctly, statusLine is a valid dict.
2. Unrelated keys (env, permissions, model, apiKeyHelper, custom hooks) -> all survive intact.
3. Malformed settings.json -> installer exits 1, file left byte-identical.
4. String statusLine -> converted to valid dict, previous value preserved in _tokenDietPreviousStatusLine.
5. Idempotency -> running install multiple times produces no duplicate hook entries.
6. Uninstall -> --uninstall restores pre-install state.
7. Generated commands -> contain sys.executable, not bare python.
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
        self.assertIn("hooks", data)
        self.assertIn("UserPromptSubmit", data["hooks"])
        self.assertIn("SessionStart", data["hooks"])
        self.assertIn("Stop", data["hooks"])

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
        self.assertIn("session_guard.py", ups_blob)

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
        self.assertEqual(data.get("_tokenDietPreviousStatusLine"), original_string_status)

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
        self.assertEqual(blob.count("session_guard.py"), 1)
        self.assertEqual(blob.count("savings_note.py"), 1)
        self.assertEqual(blob.count("usage_meter.py"), 1)

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
        self.assertIn("_tokenDietPreviousStatusLine", installed_data)

        # Uninstall
        res_uninst = self._run_installer("--uninstall")
        self.assertEqual(res_uninst.returncode, 0, f"Uninstall failed: {res_uninst.stderr}")

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            uninstalled_data = json.load(fh)

        self.assertEqual(uninstalled_data.get("statusLine"), "my-custom-statusline")
        self.assertNotIn("_tokenDietPreviousStatusLine", uninstalled_data)
        self.assertEqual(uninstalled_data.get("model"), "sonnet")
        self.assertIn("UserPromptSubmit", uninstalled_data.get("hooks", {}))
        self.assertNotIn("SessionStart", uninstalled_data.get("hooks", {}))
        self.assertNotIn("Stop", uninstalled_data.get("hooks", {}))

        ups_blob = json.dumps(uninstalled_data["hooks"]["UserPromptSubmit"])
        self.assertIn("other_guard.py", ups_blob)
        self.assertNotIn("session_guard.py", ups_blob)

    def test_7_generated_commands_contain_sys_executable(self):
        """7. Generated commands contain sys.executable, not bare python."""
        res = self._run_installer()
        self.assertEqual(res.returncode, 0)

        with open(self.settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        py_exe = sys.executable
        self.assertIn(py_exe, data["statusLine"]["command"])

        blob = json.dumps(data["hooks"])
        self.assertIn("session_guard.py", blob)
        self.assertIn("savings_note.py", blob)
        self.assertIn("usage_meter.py", blob)

        for event in ("UserPromptSubmit", "SessionStart", "Stop"):
            for item in data["hooks"][event]:
                if isinstance(item, dict):
                    if "hooks" in item:
                        for h in item["hooks"]:
                            self.assertIn(py_exe, h.get("command", ""))
                            self.assertFalse(h.get("command", "").startswith("python "))
                    elif "command" in item:
                        self.assertIn(py_exe, item.get("command", ""))
                        self.assertFalse(item.get("command", "").startswith("python "))


if __name__ == "__main__":
    unittest.main(verbosity=2)

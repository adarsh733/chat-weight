#!/usr/bin/env python3
"""Tells the user when a newer chat-weight is out. Never updates by itself.

Once a day the prompt hook starts this script in the background (--fetch), so the
chat never waits on the network. It reads one small file, VERSION, from the
project's GitHub page and writes the answer to ~/.claude/chat-weight/state/update.json.
The hook reads that answer and, when a newer version exists, asks Claude to mention
it once per chat. The user then says "update chat-weight" and Claude runs --apply.

Nothing about the user is sent: it is a plain download of one public file, like
opening a web page (GitHub sees an ordinary visit, as with any website).
Updating only on the user's say-so is deliberate: if the GitHub account were ever
taken over, silent updates would put bad code on every machine unnoticed.

  python updates.py --fetch    check now (what the hook runs in the background)
  python updates.py --status   print what is installed and what is out
  python updates.py --apply    update this folder (git pull) and re-run install.py

Releasing: raise the number in VERSION in the same commit, or nobody hears about it.
"""
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import td_common  # noqa: E402

DEFAULT_URL = "https://raw.githubusercontent.com/adarsh733/chat-weight/main/VERSION"
CHECK_EVERY = 86400         # seconds: once a day
TIMEOUT = 5


def state_path():
    return os.path.join(td_common.state_dir(), "update.json")


def installed():
    try:
        with io.open(os.path.join(SKILL, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""


def parse(v):
    """'2.1.0' -> (2, 1, 0); anything that is not a plain version -> None."""
    v = str(v or "").strip().lstrip("v")
    if not re.fullmatch(r"\d+(\.\d+){0,3}", v):
        return None
    parts = [int(x) for x in v.split(".")]
    return tuple(parts + [0] * (4 - len(parts)))


def is_newer(latest, current):
    a, b = parse(latest), parse(current)
    return bool(a and b and a > b)


def url(cfg):
    return os.environ.get("CHAT_WEIGHT_UPDATE_URL") or cfg.get("update_url") or DEFAULT_URL


def fetch(cfg=None):
    """Download VERSION and save it. Returns the version, or None (and keeps the old answer)."""
    from urllib.request import urlopen
    cfg = cfg or td_common.load_config()
    try:
        with urlopen(url(cfg), timeout=TIMEOUT) as res:
            latest = res.read(64).decode("utf-8", "replace").strip()
    except Exception:
        return None
    if not parse(latest):
        return None
    old = td_common.read_json(state_path()) or {}
    old.update({"latest": latest, "fetched_at": time.time()})
    td_common.write_json(state_path(), old)
    return latest


def _start_background_fetch():
    args = [sys.executable, os.path.abspath(__file__), "--fetch"]
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000 | 0x00000200   # no window, own process group
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)


def notice(cfg, now=None, start=_start_background_fetch):
    """Called by the hook on every message. Never waits on the network.

    Starts a background check if the last one is a day old, and returns
    (installed, latest) when a newer version is already known, else None."""
    if not cfg.get("check_for_updates", True):
        return None
    now = now or time.time()
    st = td_common.read_json(state_path()) or {}
    if now - float(st.get("started_at") or 0) >= CHECK_EVERY:
        st["started_at"] = now          # written first, so parallel chats start one check, not many
        td_common.write_json(state_path(), st)
        try:
            start()
        except Exception:
            pass
    have, latest = installed(), st.get("latest")
    return (have, latest) if is_newer(latest, have) else None


def _run(cmd):
    print("$ " + " ".join(cmd))
    res = subprocess.run(cmd, cwd=SKILL, capture_output=True, text=True)
    out = (res.stdout + res.stderr).strip()
    if out:
        print(out)
    return res.returncode


def apply():
    """Update this folder and re-run the installer. Prints what happened, in plain words."""
    before = installed()
    if not os.path.isdir(os.path.join(SKILL, ".git")):
        print("This copy of chat-weight was not installed with git, so it cannot update itself.")
        print("Download it again from https://github.com/adarsh733/chat-weight and run install.py.")
        return 1
    if _run(["git", "pull", "--ff-only"]) != 0:
        print("Not updated: git could not bring this folder up to date (often because files in it")
        print("were changed by hand). Nothing was changed. Your current version keeps working.")
        return 1
    if _run([sys.executable, os.path.join(SKILL, "install.py")]) != 0:
        print("The files updated, but install.py did not finish. Run it again by hand.")
        return 1
    st = td_common.read_json(state_path()) or {}
    st["latest"] = installed()
    td_common.write_json(state_path(), st)
    print("chat-weight updated: %s -> %s. Open a new chat to use the new version."
          % (before or "?", installed() or "?"))
    return 0


def main(argv):
    if "--fetch" in argv:
        fetch()
        return 0
    if "--apply" in argv:
        return apply()
    latest = fetch() or (td_common.read_json(state_path()) or {}).get("latest")
    have = installed()
    print("installed: %s   newest: %s" % (have or "?", latest or "could not check"))
    if not latest:
        print("Could not reach GitHub, so it is not known whether a newer version is out.")
    else:
        print("An update is available." if is_newer(latest, have) else "Up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

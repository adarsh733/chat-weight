#!/usr/bin/env python3
"""Make dist/chat-weight.zip, the file to upload when adding chat-weight to normal chats.

The zip holds one folder, chat-weight/, with SKILL.md at its top. Tests, git files and
caches are left out: a chat has no use for them.
"""
import os
import sys
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "tests", "dist"}
SKIP_FILES = {".gitignore"}


def files():
    for d, dirs, names in os.walk(ROOT):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for n in sorted(names):
            if n not in SKIP_FILES and not n.endswith(".pyc"):
                yield os.path.join(d, n)


def main():
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "chat-weight.zip")
    tmp = out + ".part"
    count = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files():
            z.write(p, os.path.join("chat-weight", os.path.relpath(p, ROOT)).replace(os.sep, "/"))
            count += 1
    with zipfile.ZipFile(tmp) as z:
        if "chat-weight/SKILL.md" not in z.namelist():
            os.remove(tmp)
            print("Something went wrong: SKILL.md is missing from the zip. Nothing was changed.")
            return 1
    os.replace(tmp, out)
    print("Made %s (%d files)." % (out, count))
    print("Upload it where skills are added in the Claude app's settings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

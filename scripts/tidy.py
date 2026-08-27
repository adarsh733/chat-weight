#!/usr/bin/env python3
"""token-diet tidy - Tier-0 cleanup of finished items in opt-in trackers."""
import datetime
import fnmatch
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td_common


def _active_claimed_files(root):
    p = os.path.join(root, ".claude", "ACTIVE-WORK.md")
    if not os.path.isfile(p):
        return set()
    claimed = set()
    in_active = False
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line_str = line.strip()
                if line_str.startswith("## Active claims"):
                    in_active = True
                    continue
                if in_active:
                    if line_str.startswith("## ") and not line_str.startswith("## Active claims"):
                        break
                    if line_str.startswith("|") and not line_str.startswith("|---") and "Claim ID" not in line_str:
                        cols = [c.strip() for c in line_str.split("|")]
                        if len(cols) >= 6:
                            files_col = cols[4]
                            if files_col and files_col != "*(none)*":
                                backtick_items = re.findall(r'`([^`]+)`', files_col)
                                items = backtick_items if backtick_items else [x.strip() for x in files_col.split(",") if x.strip()]
                                for item in items:
                                    for part in item.split(","):
                                        c_path = part.strip().strip("`").strip()
                                        if c_path and c_path != "*(none)*":
                                            claimed.add(os.path.normpath(c_path).replace("\\", "/"))
                                            claimed.add(os.path.basename(c_path))
    except Exception:
        pass
    return claimed


def _is_claimed(path, claimed_set):
    norm_p = os.path.normpath(path).replace("\\", "/")
    base_p = os.path.basename(path)
    for c in claimed_set:
        if c == norm_p or c == base_p or c == path:
            return True
        if "*" in c and (fnmatch.fnmatch(norm_p, c) or fnmatch.fnmatch(base_p, c)):
            return True
    return False


def _is_finished_line(line):
    s = line.strip()
    if re.search(r'-\s*\[[xX]\]', line):
        return True
    if s.startswith("OK ") or s == "OK":
        return True
    return False


def cmd_tidy(root, scope, cfg_fn=None):
    """Tier-0 cleanup: trim finished items from trackers (opt-in; archive original before trim)."""
    apply_changes = "--apply" in sys.argv
    if cfg_fn is not None:
        c = cfg_fn(root)
    else:
        import diet
        c = diet.cfg(root)
    trackers = c.get("trackers") or []
    fh_cfg = c.get("file_health", {})
    source_exts = set(fh_cfg.get("source_exts", [".js", ".ts", ".jsx", ".tsx", ".py", ".css", ".go", ".rb", ".java"]))
    
    print("")
    mode_str = "APPLY" if apply_changes else "DRY RUN"
    print("  TIDY (%s) - Tier-0 finished items" % mode_str)
    print("  " + "=" * 60)
    
    if not trackers:
        print("  No tracker files configured under efficiency.json \"trackers\".")
        print("")
        return
    
    claimed = _active_claimed_files(root)
    total_trimmed = 0
    
    for t_rel in trackers:
        t_full = os.path.join(root, t_rel)
        if not os.path.isfile(t_full):
            print("  missing   %s" % t_rel)
            continue
        
        # Rule: Never modify a source file
        ext = os.path.splitext(t_rel)[1].lower()
        if ext in source_exts:
            print("  [SKIP] %s is a source file (Tier-2). Never auto-modified by tidy." % t_rel)
            continue
        
        # Rule: Skip active claims
        if _is_claimed(t_rel, claimed):
            print("  [SKIP] %s is claimed in .claude/ACTIVE-WORK.md" % t_rel)
            continue
        
        try:
            with open(t_full, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except Exception as e:
            print("  error reading %s: %s" % (t_rel, e))
            continue
        
        surviving = [l for l in lines if not _is_finished_line(l)]
        trimmed_count = len(lines) - len(surviving)
        
        if trimmed_count == 0:
            print("  ok        %s (nothing to trim)" % t_rel)
            continue
        
        total_trimmed += trimmed_count
        
        if not apply_changes:
            print("  [DRY RUN] Would trim %d finished item(s) from %s" % (trimmed_count, t_rel))
        else:
            # Archive original byte-for-byte first
            archive_dir = os.path.join(root, ".claude", "archive")
            os.makedirs(archive_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            stem, fext = os.path.splitext(os.path.basename(t_rel))
            arch_name = "%s-%s%s" % (stem, ts, fext)
            arch_path = os.path.join(archive_dir, arch_name)
            try:
                with open(t_full, "rb") as rf:
                    orig_bytes = rf.read()
                with open(arch_path, "wb") as wf:
                    wf.write(orig_bytes)
                with open(t_full, "w", encoding="utf-8", newline="\n") as wf:
                    wf.writelines(surviving)
                print("  [TRIMMED] %d finished item(s) from %s (archived to %s)" % (trimmed_count, t_rel, arch_name))
            except Exception as e:
                print("  error trimming %s: %s" % (t_rel, e))
    
    print("")
    if not apply_changes:
        print("  Dry run complete. Pass --apply to execute trims and archive originals.")
    else:
        print("  Tidy complete. %d item(s) trimmed across trackers." % total_trimmed)
    print("")

#!/usr/bin/env python3
"""token-diet codemap and dupes - symbol indexing and duplicated constant detection."""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td_common


def _find_top_level_symbols(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    symbols = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, start=1):
                if ext == ".py":
                    m = re.match(r'^(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
                    m = re.match(r'^class\s+([a-zA-Z0-9_]+)\b', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
                elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
                    m = re.match(r'^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([a-zA-Z0-9_]+)\s*\(', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
                    m = re.match(r'^(?:export\s+(?:default\s+)?)?class\s+([a-zA-Z0-9_]+)\b', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
                    m = re.match(r'^(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
                elif ext == ".go":
                    m = re.match(r'^func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)\s*\(', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
                    m = re.match(r'^type\s+([a-zA-Z0-9_]+)\s+', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
                elif ext == ".rb":
                    m = re.match(r'^(?:def|class|module)\s+([a-zA-Z0-9_]+)', line)
                    if m:
                        symbols.append((m.group(1), lineno))
                        continue
    except Exception:
        pass
    return symbols


def cmd_codemap(root, scope, cfg_fn=None, walk_fn=None):
    """Write .claude/CODE-MAP.md mapping source files to top-level symbols and line numbers."""
    if cfg_fn is not None and walk_fn is not None:
        c = cfg_fn(root)
        walker = walk_fn(root, c)
    else:
        import diet
        c = diet.cfg(root)
        walker = diet._walk(root, c)
    
    fh = c.get("file_health", {})
    exts = set(fh.get("source_exts", [".js", ".ts", ".jsx", ".tsx", ".py", ".css", ".go", ".rb", ".java"]))
    
    claude_dir = os.path.join(root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    mapfile = os.path.join(claude_dir, "CODE-MAP.md")
    
    lines = ["# Code Map", "", "Top-level symbols and line numbers by source file.", ""]
    total_symbols = 0
    files_count = 0
    
    source_files = []
    for p in walker:
        if os.path.splitext(p)[1].lower() in exts:
            source_files.append(p)
    source_files.sort()
    
    for p in source_files:
        rel = os.path.relpath(p, root).replace("\\", "/")
        syms = _find_top_level_symbols(p)
        if syms:
            files_count += 1
            total_symbols += len(syms)
            lines.append("## %s" % rel)
            for name, lineno in syms:
                lines.append("- %s: line %d" % (name, lineno))
            lines.append("")
    
    with open(mapfile, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    
    print("  Wrote %s (%d symbols across %d files)" % (mapfile, total_symbols, files_count))


def _find_assigned_strings(filepath):
    results = []
    pat = re.compile(r'(?:=|\:)\s*(?:[fFrRbBuU]{1,2})?(["\'])(.*?)\1')
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                for m in pat.finditer(line):
                    val = m.group(2)
                    if len(val) >= 8:
                        results.append(val)
    except Exception:
        pass
    return results


def cmd_dupes(root, scope, cfg_fn=None, walk_fn=None):
    """List duplicate string constants (len >= 8) assigned in >= 2 distinct files."""
    if cfg_fn is not None and walk_fn is not None:
        c = cfg_fn(root)
        walker = walk_fn(root, c)
    else:
        import diet
        c = diet.cfg(root)
        walker = diet._walk(root, c)
    
    fh = c.get("file_health", {})
    exts = set(fh.get("source_exts", [".js", ".ts", ".jsx", ".tsx", ".py", ".css", ".go", ".rb", ".java"]))
    
    val_to_files = collections.defaultdict(set)
    for p in walker:
        if os.path.splitext(p)[1].lower() in exts:
            rel = os.path.relpath(p, root).replace("\\", "/")
            for val in _find_assigned_strings(p):
                val_to_files[val].add(rel)
    
    dupes = {v: sorted(files) for v, files in val_to_files.items() if len(files) >= 2}
    
    print("")
    print("  DUPLICATE CONSTANTS (length >= 8, across >= 2 files)")
    print("  " + "=" * 60)
    if not dupes:
        print("  No duplicated string constants found across files.")
        print("")
        return
    for val, files in sorted(dupes.items(), key=lambda item: (-len(item[1]), item[0])):
        print('  "%s" (%d files):' % (val, len(files)))
        for f in files:
            print("    %s" % f)
    print("")
    print("  >> %d duplicated value(s) found. Define each in one place." % len(dupes))
    print("")

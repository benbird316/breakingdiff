# -*- coding: utf-8 -*-
"""
dist_layout — installable layout build / verify (M-DIST1 / M-DIST4, B6)
==============================================================
build copies the source repository root into an installable layout: the current full
SKILL.md (compressed form belongs to B8/B9; this batch does not do stripped) + every .py
under scripts/ + every file under references/ + every file under examples/ recursively,
always excluding __pycache__. If the target already exists and is non-empty → refuse to
run (to prevent accidental overwrite; do not clear it).

verify reconciles "the three directories' relative-path file sets match the source
repository in both directions". Set semantics are stronger than file counts: counts can
match while names drift or extra files appear, and only sets catch that — a one-way
check sees missing files but not extra ones. The two sides of scripts/ are deliberately
asymmetric: want takes .py only (the source-side layout definition of scripts/ is all
*.py; taking everything would let stray files on the source side jam the forward
round-trip red forever), while got takes every file (layout smuggling must go red;
narrowing it would open a blind spot for extras). __pycache__ pruning happens before
the shape filter and is ignored under both shapes.

If the build target lands inside the source repository's subtree → refuse to run: the
copy source is the repository itself, and a target inside the scan range would copy
itself into itself while scanning (runaway self-consumption). The guard uses prefix
comparison (do not use os.path.commonpath — it raises ValueError across Windows
drives), at the _build entry point, before any makedirs/copy; a refusal produces zero
output.

Source anchor = the parent of the scripts/ directory holding this file (file_relative).
In the installed state the script has been copied away and the source root does not
exist; verifying the install directory against the manifest is outside M-DIST4 (B12
batch).

Three-tier exit codes (following the receipt.py convention):
    0  all green (build completed / verify found both directions consistent)
    1  red (build refused a non-empty target; verify found a mismatch, named entry by entry)
    2  runtime error (source anchor does not hold, bad arguments — not having run is not
       the same as having run red)
Red messages start with [dist_layout] and name each missing/extra/missing-directory item.
Pure standard library.

Usage: python dist_layout.py build <target_dir>
       python dist_layout.py verify <dir>
"""
import os
import shutil
import sys

EXIT_PASS = 0
EXIT_GATE_FAIL = 1
EXIT_RUNTIME_ERROR = 2

ROOT_FILE = "SKILL.md"
# (directory name, whether build takes .py only) — the layout definition of scripts is
# "all *.py"; references / examples take every file recursively; for verify's got-side
# shape see _verify
LEDGER_DIRS = (("scripts", True), ("references", False), ("examples", False))
EXCLUDE_DIRS = ("__pycache__", ".pytest_cache")


def _src_root():
    """Source anchor: the parent of the scripts/ directory holding dist_layout.py
    (file_relative)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _walk_files(base, only_py):
    """The set of relative paths of every file under base (posix separators, so grep
    works across machines), with cache directories (EXCLUDE_DIRS:
    __pycache__/.pytest_cache) removed wholesale; when only_py, also filter out non-.py
    files."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if only_py and not name.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), base)
            out.add(rel.replace(os.sep, "/"))
    return out


def _copy_tree(src, dst, only_py):
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in filenames:
            if only_py and not name.endswith(".py"):
                continue
            shutil.copy2(os.path.join(dirpath, name), os.path.join(target_dir, name))


def _anchor_missing(src):
    """Which of the four source-anchor items are missing. When the anchor does not hold,
    neither build nor verify can start, so it counts as a runtime error."""
    missing = [n for n in (ROOT_FILE,) + tuple(d for d, _ in LEDGER_DIRS)
               if not os.path.exists(os.path.join(src, n))]
    return missing


def _inside_source_tree(target):
    """Whether target (abspath-normalized) falls inside the source repository root's
    subtree. Prefix comparison plus a trailing separator: prevents sibling directories
    (f:\\repo2 wrongly eating f:\\repo) and drive-letter case drift; do not use
    os.path.commonpath — it raises ValueError across Windows drives. target equal to
    the source root is not covered here (the existing non-empty refusal handles it)."""
    s = os.path.abspath(_src_root()).lower()
    t = os.path.abspath(target).lower()
    return t.startswith(s + os.sep)


def _build(target):
    src = _src_root()
    missing = _anchor_missing(src)
    if missing:
        print(f"[dist_layout] runtime error: source anchor {src} lacks {', '.join(missing)}; the copy source does not hold")
        return EXIT_RUNTIME_ERROR
    if _inside_source_tree(target):
        print(f"[dist_layout] target {target} is inside the source repository subtree and build would consume itself "
              f"(the copy source {src} is the tree being written); refusing to run")
        return EXIT_GATE_FAIL
    if os.path.exists(target):
        if not os.path.isdir(target):
            print(f"[dist_layout] target {target} already exists and is not a directory; refusing to run (prevents accidental overwrite, does not clear)")
            return EXIT_GATE_FAIL
        if os.listdir(target):
            print(f"[dist_layout] target {target} already exists and is non-empty; refusing to run (prevents accidental overwrite, does not clear)")
            return EXIT_GATE_FAIL
    os.makedirs(target, exist_ok=True)
    shutil.copy2(os.path.join(src, ROOT_FILE), os.path.join(target, ROOT_FILE))
    for d, only_py in LEDGER_DIRS:
        _copy_tree(os.path.join(src, d), os.path.join(target, d), only_py)
    print(f"[dist_layout] build completed: {target} (source repository {src})")
    return EXIT_PASS


def _verify(target):
    src = _src_root()
    missing = _anchor_missing(src)
    if missing:
        print(f"[dist_layout] runtime error: source anchor {src} lacks {', '.join(missing)}; "
              "the reconciliation anchor does not hold (install-state verification belongs to B12, not this batch)")
        return EXIT_RUNTIME_ERROR
    problems = []
    if not os.path.isfile(os.path.join(target, ROOT_FILE)):
        problems.append(f"missing {ROOT_FILE}")
    for d, only_py in LEDGER_DIRS:
        tdir = os.path.join(target, d)
        if not os.path.isdir(tdir) or not os.listdir(tdir):
            problems.append(f"directory {d}/ is missing or empty")
            continue
        # want takes .py only (the source-side layout definition of scripts/ is all *.py;
        # taking everything would let stray files on the source side jam the forward
        # round-trip red forever); got takes every file (layout smuggling must go red;
        # narrowing it would open a blind spot for extras). __pycache__ pruning inside
        # _walk_files happens before the shape filter.
        want = _walk_files(os.path.join(src, d), only_py)
        got = _walk_files(tdir, False if d == "scripts" else only_py)
        problems += [f"{d}/{rel} is missing" for rel in sorted(want - got)]
        problems += [f"{d}/{rel} is extra" for rel in sorted(got - want)]
    if problems:
        print(f"[dist_layout] verify mismatch, {len(problems)} items:")
        for p in problems:
            print(f"  - {p}")
        return EXIT_GATE_FAIL
    print(f"[dist_layout] verify passed: {target} and source repository {src} match in both directions")
    return EXIT_PASS


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("build", "verify"):
        print("usage: python dist_layout.py build <target_dir> | verify <dir>",
              file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    return _build(argv[1]) if argv[0] == "build" else _verify(argv[1])


if __name__ == "__main__":
    sys.exit(main())

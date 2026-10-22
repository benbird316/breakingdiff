# -*- coding: utf-8 -*-
"""
version_stamp — single source of truth for the version, sync / check (M-DIST3, B7)
==========================================================
Single source = repository root VERSION (one-line semver `^\\d+\\.\\d+\\.\\d+$`, no v
prefix).
Derived-site list = module constant DERIVED_TARGETS, each item (relative path, dotted key
path); dotted syntax = key names separated by dots locating one value inside json (B7
scheduler decision ②, no $ syntax).

DERIVED_TARGETS is currently an empty tuple — that is a decided fact, not a half-finished
product: the distribution surface goes entirely through native directories (the manifest
was decided against), so there is no derived site to register; when B12 introduces the
manifest / INSTALL.md version site, add the (relative path, key path) pairs then. At that
point check's checked=N denominator follows the list length automatically, with no change
to the reporting logic.

sync: read VERSION → write each derived site. Writing is field-level (B7 scheduler
decision ③): touch only the leaf the dotted key points at, leave every other field in the
derived file as is — not a whole-file rewrite; compare before writing, and do not touch
the file when nothing changed (mtime unchanged — "did work" and "touched the file" are
two different things, and rewriting something unchanged only pollutes the mtime evidence).
check: (a) VERSION is present and well-formed (absent → exit 1, assertion red; present but
unreadable — a directory, a permission hole, and similar OSError → exit 2, runtime error,
not mixed with assertion red); (b) compare each derived site; a mismatch, a wholly missing
derived file, a missing key path, or bad json all exit 1 and are named (carrying
coverage_guard's discipline: raising is not warning — a missing file does not equal
consistency, and silently skipping swaps "the enumeration is complete" for "whatever was
enumerated"); (c) reporting carries the denominator checked=N, and an empty derived
surface self-reports explicitly instead of pretending "everything was checked".

Three-tier exit codes (following the dist_layout convention):
    0  all green (check consistent / sync completed, including the empty-derived-surface
       self-report)
    1  red (VERSION missing or malformed, a derived site drifted, a derived file
       missing/broken)
    2  runtime error (bad arguments — not having run is not the same as having run red)
Red messages start with [version_stamp]. Source repository root = the parent of the
scripts/ directory holding this file (file_relative, the same anchor as dist_layout; do
not use bd_paths — this file lives in the repository itself, and after being copied away
the anchor moves with it, which is exactly what we want). Pure standard library.

Usage: python version_stamp.py sync
       python version_stamp.py check
"""
import json
import os
import re
import sys

EXIT_PASS = 0
EXIT_GATE_FAIL = 1
EXIT_RUNTIME_ERROR = 2

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

VERSION_FILE = "VERSION"

# (relative path, dotted key path). Empty is a decided fact (no manifest), not a
# half-finished product; add entries when B12 introduces the manifest.
DERIVED_TARGETS = ()

# Sentinel for a dotted lookup that finds nothing: a derived site's legal value may be
# None/0/"", and using None as the "missing" marker would misread "the key is there with
# a null value" as "the key is not there".
_MISSING = object()


class _Red(Exception):
    """A check/sync red: the message carries the [version_stamp] prefix, main prints it
    and exits 1."""


def _src_root():
    """Source anchor: the parent of the scripts/ directory holding version_stamp.py
    (file_relative)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_version(root):
    path = os.path.join(root, VERSION_FILE)
    if not os.path.exists(path):
        raise _Red(
            f"[version_stamp] {VERSION_FILE} does not exist ({path}) — the single source of truth "
            "is absent and version checking cannot start. Missing is a check failure, not "
            "\"treated as consistent\"")
    # Present but not necessarily readable: directory state (IsADirectoryError),
    # permission holes, and similar OSError are not caught here. "Cannot read the source
    # of truth" is an environment error, bubbling to main's runtime-error tier (exit 2),
    # not disguised as an assertion red — only a malformed format is exit-1 semantics.
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not SEMVER_RE.fullmatch(text):
        raise _Red(
            f"[version_stamp] {VERSION_FILE} content {text!r} does not match semver "
            r"^\d+\.\d+\.\d+$ — a v prefix or a two-part form both count as malformed; "
            "passing an illegal version number downstream pollutes reconciliation")
    return text


def _lookup(data, dotted):
    """Look up by dotted key path; return _MISSING when not found (not None — see the
    sentinel comment)."""
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _set(data, dotted, value):
    """Field-level write: touch only the leaf the dotted key points at; create
    intermediate dicts when missing, and leave every other field alone. Returns whether
    the value actually changed — that is the criterion for "compare before writing", not
    diffing after writing."""
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    leaf = parts[-1]
    if leaf in cur and cur[leaf] == value:
        return False
    cur[leaf] = value
    return True


def _load_json(path):
    """Read a derived file. Bad json is reported separately: sync refuses to write (no
    silent rewrite replacing it), check counts it red."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _check():
    root = _src_root()
    version = _read_version(root)
    problems = []
    for rel, dotted in DERIVED_TARGETS:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            problems.append(f"{rel} is missing — derived site {dotted} cannot be checked; an absent file does not count as consistent")
            continue
        try:
            data = _load_json(path)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            problems.append(f"{rel} does not parse as legal JSON ({e}); derived site {dotted} cannot be compared")
            continue
        actual = _lookup(data, dotted)
        if actual is _MISSING:
            problems.append(f"derived site {dotted} is missing from {rel}")
        elif actual != version:
            problems.append(f"{rel}: {dotted} = {actual!r}, expected {version!r}")
    n = len(DERIVED_TARGETS)
    if problems:
        print(f"[version_stamp] check mismatch, {len(problems)} items (checked={n}):")
        for p in problems:
            print(f"  - {p}")
        return EXIT_GATE_FAIL
    print(f"[version_stamp] check passed: source version {version}, derived targets {n}, "
          f"checked={n}, every site consistent")
    return EXIT_PASS


def _sync():
    root = _src_root()
    version = _read_version(root)
    if not DERIVED_TARGETS:
        print(f"[version_stamp] sync self-report: source version {version}, 0 derived targets, nothing to write")
        return EXIT_PASS
    written, kept = 0, 0
    for rel, dotted in DERIVED_TARGETS:
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            try:
                data = _load_json(path)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"[version_stamp] sync refused to write: {rel} is not legal JSON ({e}) — "
                      "a broken derived file needs a human; silently rewriting it would erase the evidence of damage")
                return EXIT_GATE_FAIL
            if not isinstance(data, dict):
                print(f"[version_stamp] sync refused to write: {rel}'s top level is not a json object; "
                      f"key path {dotted} has nowhere to land")
                return EXIT_GATE_FAIL
        else:
            data = {}
        if _set(data, dotted, version):
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2)
                f.write("\n")
            written += 1
        else:
            kept += 1
    print(f"[version_stamp] sync completed: source version {version}, derived targets {len(DERIVED_TARGETS)}, "
          f"{written} written, {kept} skipped with no change")
    return EXIT_PASS


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in ("sync", "check"):
        print("usage: python version_stamp.py sync | check", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    try:
        return _sync() if argv[0] == "sync" else _check()
    except _Red as e:
        print(str(e))
        return EXIT_GATE_FAIL
    except OSError as e:
        # OSError (including IsADirectoryError/PermissionError) belongs to runtime-error
        # tier 2, not mixed with assertion red — OSError.__str__ carries the file name
        # and the errno reason, so name it directly.
        print(f"[version_stamp] runtime error: {e}")
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())

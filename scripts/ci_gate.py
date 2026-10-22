#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ci_gate — one entry point that runs every test script in this repository
=======================================================================
Both the local pre-commit hook and the GitHub Actions workflow call this file
and nothing else. That is the whole point: if the two kept their own lists, the
lists would drift, and the drift is silent — a new test gets added, one side
never learns about it, and the gate stays green while the surface it claims to
cover shrinks. So the workflow file does not enumerate tests either.

## Discovery is by naming convention, never by list

A file is a test if its name is `test_*.py` or `*_test.py`, anywhere under the
repository root, except under `__pycache__`, `.git`, `.pytest_cache`, and the
blind-run organizer directories (`_grader_local`).

Measured 2026-10-22: a hand-written list of 27 scripts was one short — it missed
`examples/docaudit/test_docaudit.py`, because that file sits one level deeper
than its siblings and the glob that built the list did not recurse. The README
had it; the list did not. That is the failure mode this rule prevents, and it
had already happened once before the rule existed.

`examples/forgery_poc.py` is deliberately not a test: it holds moves
(`forge_*` / `measure`), not assertions. It reaches the P side through
`delivery_gate_test.py`, which imports it and asserts on what it returns. The
naming rule keeps it out on its own — it matches neither pattern.

## "Nothing ran" must never look green

If discovery returns zero files, the gate exits 2, not 0. A typo in the
pattern, a renamed directory, or a checkout that dropped the tree would
otherwise print a clean summary over an empty run — the same three-level
silence this repository keeps closing elsewhere. Every run also prints the full
discovered list, so a shrunken surface is visible without a stored baseline.

## Exit tiers (same three as scripts/receipt.py, deliberately)

    0  every discovered test exited 0
    1  at least one test exited non-zero (business failure — block the commit)
    2  the gate could not run at all (no tests discovered, bad arguments, the
       gate itself raised) — "did not run" is not "ran red"

## Report, never summarize

A failing test's last lines of output are printed verbatim, one block per
failure. The gate does not retry, reorder by severity, or collapse failures
into a count. The caller decides what a failure means.

## What CI can and cannot cover (measured, not assumed)

The corpora are gitignored and fetched on demand — 56MB of Feather,
6MB of OpenAPI snapshots, the 7MB PDG sqlite, the 2.1GB llama.cpp archive — so
a fresh checkout has none of them. The case-study tests degrade to their
no-corpus path instead of failing: 27/27 green on a corpus-free tree with
pyarrow installed (2026-10-22). pyarrow itself is the one third-party package
the suite touches, and only in `casestudy/malecns/test_aligned.py`.

So on every push this gate proves the code-level surface. The corpus-anchored
assertions only run where the corpus was fetched, which on CI means never. That
limit is stated here rather than papered over: a green CI run is not evidence
that the case studies still reconcile against their data.

## Usage

    python scripts/ci_gate.py                # run every discovered test
    python scripts/ci_gate.py --list         # discovery only, run nothing
    python scripts/ci_gate.py --only refs    # substring filter on the path
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Anchor = the parent of the scripts/ directory holding this file. Resolved from
# __file__ so the gate works from any cwd, the same way dist_layout.py anchors.
ROOT = Path(__file__).resolve().parent.parent

# Pruned before descending, so a large .git or a fetched corpus tree costs nothing.
PRUNE = {"__pycache__", ".git", ".pytest_cache", "_grader_local"}

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_RUNTIME = 2


def discover(root):
    """Return every test file under root as a sorted list of relative paths."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE)
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            if name.startswith("test_") or name.endswith("_test.py"):
                rel = Path(dirpath, name).relative_to(root)
                found.append(rel)
    return sorted(found, key=lambda p: p.as_posix())


def run_one(root, rel):
    """Run one test with the interpreter that is running this gate.

    Same interpreter, not "python" from PATH: a gate that ran some tests under
    one interpreter and some under another would report a mixture nobody can
    read. cwd is the repository root for every test, so a test that resolves a
    path relative to its own file and one that resolves it relative to the root
    both behave the same way locally and on CI.
    """
    start = time.time()
    proc = subprocess.run(
        [sys.executable, str(root / rel)],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        errors="replace",
    )
    return proc.returncode, time.time() - start, proc.stdout, proc.stderr


def tail(text, limit=15):
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    return "\n".join(lines[-limit:])


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ci_gate",
        description="Run every test script discovered under the repository root.",
    )
    parser.add_argument("--list", action="store_true",
                        help="print the discovered test files and exit")
    parser.add_argument("--only", default=None, metavar="SUBSTRING",
                        help="run only tests whose relative path contains SUBSTRING")
    args = parser.parse_args(argv)

    tests = discover(ROOT)
    if not tests:
        print("[ci_gate] runtime error: discovered zero test files under %s. "
              "The discovery pattern or the checkout is wrong — this is not a pass."
              % ROOT, file=sys.stderr)
        return EXIT_RUNTIME

    selected = [t for t in tests if args.only is None or args.only in t.as_posix()]
    if not selected:
        print("[ci_gate] runtime error: --only %r matched none of the %d discovered "
              "test files." % (args.only, len(tests)), file=sys.stderr)
        return EXIT_RUNTIME

    width = max(len(t.as_posix()) for t in selected)
    for t in selected:
        print("  %s" % t.as_posix())
    print("[ci_gate] %d test file(s) discovered, %d selected"
          % (len(tests), len(selected)))

    if args.list:
        return EXIT_PASS

    print("")
    failures = []
    started = time.time()
    for rel in selected:
        code, elapsed, out, err = run_one(ROOT, rel)
        status = "PASS" if code == 0 else "FAIL"
        print("%s %7.0fms  %s" % (status, elapsed * 1000, rel.as_posix()))
        if code != 0:
            failures.append((rel.as_posix(), code, out, err))

    total = time.time() - started
    print("")
    if not failures:
        print("[ci_gate] %d passed in %.1fs — gate green"
              % (len(selected), total))
        return EXIT_PASS

    print("[ci_gate] %d passed, %d FAILED in %.1fs"
          % (len(selected) - len(failures), len(failures), total))
    for name, code, out, err in failures:
        print("")
        print("---- FAIL %s (exit %d) ----" % (name, code))
        # unittest writes its summary to stderr; a plain script usually writes to
        # stdout. Print whichever actually carried the news, stderr first.
        body = err.strip() or out.strip()
        print(tail(body))
    print("")
    print("[ci_gate] gate red — the commit is blocked. Fix the failures above; "
          "the gate does not retry.")
    return EXIT_FAIL


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — the gate must not die silently
        print("[ci_gate] runtime error: %s: %s" % (type(exc).__name__, exc),
              file=sys.stderr)
        sys.exit(EXIT_RUNTIME)

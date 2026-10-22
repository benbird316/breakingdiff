# -*- coding: utf-8 -*-
"""
dist_layout build/verify contract — the red end of B6's TDD (spec freeze §3/§4, T1–T9)
========================================================================
build copies the source repository root into an installable layout (SKILL.md + every
.py under scripts/ + every file under references/ + examples/ recursively, excluding
__pycache__); verify reconciles "the three directories' relative-path file sets match
the source repository in both directions". Two-directional sets are stronger than "the
file counts match": counts can match while names drift or extra files appear, and only
set semantics catch that — T4 (smuggle one extra file) is its direct red. T7 pins
build's self-intersection guard: a target inside the source repository subtree must be
refused — without the guard, _copy_tree copies itself into itself and grows without
bound (a review measured 7613 files in 6 seconds); T8 pins that scripts reconciliation
takes every file on the got side, so non-.py clutter smuggled into the layout must also
be judged "extra".

The tests run build/verify for real through subprocess (not import-then-self-compare),
asserting exit codes 0/1/2 directly against the contract's three-tier convention. All
action happens in a tempdir; the source repository is read-only and never written; do
not hand-build an "ideal layout" and assert against it — a criterion that bypasses the
subject under test tests nothing.

This file is the red end of B6: dist_layout.py is an implementation-side deliverable
that does not exist yet, so it exits 2 (runtime error: the script is absent; not having
run is not the same as having run red). After implementation-side delivery T1–T9 should
be all green; behavior that does not match exits 1. Red is the expected state, not a
failure.

Red messages start with [dist_layout_test] and name each missing/extra item.
No pytest dependency; pytest can collect it directly when present.
Usage: python scripts/dist_layout_test.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)           # source anchor: one level above the scripts/ holding dist_layout.py

SCRIPT = os.path.join(HERE, "dist_layout.py")

# Source repository premise: build's copy source and verify's reconciliation anchor both
# live at these four points
REPO_LAYOUT = ("SKILL.md", "scripts", "references", "examples")

EXTRA_NAME = "bd_layout_probe_should_not_exist.py"   # the extra file T4 smuggles into the layout
FAKE_PYC = "bd_layout_fake_cache.pyc"                # the fake cache T6 smuggles into the layout
STRAY_NAME = "stray.txt"                             # the non-.py clutter T8 smuggles into the layout's scripts/


class DistLayoutTestError(AssertionError):
    """Assertion red (exit-code 1 semantics): it ran, and judged the behavior as not
    matching the contract. The runner uses the exception type to split "red" and
    "runtime error" into two exit codes."""


def _run(*args):
    """Run the subject for real through subprocess; return CompletedProcess. Keep
    stdout/stderr as bytes: child output encoding follows the host locale (GBK is common
    on Chinese Windows), while the assertion anchors use only ASCII file/directory names
    — bytes are identical under every encoding, so the whole encoding trap is avoided."""
    if not os.path.isfile(SCRIPT):
        raise RuntimeError(
            "[dist_layout_test] runtime error: scripts/dist_layout.py does not exist "
            "(B6 implementation-side not delivered?); the test cannot run")
    try:
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True)
    except OSError as e:
        raise RuntimeError(
            f"[dist_layout_test] runtime error: starting the subprocess failed: {e}") from e


def _run_bounded(*args, timeout):
    """A real run with a timeout (T7 only): without the guard, build's self-consumption
    runs away and cannot be awaited forever. On timeout, subprocess.run kills the
    process and re-raises TimeoutExpired as is; the runaway leftover tree is cleaned by
    the caller's finally."""
    if not os.path.isfile(SCRIPT):
        raise RuntimeError(
            "[dist_layout_test] runtime error: scripts/dist_layout.py does not exist "
            "(B6 implementation-side not delivered?); the test cannot run")
    try:
        return subprocess.run([sys.executable, SCRIPT, *args],
                              capture_output=True, timeout=timeout)
    except OSError as e:
        raise RuntimeError(
            f"[dist_layout_test] runtime error: starting the subprocess failed: {e}") from e


def _force_rmtree(path):
    """T7 cleanup: the self-consumed tree nests level by level along
    "_t7_probe/scripts", and in ten seconds it can exceed Windows MAX_PATH; when plain
    rmtree cannot delete it, fall back to the \\\\?\\ prefix and try again; if neither
    works, raise — a leftover tree in the repository is worse than a red test, so do not
    stay silent."""
    abs_path = os.path.abspath(path)
    if os.path.exists(abs_path):
        shutil.rmtree(abs_path, ignore_errors=True)
    prefixed = "\\\\?\\" + abs_path
    if os.path.exists(prefixed):
        shutil.rmtree(prefixed, ignore_errors=True)
    if os.path.exists(prefixed):
        raise RuntimeError(
            f"[dist_layout_test] T7 cleanup failed: {abs_path} cannot be fully deleted (suspected "
            "over-long path); the repository leftover must be removed by hand before rerunning")


def _out(p):
    return (p.stdout + p.stderr).decode("utf-8", "replace")


def _require_repo_layout():
    """When the source repository lacks SKILL.md or one of the three directories, both
    build's copy source and verify's reconciliation anchor fail to hold — the repository
    itself is wrong, no red/green conclusion is meaningful, and it counts as a runtime
    error."""
    for name in REPO_LAYOUT:
        if not os.path.exists(os.path.join(REPO_ROOT, name)):
            raise RuntimeError(
                f"[dist_layout_test] runtime error: source repository root {REPO_ROOT} lacks {name}; "
                "the copy source/reconciliation anchor does not hold")


def _build(target):
    p = _run("build", target)
    if p.returncode != 0:
        raise DistLayoutTestError(
            f"[dist_layout_test] build {target} should exit 0, got {p.returncode}:\n"
            + _out(p))
    return p


def _verify_expect(target, want_code, must_mention=()):
    """Assert the verify exit code and red-message naming in one go. In the red state,
    every missing and extra file must be named; a failure message that only says
    "mismatch" without names forces whoever debugs it to diff by hand."""
    p = _run("verify", target)
    out = p.stdout + p.stderr
    assert p.returncode == want_code, \
        f"[dist_layout_test] verify should exit {want_code}, got {p.returncode}:\n" + _out(p)
    for anchor in must_mention:
        assert anchor.encode("ascii") in out, \
            f"[dist_layout_test] verify output does not name {anchor} (missing/extra items must be named one by one)"
    return p


def test_t1_build_then_verify_roundtrip():
    """T1: the forward round-trip. build exits 0, the product has at least SKILL.md and
    three non-empty directories, and verify on the same product exits 0. Those
    isfile/isdir checks in between are not a hand-built ideal layout — they are build's
    minimal-product contract, guarding against a build/verify symmetry bug (when both
    sides fail to check something, the round-trip passes itself)."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "layout")
        _build(target)
        assert os.path.isfile(os.path.join(target, "SKILL.md")), \
            "[dist_layout_test] build product lacks SKILL.md — the root file was not copied out"
        for d in ("scripts", "references", "examples"):
            path = os.path.join(target, d)
            assert os.path.isdir(path) and os.listdir(path), \
                f"[dist_layout_test] build product lacks directory {d} or the directory is empty"
        _verify_expect(target, 0)


def test_t2_verify_reds_on_missing_file():
    """T2: the layout is missing one file → verify exits 1 and the red message names
    that file. The victim is taken fresh from the build product (the first .py in sorted
    order) rather than freezing a specific name — the naming assertion is about "the one
    that was deleted", not a particular file."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "layout")
        _build(target)
        scripts_dir = os.path.join(target, "scripts")
        pys = sorted(n for n in os.listdir(scripts_dir) if n.endswith(".py"))
        if not pys:
            raise DistLayoutTestError(
                "[dist_layout_test] build product's scripts/ has no .py — "
                "the scripts were not copied, so T2 has nothing to delete")
        victim = pys[0]
        os.remove(os.path.join(scripts_dir, victim))
        _verify_expect(target, 1, must_mention=(victim,))


def test_t3_verify_reds_on_missing_dir():
    """T3: an entire subdirectory is gone → verify exits 1. After deleting references/
    the directory-missing and set-mismatch conditions both hold; this pins the exit code
    and the directory-name naming (contract: a missing directory is named)."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "layout")
        _build(target)
        shutil.rmtree(os.path.join(target, "references"))
        _verify_expect(target, 1, must_mention=("references",))


def test_t4_verify_reds_on_extra_file():
    """T4: one extra file is smuggled in → verify exits 1 and names it — the direct red
    for a two-directional set. An implementation that only checks one direction must go
    red here (final-review mutation candidate ③ pins exactly this half)."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "layout")
        _build(target)
        with open(os.path.join(target, "examples", EXTRA_NAME), "wb") as f:
            f.write(b"probe\n")
        _verify_expect(target, 1, must_mention=(EXTRA_NAME,))


def test_t5_build_refuses_nonempty_target():
    """T5: the target already exists and is non-empty → refuse to run (exit 1), and the
    existing content must be left alone — a guard that clears first and refuses second
    has not prevented anything."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "occupied")
        os.makedirs(target)
        marker = os.path.join(target, "occupant.txt")
        with open(marker, "wb") as f:
            f.write(b"do not touch\n")
        p = _run("build", target)
        assert p.returncode == 1, \
            (f"[dist_layout_test] build should refuse a non-empty target (exit 1), "
             f"got {p.returncode}:\n" + _out(p))
        with open(marker, "rb") as f:
            assert f.read() == b"do not touch\n", \
                "[dist_layout_test] build touched existing content when refusing a non-empty target — accidental-overwrite prevention failed"


def test_t6_pycache_is_invisible_to_build_and_verify():
    """T6: __pycache__ enters neither the layout nor the reconciliation shape. The
    construction follows the spec freeze: after build, smuggle a fake pyc into the
    product's scripts/__pycache__/ and verify must still exit 0 — if the reconciliation
    shape is polluted by cache files, this goes red at once. The build-side exclusion
    assertion only has discriminating power when the source repository happens to have
    __pycache__ at the time; when it does not, print one self-reporting line about the
    coverage boundary rather than pretending it checked (the normal-state verification
    of build's exclusion surface belongs to the final-review mutation evidence)."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "layout")
        _build(target)
        src_cache = os.path.join(REPO_ROOT, "scripts", "__pycache__")
        built_cache = os.path.join(target, "scripts", "__pycache__")
        if os.path.isdir(src_cache):
            assert not os.path.exists(built_cache), \
                "[dist_layout_test] source scripts/__pycache__ was copied into the layout — build exclusion failed"
        else:
            print("  SKIP-NOTE source scripts/__pycache__ absent; build's exclusion surface has zero discrimination this run "
                  "(verify-side exclusion is still verified by the pyc-smuggling section)")
        os.makedirs(built_cache, exist_ok=True)
        with open(os.path.join(built_cache, FAKE_PYC), "wb") as f:
            f.write(b"\x00fake\n")
        _verify_expect(target, 0)


def test_t7_build_rejects_target_inside_repo():
    """T7: a build target inside the source repository subtree → refuse (exit 1). The
    source anchor is file_relative and build uses the repository it lives in as the copy
    source; a target inside the source repository makes _copy_tree copy directories it
    scans back into the scan range, and the self-consumption grows without bound. Red-
    state evidence discipline: without the guard this run most likely takes the 10-second
    timeout path — kill the process, clean up in finally, record red "build self-consumption
    ran away"; with the guard implemented it should exit 1 in a split second. On refusal
    the target must be empty (the guard is at the _build entry point, before any
    makedirs/copy); the product probe uses the \\\\?\\ prefix — after a runaway tree grows
    too long, a plain-path exists probe reports a false negative. The red message's naming
    anchor is the target directory name (ASCII); the "refused" wording belongs to the
    implementation, not a frozen literal."""
    _require_repo_layout()
    target = os.path.join(HERE, "_t7_probe")
    try:
        try:
            p = _run_bounded("build", target, timeout=10)
        except subprocess.TimeoutExpired:
            raise DistLayoutTestError(
                "[dist_layout_test] T7 build self-consumption ran away: a target inside the source "
                "repository subtree was not refused; killed after a 10-second timeout (the runaway tree "
                "is cleaned in finally)")
        out = p.stdout + p.stderr
        reds = []
        if p.returncode != 1:
            reds.append(f"exit code should be 1 (refused), got {p.returncode}")
        if b"_t7_probe" not in out:
            reds.append("the red message does not name the refused target _t7_probe")
        if os.path.exists("\\\\?\\" + os.path.abspath(target)):
            reds.append("the target was still produced on refusal — the guard must precede any makedirs/copy")
        if reds:
            raise DistLayoutTestError(
                "[dist_layout_test] T7: build did not correctly refuse a target inside the repository subtree:\n  - "
                + "\n  - ".join(reds))
    finally:
        _force_rmtree(target)


def test_t8_verify_reds_on_stray_nonpy_in_scripts():
    """T8: the direct red for narrowing the scripts shape to .py-only on the got side
    (review measured: smuggling stray.txt exited 0 silently). Decision: got takes every
    file while want stays .py-only — narrowing want is justified (the source-side layout
    definition of scripts/ is all *.py; taking everything would let stray source-side
    files jam the forward round-trip red forever); got is "what the layout actually
    contains", and narrowing it would open a blind spot for extras. The stray must go red
    as "extra" and be named scripts/stray.txt (the implementation's red-message relative
    path uses posix separators; the anchor is pinned accordingly). It does not conflict
    with T6: __pycache__ as a whole directory is outside the reconciliation shape, so
    T6's pyc must still be ignored, while T8's stray sits directly under scripts/ and
    must be caught."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "layout")
        _build(target)
        with open(os.path.join(target, "scripts", STRAY_NAME), "wb") as f:
            f.write(b"stray\n")
        _verify_expect(target, 1, must_mention=("scripts/" + STRAY_NAME,))


def test_t9_pytest_cache_is_invisible_to_build_and_verify():
    """T9: .pytest_cache gets the same treatment as __pycache__ — it enters neither the
    layout nor the reconciliation shape. Cause: running pytest locally before the V1.0
    release left scripts/.pytest_cache/, and verify against the source repository went
    red (nodeids judged "extra"), going green only after a manual cleanup each time — a
    pit of "someone has to remember to clean it every time", the same class of cache
    artifact as __pycache__, so the pruning shape should be identical. The construction
    follows the T6 freeze: after build, smuggle a fake cache file into the product's
    scripts/.pytest_cache/ and verify must still exit 0; the build-side exclusion
    assertion only has discriminating power when the source repository happens to have
    scripts/.pytest_cache at the time, and when it does not, print SKIP-NOTE to self-
    report the coverage boundary rather than pretending it checked."""
    _require_repo_layout()
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "layout")
        _build(target)
        src_cache = os.path.join(REPO_ROOT, "scripts", ".pytest_cache")
        built_cache = os.path.join(target, "scripts", ".pytest_cache")
        if os.path.isdir(src_cache):
            assert not os.path.exists(built_cache), \
                "[dist_layout_test] source scripts/.pytest_cache was copied into the layout — build exclusion failed"
        else:
            print("  SKIP-NOTE source scripts/.pytest_cache absent; build's exclusion surface has zero discrimination this run "
                  "(verify-side exclusion is still verified by the cache-smuggling section)")
        os.makedirs(built_cache, exist_ok=True)
        nodeids = os.path.join(built_cache, "v", "cache", "nodeids")
        os.makedirs(os.path.dirname(nodeids), exist_ok=True)
        with open(nodeids, "wb") as f:
            f.write(b'["fake"]\n')
        _verify_expect(target, 0)


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad, errs = [], []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS {name}")
        except (DistLayoutTestError, AssertionError):
            bad.append(name)
            print(f"  FAIL {name}")
            traceback.print_exc()
        except Exception:
            errs.append(name)
            print(f"  ERROR {name}")
            traceback.print_exc()
    parts = []
    if bad:
        parts.append(f"failed: {bad}")
    if errs:
        parts.append(f"runtime errors: {errs} (exit code 2, see ERROR above)")
    passed = len(fns) - len(bad) - len(errs)
    print(f"\n{passed}/{len(fns)} passed" + (", " + "; ".join(parts) if parts else ""))
    return 2 if errs else (1 if bad else 0)


if __name__ == "__main__":
    raise SystemExit(main())

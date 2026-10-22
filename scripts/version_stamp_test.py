# -*- coding: utf-8 -*-
"""
version_stamp sync/check contract — the red end of B7's TDD (spec freeze §2/§4)
================================================================
Single version source of truth = repository root VERSION (semver `^\\d+\\.\\d+\\.\\d+$`);
derived-site list = module constant DERIVED_TARGETS (each item of shape (relative path,
json path expression); currently an empty tuple — not doing the manifest is a decided
fact, and INSTALL.md's version site joins only when B12 does).

  sync  : read VERSION and write each derived site; compare before writing and do not
          write when nothing changed (the energy-sankey precedent); an empty derived
          surface self-reports explicitly and exits 0, not pretending work was done.
  check : (a) VERSION exists and is well-formed; (b) each derived site is compared, and
          a mismatch exits 1 (carrying coverage_guard's discipline: raising is not
          warning); (c) reporting carries the denominator checked=N (N = derived-site
          count) — an empty derived surface self-reports explicitly instead of
          pretending "everything was checked".
  Red messages carry the [version_stamp] prefix; exit codes are the three tiers 0/1/2;
  the source repository root = one level above the scripts/ holding this file
  (file_relative, the same anchor as dist_layout).

Flow (everything in a tempdir): the implementation derives the repository root by
file_relative, so the test copies version_stamp.py into tempdir/scripts/ and runs it for
real through subprocess — the copy's root derivation is pinned to the tempdir, VERSION
and derived sites are fully controlled, and nothing depends on the real repository's
VERSION being present. Child processes uniformly get PYTHONIOENCODING=utf-8: the red
messages are English text, but unless the child's output encoding is pinned, decoding
under a GBK host is a gamble.

The non-empty derived-site scenario is injected through a `python -c` wrapper: sys.path
points at tempdir/scripts, and after import DERIVED_TARGETS is assigned directly (the
equivalent of monkeypatching a module constant inside the child-process boundary), then
main([subcmd]) is called — the entry shape follows the dist_layout precedent main(argv)
(pinned by B7 scheduler decision). The json path expression syntax is pinned to a single
dotted layer: key names separated by dots locating one value inside json, no $ syntax (B7
scheduler decision ②); multi-layer paths are outside this test's surface. Other existing
fields in the derived file must not be destroyed by sync (per-site field-level write
semantics, not a whole-file rewrite; decision ③).

This file is the red end of B7: version_stamp.py is an implementation-side deliverable
that does not exist yet, so it exits 2 (runtime error: the script is absent; not having
run is not the same as having run red). After implementation-side delivery all scenarios
should be green; behavior that does not match exits 1. Red is the expected state, not a
failure.

Red messages start with [version_stamp_test]. No pytest dependency; pytest can collect it
directly when present. Usage: python scripts/version_stamp_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "version_stamp.py")

VALID_VERSION = "1.0.0"
# Injection derived site: single dotted-layer expression (syntax decision ② pinned, see
# the module docstring)
TARGETS = (("derived.json", "version"),)
DERIVED_NAME = "derived.json"


class VersionStampTestError(AssertionError):
    """Assertion red (exit-code 1 semantics): it ran, and judged the behavior as not
    matching the contract. The runner uses the exception type to split "red" and
    "runtime error" into two exit codes; conflating them makes "the implementation has a
    bug" and "the test did not run" look the same."""


def _out(p):
    return (p.stdout + p.stderr).decode("utf-8", "replace")


def _require_script():
    if not os.path.isfile(SCRIPT):
        raise RuntimeError(
            "[version_stamp_test] runtime error: scripts/version_stamp.py does not exist "
            "(B7 implementation-side not delivered?); the test cannot run")


def _stage_repo(td, version_text):
    """Build a minimal repository in the tempdir: scripts/version_stamp.py (a copy of the
    real implementation) + VERSION. The copy derives the repository root by
    file_relative, pinning it to the tempdir, so VERSION and derived sites are fully
    controlled. version_text=None means no VERSION is written (the missing scenario)."""
    _require_script()
    scripts_dir = os.path.join(td, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    shutil.copyfile(SCRIPT, os.path.join(scripts_dir, "version_stamp.py"))
    if version_text is not None:
        with open(os.path.join(td, "VERSION"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(version_text)
    return td


def _run_cmd(repo, subcmd):
    """Run the version_stamp.py subcommand in the tempdir repository for real through
    subprocess."""
    _require_script()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        return subprocess.run(
            [sys.executable, os.path.join(repo, "scripts", "version_stamp.py"),
             subcmd], capture_output=True, env=env, cwd=repo, timeout=60)
    except OSError as e:
        raise RuntimeError(
            f"[version_stamp_test] runtime error: starting the subprocess failed: {e}") from e


def _run_injected(repo, subcmd, targets):
    """Real run with an injected DERIVED_TARGETS: a -c wrapper imports the module in the
    tempdir repository, assigns the module constant directly (the equivalent of
    monkeypatching a module constant inside the child-process boundary), then calls
    main([subcmd]) — the entry shape follows the dist_layout precedent main(argv)."""
    _require_script()
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n" % os.path.join(repo, "scripts")
        + "import version_stamp\n"
        "version_stamp.DERIVED_TARGETS = %r\n" % (tuple(targets),)
        + "sys.exit(version_stamp.main([%r]))\n" % subcmd
    )
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        return subprocess.run([sys.executable, "-c", code], capture_output=True,
                              env=env, cwd=repo, timeout=60)
    except OSError as e:
        raise RuntimeError(
            f"[version_stamp_test] runtime error: starting the subprocess failed: {e}") from e


def _assert_exit(p, want, what):
    assert p.returncode == want, (
        f"[version_stamp_test] {what} should exit {want}, got {p.returncode}:\n"
        + _out(p))


def _write_derived(repo, obj):
    path = os.path.join(repo, DERIVED_NAME)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True)
    return path


def _read_derived(repo):
    path = os.path.join(repo, DERIVED_NAME)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_check_passes_with_valid_version_and_reports_checked_zero():
    """VERSION is valid (1.0.0) → check exits 0 and the output contains checked=0 —
    reporting carries the denominator, and an empty derived surface self-reports
    explicitly. The derived-site list being empty is a decided fact (no manifest);
    checked=0 is an honest self-report, not short work."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, VALID_VERSION + "\n")
        p = _run_cmd(repo, "check")
        _assert_exit(p, 0, "check (valid VERSION)")
        assert "checked=0" in _out(p), \
            "[version_stamp_test] check output lacks the denominator self-report checked=0:\n" + _out(p)


def test_check_reds_when_version_missing():
    """VERSION missing → check exits 1 and the red message carries the [version_stamp]
    prefix — a missing source of truth is red, not silently passed."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, None)
        p = _run_cmd(repo, "check")
        _assert_exit(p, 1, "check (VERSION missing)")
        assert "[version_stamp]" in _out(p), \
            "[version_stamp_test] the red message lacks the [version_stamp] prefix:\n" + _out(p)


def test_check_reds_on_malformed_version():
    """VERSION content V0.1 / 1.0 → malformed (semver ^\\d+\\.\\d+\\.\\d+$); check exits 1
    with the prefix — both a v prefix and a two-part form are in the forbidden set."""
    for bad in ("V0.1\n", "1.0\n"):
        with tempfile.TemporaryDirectory() as td:
            repo = _stage_repo(td, bad)
            p = _run_cmd(repo, "check")
            _assert_exit(p, 1, f"check (VERSION={bad.strip()!r} malformed)")
            assert "[version_stamp]" in _out(p), \
                "[version_stamp_test] the red message lacks the [version_stamp] prefix:\n" + _out(p)


def test_sync_writes_derived_targets_then_check_greens():
    """Derived sites non-empty (injected TARGETS): sync writes VERSION into the specified
    site of the derived json without destroying other existing fields (per-site write,
    not a whole-file rewrite); after the write check exits 0 and reports checked=1 — the
    denominator follows the derived-site count, not a constant 0."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, VALID_VERSION + "\n")
        _write_derived(repo, {"other": "keep"})
        p = _run_injected(repo, "sync", TARGETS)
        _assert_exit(p, 0, "sync (injected derived site, first write)")
        data = _read_derived(repo)
        assert data.get("version") == VALID_VERSION, \
            f"[version_stamp_test] after sync the derived site should be {VALID_VERSION!r}, got {data!r}"
        assert data.get("other") == "keep", \
            f"[version_stamp_test] sync destroyed an existing field of the derived file: {data!r}"
        c = _run_injected(repo, "check", TARGETS)
        _assert_exit(c, 0, "check (should be consistent after sync)")
        assert "checked=1" in _out(c), \
            "[version_stamp_test] check output lacks the denominator self-report checked=1:\n" + _out(c)


def test_check_reds_and_names_target_when_derived_diverged():
    """Hand-edit a derived site (bypassing sync) → check exits 1 and the red message
    names the derived file — "which site drifted" must be locatable; reporting only
    "mismatch" leaves whoever debugs it to diff by hand."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, VALID_VERSION + "\n")
        _write_derived(repo, {"other": "keep"})
        s = _run_injected(repo, "sync", TARGETS)
        _assert_exit(s, 0, "sync (preparatory write)")
        data = _read_derived(repo)
        data["version"] = "9.9.9"
        _write_derived(repo, data)
        c = _run_injected(repo, "check", TARGETS)
        _assert_exit(c, 1, "check (derived site hand-edited)")
        out = _out(c)
        assert "[version_stamp]" in out and DERIVED_NAME in out, \
            (f"[version_stamp_test] the red message must carry the prefix and name {DERIVED_NAME}:\n"
             + out)


def test_sync_skips_write_when_nothing_changed():
    """sync does not write when nothing changed (compare before writing): after the
    second sync the derived file's mtime is unchanged and the content reads back the
    same — the mtime assertion catches the "rewrite every time" regression, and the
    read-back prevents the "touch without writing" false green. The two syncs are tens of
    milliseconds apart across subprocess boundaries, so a rewrite would definitely change
    the mtime."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, VALID_VERSION + "\n")
        _write_derived(repo, {"other": "keep"})
        p1 = _run_injected(repo, "sync", TARGETS)
        _assert_exit(p1, 0, "sync (first)")
        path = os.path.join(repo, DERIVED_NAME)
        m1 = os.path.getmtime(path)
        p2 = _run_injected(repo, "sync", TARGETS)
        _assert_exit(p2, 0, "sync (rerun should change nothing)")
        m2 = os.path.getmtime(path)
        assert m1 == m2, \
            (f"[version_stamp_test] sync rewrote the derived file when nothing changed "
             f"(mtime {m1!r} → {m2!r}) — compare-before-write failed")
        assert _read_derived(repo).get("version") == VALID_VERSION, \
            "[version_stamp_test] the derived site's content changed after the second sync"


def test_sync_self_reports_empty_derived_surface():
    """sync with an empty derived surface → exits 0 and explicitly self-reports (source
    version, 0 derived targets, nothing to write) — zero derived sites must still be
    reported; a silent success and "checked" are not the same thing."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, VALID_VERSION + "\n")
        p = _run_cmd(repo, "sync")
        _assert_exit(p, 0, "sync (empty derived surface)")
        out = _out(p)
        for anchor in (VALID_VERSION, "0 derived targets", "nothing to write"):
            assert anchor in out, \
                f"[version_stamp_test] the empty-derived-surface self-report lacks anchor {anchor!r}:\n" + out


def test_check_reds_naming_missing_derived_file_when_target_absent():
    """After injecting a derived site, the derived file is wholly missing → check exits 1
    and the red message names that file (B7 scheduler decision ⑥): a nonexistent file does
    not equal "consistent", and silently skipping swaps "the enumeration is complete" for
    "whatever was enumerated" — missing is a check result and must be reported explicitly.
    Note the boundary with scenario 1: that one is an empty derived surface
    (DERIVED_TARGETS currently empty) self-reporting checked=0 and exiting 0; this one has
    a non-empty derived site with the file absent, which is a check failure."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, VALID_VERSION + "\n")
        assert not os.path.exists(os.path.join(repo, DERIVED_NAME))
        c = _run_injected(repo, "check", TARGETS)
        _assert_exit(c, 1, f"check (derived file {DERIVED_NAME} missing)")
        out = _out(c)
        assert "[version_stamp]" in out and DERIVED_NAME in out, \
            (f"[version_stamp_test] the red message must carry the prefix and name the missing file "
             f"{DERIVED_NAME}:\n" + out)


def test_version_unreadable_maps_to_runtime_error():
    """VERSION unreadable (created as a directory) → check exits 2 as a runtime error (B7
    review G2): "cannot read the source of truth" is not an assertion red (only a
    malformed format is exit 1), it is an execution-environment error — the three-tier
    exit codes must put OSError in tier 2; bubbling up as a bare traceback with exit 1
    mixes tiers (the caller would read 1 as "version check failed" and try to fix the
    version number, which cannot work). The current implementation catches only assertion
    red in main → OSError bubbles to exit 1 → this case is red; once the implementation
    adds the catch and exits 2 it is green."""
    with tempfile.TemporaryDirectory() as td:
        repo = _stage_repo(td, None)
        os.mkdir(os.path.join(repo, "VERSION"))
        p = _run_cmd(repo, "check")
        _assert_exit(p, 2, "check (VERSION is an unreadable directory → should be runtime-error tier 2)")


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad, errs = [], []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS {name}")
        except (VersionStampTestError, AssertionError):
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

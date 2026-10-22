# -*- coding: utf-8 -*-
"""
bd_paths four-level resolution contract — the red end of B6's TDD (spec freeze §2/§4, T1–T6)
================================================================
resolve_bd_home tries four sources first-match-wins: BD_HOME → CLAUDE_SKILL_DIR →
CLAUDE_PLUGIN_ROOT → two levels up from file_hint. Every candidate passes the same
usability assertion (scripts/breakingdiff.py is a real file); a source set explicitly
but with an unusable candidate must raise at once and must not degrade silently to the
next level — an explicit environment variable is the user's or host's intent, and
"resolved against the wrong directory" is worse than not resolved at all, while a
silent substitution would drop the degraded value into the legal readout domain.

This file is the red end of B6: bd_paths.py is an implementation-side deliverable that
does not exist yet, so it exits 2 (runtime error: import failed; not having run is not
the same as having run red). After the implementation-side delivery T1–T6 should be all
green; behavior that does not match exits 1. Red is the expected state, not a failure.

T1–T6 all go through resolve_bd_home(environ=..., file_hint=...) parameter injection;
no setenv — polluting the process environment and then cleaning it up leaves a mine for
the next test if not fully cleaned. The repository root is two levels up from this
test's __file__, never a hardcoded path.

Red messages start with [bd_paths_test] and name what was got versus what was expected.
No pytest dependency; pytest can collect it directly when present.
Usage: python scripts/bd_paths_test.py
"""
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)           # one level above scripts/, i.e. the repository root
sys.path.insert(0, HERE)

# Test double for file_hint: co-located with where the subject will land
# (scripts/bd_paths.py), so two levels up is REPO_ROOT. The contract takes only the two
# levels above hint as the candidate and does not stat hint itself, so this path not
# existing before the implementation ships does not affect the assertions.
HINT = os.path.join(HERE, "bd_paths.py")

REPO_ANCHOR = os.path.join(REPO_ROOT, "scripts", "breakingdiff.py")


class BdPathsTestError(AssertionError):
    """Assertion red (exit-code 1 semantics): it ran, and judged the behavior as not
    matching the contract. The runner uses the exception type to split "red" and
    "runtime error" into two exit codes; conflating them makes "the implementation has
    a bug" and "the test did not run" look the same."""


def _load():
    """Lazily import the subject. An import failure counts as a runtime error (exit
    code 2): at module top level the script would crash outright, and "did not run"
    would disguise itself as "ran red"."""
    try:
        import bd_paths
    except Exception as e:
        raise RuntimeError(
            "[bd_paths_test] runtime error: import bd_paths failed "
            f"(B6 implementation-side not delivered?): {e!r}") from e
    return bd_paths


def _require_repo_anchor():
    """T1–T4 use REPO_ROOT as a "usable candidate", premised on scripts/breakingdiff.py
    really being there. If the premise collapses, the repository itself is wrong and no
    red/green conclusion is meaningful, so it counts as a runtime error."""
    if not os.path.isfile(REPO_ANCHOR):
        raise RuntimeError(
            f"[bd_paths_test] runtime error: {REPO_ROOT} lacks scripts/breakingdiff.py; "
            "the candidate-usability premise does not hold")


def _assert_home(home, source, want_source, want_root):
    assert source == want_source, \
        f"[bd_paths_test] source should be {want_source!r}, got {source!r}"
    assert os.path.realpath(home) == os.path.realpath(want_root), \
        f"[bd_paths_test] bd_home should resolve to {want_root}, got {home!r}"


def _get_error_type(B):
    """Get the BdPathError class and pin the type contract: a ValueError subclass (spec
    §2 freeze). An implementation missing this class is itself behavior mismatch, i.e.
    red."""
    etype = getattr(B, "BdPathError", None)
    if etype is None:
        raise BdPathsTestError(
            "[bd_paths_test] bd_paths does not define BdPathError — "
            "the exception type is part of the contract (BdPathError(ValueError))")
    assert issubclass(etype, ValueError), \
        f"[bd_paths_test] BdPathError should be a ValueError subclass, got {etype!r}"
    return etype


def _assert_error_shape(exc, anchors):
    """Error shape: the message starts with [bd_paths] and names the sources tried. The
    source anchors are relaxed to "either the source enum name or the environment
    variable name hits" — the contract freezes the enum values and the duty to name the
    sources tried, not a message wording template; pinning the anchor too tightly would
    force the implementation to chase literals."""
    msg = str(exc)
    assert msg.startswith("[bd_paths]"), \
        f"[bd_paths_test] the BdPathError message should start with [bd_paths], got: {msg!r}"
    assert any(a in msg for a in anchors), \
        f"[bd_paths_test] the message does not name the sources tried ({anchors}), got: {msg!r}"


def test_t1_env_level_wins():
    """T1: BD_HOME non-empty and its candidate usable → (repository root, "env"), the
    first level under first-match-wins."""
    B = _load()
    _require_repo_anchor()
    home, source = B.resolve_bd_home(environ={"BD_HOME": REPO_ROOT}, file_hint=HINT)
    _assert_home(home, source, "env", REPO_ROOT)


def test_t2_skill_dir_level():
    """T2: BD_HOME absent, CLAUDE_SKILL_DIR non-empty and usable → (repository root,
    "skill_dir"). The environ deliberately has no BD_HOME key — "unset" and "set to the
    empty string" are two entry points, and the latter belongs to T4."""
    B = _load()
    _require_repo_anchor()
    home, source = B.resolve_bd_home(environ={"CLAUDE_SKILL_DIR": REPO_ROOT},
                                     file_hint=HINT)
    _assert_home(home, source, "skill_dir", REPO_ROOT)


def test_t3_plugin_root_level():
    """T3: the first two levels absent, CLAUDE_PLUGIN_ROOT non-empty and usable →
    (repository root, "plugin_root")."""
    B = _load()
    _require_repo_anchor()
    home, source = B.resolve_bd_home(environ={"CLAUDE_PLUGIN_ROOT": REPO_ROOT},
                                     file_hint=HINT)
    _assert_home(home, source, "plugin_root", REPO_ROOT)


def test_t4_file_relative_when_env_all_empty():
    """T4: all three env levels explicitly passed as the empty string → all skipped as
    unset, landing on (repository root, "file_relative"). Using empty strings rather than
    an empty dict also pins the contract "the empty string counts as unset": if the
    implementation treats "set but empty" as an explicit setting and raises while
    validating it, this case goes red at once."""
    B = _load()
    _require_repo_anchor()
    environ = {"BD_HOME": "", "CLAUDE_SKILL_DIR": "", "CLAUDE_PLUGIN_ROOT": ""}
    home, source = B.resolve_bd_home(environ=environ, file_hint=HINT)
    _assert_home(home, source, "file_relative", REPO_ROOT)


def test_t5_explicit_but_unusable_raises_without_fallback():
    """T5: the direct red for decision point A. BD_HOME points at a tempdir with no
    scripts/breakingdiff.py, while a usable CLAUDE_SKILL_DIR sits behind it — an
    implementation that degrades silently returns (repository root, "skill_dir") instead
    of raising, and goes red here at once. The error message must also name the env
    source; whoever debugs it has to see which level killed the resolution."""
    B = _load()
    etype = _get_error_type(B)
    with tempfile.TemporaryDirectory() as td:
        environ = {"BD_HOME": td, "CLAUDE_SKILL_DIR": REPO_ROOT}
        try:
            got = B.resolve_bd_home(environ=environ, file_hint=HINT)
        except etype as e:
            _assert_error_shape(e, anchors=("env", "BD_HOME"))
        except Exception as e:
            raise BdPathsTestError(
                f"[bd_paths_test] T5 raised {type(e).__name__} instead of BdPathError: {e!r}"
                " — the exception type is part of the contract") from e
        else:
            raise BdPathsTestError(
                f"[bd_paths_test] T5 decision point A: BD_HOME={td} has no "
                f"scripts/breakingdiff.py, yet it raised no BdPathError and returned {got!r}"
                " — explicitly set but with an unusable candidate must raise at once, never degrade into the next level")


def test_t6_all_unset_and_dead_file_hint_raises():
    """T6: all four levels come up empty. The three env levels are not in the dict;
    walking two levels up from file_hint (i.e. an empty tempdir) leaves the candidate
    unusable — the file_relative fallback is unusable too, so it must raise and stop,
    never guess cwd or fall back to cwd. The intermediate directories hint points at are
    not really created: the contract takes only the two levels above hint, which also
    blocks out-of-bounds behavior such as "the implementation stats hint itself"."""
    B = _load()
    etype = _get_error_type(B)
    with tempfile.TemporaryDirectory() as td:
        hint = os.path.join(td, "a", "b", "bd_paths.py")
        dead_root = os.path.dirname(os.path.dirname(hint))
        try:
            got = B.resolve_bd_home(environ={}, file_hint=hint)
        except etype as e:
            _assert_error_shape(e, anchors=("file_relative",))
        except Exception as e:
            raise BdPathsTestError(
                f"[bd_paths_test] T6 raised {type(e).__name__} instead of BdPathError: {e!r}"
                " — the exception type is part of the contract") from e
        else:
            raise BdPathsTestError(
                f"[bd_paths_test] T6: all four levels missed (two levels up from hint is {dead_root}"
                f" with no scripts/breakingdiff.py), yet it returned {got!r} instead of raising "
                "BdPathError — an unusable fallback must raise")


def test_r3_sources_enum_is_frozen_anchor():
    """R3 (B7 spec freeze §4): the SOURCES enum anchor. M-DIST2's bd_source enum check
    references the same single source (bd_paths.SOURCES) without copying literals — if
    the source drifts, the receipt enum drifts with it, and both the four values and
    their order are pinned. B6 already delivered this constant with matching values, so
    this case is currently green: it is a permanent anti-drift anchor, not a red-state
    assertion."""
    B = _load()
    assert B.SOURCES == ("env", "skill_dir", "plugin_root", "file_relative"), \
        f"[bd_paths_test] R3: SOURCES enum drifted, got {getattr(B, 'SOURCES', None)!r}"


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad, errs = [], []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS {name}")
        except (BdPathsTestError, AssertionError):
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

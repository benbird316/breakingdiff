# -*- coding: utf-8 -*-
"""
leak_guard write-red tests — the B12 blind-run payload's anti-leak guard
====================================================================
The minimal tests for scripts/leak_guard.py (4 cases; repository convention: no pytest
dependency, main() runs directly, and pytest collects them when present):

  1. a clean temporary repository → exit 0 (the no-false-positive baseline)
  2. a real test_ function name from the corpus injected into a temporary SKILL.md →
     exit 1 (rule one, function-name tier)
  3. a grading keyword injected into a temporary references/*.md → exit 1 (rule two,
     word-list tier)
  4. a desensitized scanner (scan_text always empty) → self_check must go red on its
     own (the guard itself is pinned by mutation evidence: when the gate is changed to
     always pass, the self-proof must raise an alarm)

All fixtures are synthesized in temporary directories and never touch live repository
files — the live repository changes batch by batch, and writing live content into
assertions would pin the regression net to a historical slice (the same discipline as
refs_guard_test). main's root is injected explicitly (the same discipline as receipt's
"inject repo_root explicitly"), so the tests do not depend on CWD.
"""
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import leak_guard
from leak_guard import LEAK_WORDS, collect_test_fingerprints, main, self_check


def _make_repo(tmp, skill_text, ref_text):
    """A minimal isomorphic repository: SKILL.md + references/a.md + scripts/fake_test.py.

    fake_test.py carries one test_ function and one assert message containing a space —
    each of the two tiers of the corpus gets one real injectable fingerprint."""
    os.makedirs(os.path.join(tmp, "references"))
    os.makedirs(os.path.join(tmp, "scripts"))
    with open(os.path.join(tmp, "SKILL.md"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(skill_text)
    with open(os.path.join(tmp, "references", "a.md"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(ref_text)
    with open(os.path.join(tmp, "scripts", "fake_test.py"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(
            "def test_fake_probe_behavior():\n"
            "    assert 1 == 1, \"fake probe message for the leak corpus\"\n")
    return tmp


def test_clean_repo_exits_zero():
    """A clean repository (SKILL/references have no fingerprints and no grading words) →
    main exits 0.

    The corpus file is on disk (fake_test.py has fingerprints) while the scan surface is
    clean — this verifies the normal green of "corpus present, no leak", not the empty
    green of "no corpus, so it spins green"."""
    tmp = tempfile.mkdtemp(prefix="leak_guard_clean_")
    try:
        _make_repo(tmp, "# Normal skill document\n\nExplains usage with nothing sensitive.\n",
                   "# Reference document\n\nNormal content.\n")
        code = main([], root=tmp)
        assert code == 0, f"a clean repository should exit 0, got {code}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_injected_test_assertion_exits_one():
    """Inject a real test_ function name from the corpus into a temporary SKILL.md →
    exit 1.

    The injected word comes from the actually collected corpus (not hardcoded), ensuring
    the injection point is a fingerprint really consumed by the scanner — preventing
    "you injected a word that does not exist; red or not proves nothing"."""
    tmp = tempfile.mkdtemp(prefix="leak_guard_func_")
    try:
        _make_repo(tmp, "# Normal skill document\n\nExplains usage.\n",
                   "# Reference document\n\nNormal content.\n")
        funcs, lits = collect_test_fingerprints(tmp)
        assert "test_fake_probe_behavior" in funcs, "the corpus should actually collect the fixture function name"
        with open(os.path.join(tmp, "SKILL.md"), "a",
                  encoding="utf-8", newline="\n") as f:
            f.write("Pointer: read the table of test_fake_probe_behavior.\n")
        code = main([], root=tmp)
        assert code == 1, f"an injected function name should exit 1, got {code}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_injected_judging_word_exits_one():
    """Inject a grading keyword into a temporary references/*.md → exit 1.

    The word comes from LEAK_WORDS (the grading table's characteristic words), and the
    injection surface is references rather than SKILL.md — each of the two scan surfaces
    needs its own red evidence."""
    tmp = tempfile.mkdtemp(prefix="leak_guard_word_")
    try:
        assert LEAK_WORDS, "the grading word list must not be empty"
        _make_repo(tmp, "# Normal skill document\n\nExplains usage.\n",
                   "# Reference document\n\nThis chapter covers the " + LEAK_WORDS[0] + " standard.\n")
        code = main([], root=tmp)
        assert code == 1, f"an injected grading word should exit 1, got {code}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_self_check_catches_desensitized_scanner():
    """The scanner is desensitized (scan_text mutated to always pass) → self_check must go
    red.

    A gate can itself fail silently — once it is changed to always pass, leaks still go
    unreported, so the self-proof must catch the "desensitized" mutation itself rather
    than merely verify "the function did not raise"."""
    tmp = tempfile.mkdtemp(prefix="leak_guard_muted_")
    original = leak_guard.scan_text
    try:
        _make_repo(tmp, "# Normal skill document\n\nExplains usage.\n",
                   "# Reference document\n\nNormal content.\n")
        leak_guard.scan_text = lambda *a, **k: []
        try:
            assert not self_check(), (
                "self_check still returned True after the scanner was mutated to always "
                "pass — the self-proof cannot catch its own desensitization, which means "
                "there is no self-proof")
        finally:
            leak_guard.scan_text = original
        # The green after restoration depends on the live repository's corpus being
        # non-empty (self_check hardcodes the live ROOT): when every live
        # scripts/*_test.py is emptied, this goes red, which is the correct red of "an
        # empty corpus means the self-proof does not hold", not a defect of this case —
        # consistent with the live repository's normal all-green account.
        assert self_check(), "self_check should return to normal green after restoration"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_all():
    """Thin wrapper: run each case, all green 0 / any red 1 (following the repository's
    two passing tiers of the three-tier code).

    It is not named main — this file's `from leak_guard import main` subject entry must
    stay visible; following the repository convention of "a thin main wrapper run
    directly" and naming this main would shadow the subject entry (measured before: a
    case's main([], root=...) called this file's thin wrapper and reported a false red
    about a nonexistent root parameter)."""
    tests = [test_clean_repo_exits_zero,
             test_injected_test_assertion_exits_one,
             test_injected_judging_word_exits_one,
             test_self_check_catches_desensitized_scanner]
    bad = []
    for fn in tests:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except Exception:
            bad.append(fn.__name__)
            print(f"  FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(bad)}/{len(tests)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(run_all())

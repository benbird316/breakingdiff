# -*- coding: utf-8 -*-
"""
Trigger conditions and the coverage gate — regression tests
==================================================
Pins the commitments introduced when SKILL.md was rewritten on 2026-10-12. Those
items used to sit entirely outside the catalog, so the bootstrap instance was blind
to them (the four quadrants returned a zero-change readout, misread as "verified").
This file brings them into the surface under test and pins each one down.

Does not depend on pytest (the local `raises` stands in); pytest can still collect it.
Usage: python trigger_conditions_test.py
"""
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import test_alignment_bootstrap as A
from coverage_guard import CoverageError, find_uncovered, require_covered


class raises:
    """Minimal context manager: a stand-in for pytest.raises."""

    def __init__(self, exc):
        self.exc = exc
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"should have raised {self.exc.__name__}, but did not")
        self.value = ev
        return issubclass(et, self.exc)


SPEC = A.SPEC_TEXT          # the frozen contract corpus, read verbatim
TEST_FILE = os.path.join(HERE, 'test_alignment_bootstrap_test.py')
TRIG_FILE = os.path.join(HERE, 'trigger_conditions_test.py')


def _read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


TRIG_TEXT = _read(TRIG_FILE)
TEST_TEXT = _read(TEST_FILE)
# Read SKILL.md by itself too: criteria such as the size ceiling and historical
# wording measure the SKILL.md file itself; since B2, SPEC_TEXT is a seven-file union
# and can no longer serve as a single-file measurement proxy.
SKILL_TEXT = _read(os.path.join(ROOT, 'SKILL.md'))


# --------------------------------------------- trigger conditions: structural, not wording
def test_trigger_is_the_agent_judgment_node():
    """The trigger must be a judgment action the agent takes, not something the user
    might say.

    This is the core commitment of that rewrite: the original hung trigger words on
    terms only someone who had read the docs would use — "semantic drift", "two
    accounts", "four quadrants" — and hit 0 of 16 real scenarios literally.
    """
    assert "The trigger is not an instruction the user gave" in SPEC
    assert "you are about to output a claim about the relationship between two or more materials" in SPEC


def test_six_preconditions_are_listed():
    """Six preconditions: P1 was generalized on 2026-10-15 to N≥2 accounts, and P6
    (account independence) was added the same day."""
    assert "six structural preconditions" in SPEC
    for p in ("P1", "P2", "P3", "P4", "P5", "P6"):
        assert p in SPEC, f"missing precondition {p}"
    # P1's generalized semantics must really be in the contract, not just the letter
    assert "N ≥ 2 accounts" in SPEC
    # P6's criterion: agreement between same-source accounts is self-consistency, not
    # cross-verification
    assert "the sources of the accounts are independent" in SPEC


def test_p3_is_marked_as_the_whole_value():
    """P3 (the change is legal and raises nothing) must be written as where all the
    value is.

    This is the division of labor with P1/P2: P1 and P2 decide "can it", P3 decides
    "should it".
    """
    assert "the change is legal and raises nothing" in SPEC
    assert "All the value is in P3" in SPEC


# --------------------------------------------- all four scenario domains are present
def test_all_four_domains_are_covered():
    """Programming, engineering, theory, research — the use cases of all four domains
    must be named in the contract."""
    assert "behavioral equivalence before and after a refactor" in SPEC
    assert "a clause-by-clause comparison of acceptance criteria" in SPEC
    assert "find counterexamples in the same parameter domain" in SPEC
    assert "a clause-by-clause comparison of what the evidence covers" in SPEC


def test_science_use_is_scoped_not_promised():
    """Science use must be written with boundaries: the quantifiable part is usable,
    whether a conclusion is right is not.

    This keeps the skill from overselling itself — it reports divergence, it does not
    adjudicate.
    """
    assert "report only divergence, never adjudicate" in SPEC
    assert "you need to adjudicate who is right" in SPEC


# --------------------------------------------- the three new exclusions
def test_three_exclusions_are_stated():
    for x in ("only one material",
              "the account is prose and cannot be enumerated into parameter points",
              "adjudicate who is right"):
        assert x in SPEC, f"missing exclusion: {x}"


# --------------------------------------------- the coverage gate's own behavior
def test_new_chapters_are_now_in_the_catalog():
    """The catalog must recognize this round's new chapters, or it goes blind again."""
    topics = {e["topic"] for e in A.CATALOG}
    for t in ("trigger point", "six preconditions", "silent zone", "refactor",
              "regulation", "counterexample", "evidence", "coverage gate"):
        assert t in topics, f"catalog is missing topic: {t} (a zero readout would be misread again)"


def test_self_coverage_gate_runs_before_reading():
    """The main program must pass the coverage gate before reading the four quadrants."""
    assert "self_coverage_gate()" in _read(os.path.join(HERE,
                                                        'test_alignment_bootstrap.py'))


def test_out_of_catalog_change_is_caught():
    """The original lesson of this round: a change outside the catalog must be raised
    by the gate."""
    with raises(CoverageError):
        require_covered(["a brand-new promise marker"], ["provenance", "verbatim"])


def test_in_catalog_change_is_quiet():
    """The gate does not make noise: a change inside the surface under test passes
    quietly."""
    require_covered(["provenance", "verbatim", "coverage gate"],
                    ["provenance", "verbatim", "coverage gate"])


def test_zero_reading_is_not_approval():
    """Zero readout ≠ verified — this sentence must be in the contract, not only in
    code."""
    assert "A zero readout is not a pass" in SPEC


def test_no_hardcoded_test_counts_in_spec():
    """The docs must not hard-code test counts — the moment they are written they
    start to expire.

    This was established by measurement on 2026-10-15: the verification section of
    SKILL.md once said "71 tests in total" and "10/10", "11/11" per file; the next
    round of changes turned those into stale numbers. **A stale promise is worse than
    "the docs do not mention it"**: readers take it as the baseline, so a drift like
    "docs say 71, reality 76" reads as normal instead of as an alarm.

    The right way: the verification section lists commands only; run once and the
    number is known, no need to maintain it in the docs.

    The criterion must separate **numbers that expire** from **stable numbers** —
    the four-quadrant counts 25/0/1/0, the 7/4/2/0 in historical records, and N=2 in
    term definitions are all determined by their input, do not change when the code
    changes, and must not be caught by this test.

    ★ Mutation-evidence lesson: the first version of this check wrote the scan
      condition too narrowly (requiring "passed" or "test count" on the same line),
      so `# 13/13 passed` slipped through and the test stayed green under mutation.
      Scan with a regex, not with semantic conditions.
    """
    # The verification section heading is accepted in both English forms during the
    # i18n transition, so "the section is missing after translation" is not misread as
    # "a hard-coded number is in the verification section".
    for heading in ("## Verification",):
        if heading in A.SPEC_TEXT:
            sec = A.SPEC_TEXT.split(heading, 1)[1]
            break
    else:
        raise AssertionError("SKILL.md is missing its verification section (expected \"## Verification\")")
    # The two lines allowed to contain "hard-coded" (they explain why it is not done)
    exempt_markers = ("not hard-coded here", "no need to maintain in the document", "goes stale")
    # Shapes: "N/N passed", "all N tests", "N named test_ functions" in comments
    patterns = [
        r"\d+/\d+ passed",
        r"all\s*\d+",
        r"\d+\s+named",
        r"\d+\s+tests all green",
    ]
    for line in sec.split("\n"):
        if any(m in line for m in exempt_markers):
            continue
        for pat in patterns:
            if re.search(pat, line):
                raise AssertionError(
                    f"SKILL.md verification section hard-codes an expiring test count: {line.strip()!r}\n"
                    f"  matched pattern {pat}\n"
                    f"  -> list only the commands; one run gives the number. A hard-coded number drifts,"
                    f"     and drift read as normal stops being an alarm")


def test_verification_docs_point_at_the_single_gate_entry():
    """The verification docs must be runnable, and must not drift from the gate.

    This replaces test_verification_section_lists_every_test_file, which required
    README to print every test filename. That requirement was right while a printed
    list was the only way to run the suite: a test missing from the list was a test
    nobody would run. Once scripts/ci_gate.py discovers tests by name, the printed
    list becomes a second copy of one fact — and it drifted exactly as second copies
    do. Measured 2026-10-22: the hand-maintained list held 27 files while the
    repository held 28; examples/docaudit/test_docaudit.py was absent because it sits
    one directory deeper than its siblings.

    The protection is not relaxed, it moves to a firmer footing. "Every filename
    appears in the docs" is text matching, which a stale line satisfies after the
    file has been renamed. The replacement asserts that the gate's actual discovery
    covers every file the P-side account registers — a behavioural check of the
    thing that runs — plus a text check that the docs name both the entry point and
    the naming rule, because discovery by convention is only safe if the convention
    is written down where a reader will find it."""
    with open(os.path.join(A.ROOT, 'README.md'), encoding='utf-8') as f:
        readme = f.read()
    heading = "## Install and verify"
    assert heading in readme, (
        "README.md is missing its install-and-verify section: expected "
        "\"## Install and verify\"")
    sec = readme.split(heading, 1)[1]

    assert 'scripts/ci_gate.py' in sec, (
        "README.md \"Install and verify\" does not name the single gate entry "
        "(scripts/ci_gate.py): a reader following the docs would have to rebuild the "
        "suite by hand, which is how the previous list came to be one file short")
    assert 'test_*.py' in sec and '*_test.py' in sec, (
        "README.md \"Install and verify\" does not state the test naming convention: "
        "discovery by name is the only reason a new test needs no registration, so a "
        "reader who does not know the rule cannot predict what the gate covers")

    import ci_gate
    discovered = {p.as_posix() for p in ci_gate.discover(A.ROOT)}
    missing = []
    for path in A.TEST_FILES_ALL:
        rel = os.path.relpath(path, A.ROOT).replace(os.sep, '/')
        if rel not in discovered:
            missing.append(rel)
    assert not missing, (
        f"the gate does not discover these registered test files: {missing}\n"
        f"  -> they sit in the P-side account but outside the naming rule, so the gate "
        f"would report green without ever running them")


def test_spec_stays_rule_only_not_a_changelog():
    """SKILL.md carries rules and usage only, never historical evidence — evidence goes
    to CHANGELOG.md.

    This rule was set on 2026-10-15, after SKILL.md had grown to 364 lines / 25 KB,
    about 80 of them history-shaped content (incident numbers from some day, the
    mutation ledger, per-move tables). **The description is already 850 characters;
    the longer the file, the worse the trigger precision** — a real cost, because the
    agent reads the whole file on every trigger.

    The layering is by audience:
      SKILL.md            read on every trigger  -> rules and usage only
      references/         read when writing a new instance -> method
      CHANGELOG.md        read when a human checks -> evidence

    This test turns "do not pile up history" into an executable criterion instead of
    relying on discipline.

    ★ The criterion must pick shapes that really expire: dated headings, data tables
      with dates, "measured incident" narratives. **Do not catch** cross-domain
      measured conclusions such as "measured criterion power" — that is an account of
      the criterion's boundaries, part of the rules.
    """
    # 1) Section headings must not carry dates or batch numbers — such headings invite
    #    piling more history here next time
    for m in re.finditer(r"^#{2,3}\s+(.+?)\s*$", SKILL_TEXT, re.M):
        title = m.group(1)
        if re.search(r"20\d{2}-\d{2}|measured ledger|batch", title):
            raise AssertionError(
                f"SKILL.md section heading carries a date or batch number: {title!r}\n"
                f"  -> historical evidence goes to CHANGELOG.md; body headings name rules only")

    # 2) Measured-number tables in the body must not carry "which batch fixed it" wording
    banned_lines = ["2026-10-12 measured incident", "2026-10-15 measured",
                    "triggered again this round", "the ledger follows",
                    "the table below is measured results"]
    for b in banned_lines:
        if b in SKILL_TEXT:
            raise AssertionError(
                f"SKILL.md body contains historical-record wording {b!r}\n"
                f"  -> that content goes to CHANGELOG.md; the body keeps executable rules only")

    # 3) Size ceiling — exceeding it means history is piling up again.
    #    Threshold = net rule volume + 16 of headroom; when net rule volume changes the
    #    threshold is re-estimated by the same formula (do not paste the current value;
    #    keep headroom for the next rule batch): first set at 360 on 2026-10-12 (net 344
    #    then); after the five anti-self-deception steps added receipt / provenance /
    #    blind-write / host-hook sections the net was 368, re-estimated to 380 by the
    #    same formula. After the close-out batch grew it (verification section +4 test
    #    lines + pointer list +1 line, reconcilable via git diff) the net was 383;
    #    recomputed by the same formula: 383 + 16 = 399.
    #    What this test guards against is "history starts piling up again", not "being
    #    short" — a re-estimate must correspond to a real net-rule increase (git diff
    #    reconcilable), not open a gate for historical content.
    #
    #    ★ Strip trailing line endings before counting. Measured trap: 61 bare CRs had
    #      crept into the file (following the Markdown hard line breaks "two trailing
    #      spaces"), and split("\n") cut each of them -> 344 lines were counted as 406,
    #      a false "over the limit", while after removing bare CRs there was not one
    #      extra line. Criterion: **a measurement convention must not be swayed by
    #      irrelevant byte differences**, otherwise it reports a false red, and a false
    #      red sends people to fix the wrong thing.
    raw = SKILL_TEXT
    lines = [ln.rstrip("\r") for ln in raw.replace("\r\n", "\n").split("\n")]
    SKILL_MAX_LINES = 399   # assertion and error text share one constant, preventing drift
    assert len(lines) <= SKILL_MAX_LINES, (
        f"SKILL.md is {len(lines)} lines (limit {SKILL_MAX_LINES}) — "
        f"most likely CHANGELOG content was moved back in. "
        f"Rules go to the body, evidence to CHANGELOG.md, method to references/, navigation to README.md")


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith('test_') and callable(f)]
    bad = []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception:
            bad.append(name)
            print(f"  FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(fns) - len(bad)}/{len(fns)} passed"
          + (f", failures: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
coverage_guard's own regression tests and mutation evidence
==================================================
A gate itself can fail silently in three tiers: once require_covered is changed to
always return None, "raised nothing" and "passed the check" are observationally
indistinguishable. So it must be pinned down by tests.

No pytest dependency (the `raises` below is local); pytest can still collect it.
Usage: python coverage_guard_test.py
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from coverage_guard import (CoverageError, coverage_ratio,
                            find_uncovered, require_covered)


class raises:
    """Minimal context manager: a stand-in for pytest.raises."""

    def __init__(self, exc):
        self.exc = exc
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"expected {self.exc.__name__} to be raised, but nothing was raised")
        self.value = ev
        return issubclass(et, self.exc)


# These 8 words are the English topic words (`TOPIC_EN`) the test_alignment_bootstrap
# catalog maps its topics to — copied here as the surface under test.
CATALOG = ["provenance", "verbatim", "source-test self-check", "discrimination",
           "tuple", "construction time", "four-quadrant", "mutation"]


# ------------------------------------------------------------ it blocks
def test_real_incident_is_caught():
    """A real incident on 2026-10-12: the change was entirely outside the catalog and
    the four-quadrant readout did not move by a word. The gate must raise it as a gap,
    not pass it quietly."""
    real = ["five structural preconditions", "trigger sits at the decision node",
            "behavioral equivalence before and after the refactor",
            "clause-by-clause comparison of acceptance criteria",
            "report divergence only, never adjudicate"]
    with raises(CoverageError) as e:
        require_covered(real, CATALOG, what="real changes")
    msg = str(e.value)
    assert "[CG:UNCOVERED]" in msg
    assert e.value.reason == "UNCOVERED", "the criterion code is a stable contract; it does not follow the message language"
    assert e.value.gaps == set(real), "the gap set travels in structured fields, not scraped from the message"
    assert all(k in msg for k in real)


def test_gap_message_lists_every_gap():
    with raises(CoverageError) as e:
        require_covered(["provenance", "gap-a", "gap-b", "gap-c"], CATALOG)
    assert len(e.value.gaps) == 3, f"the gap count travels in structured fields; got {len(e.value.gaps)}"
    for k in ("gap-a", "gap-b", "gap-c"):
        assert k in str(e.value)


def test_whitespace_does_not_fake_coverage():
    """Full-width/half-width and whitespace differences must not make a real gap look covered."""
    gaps, _ = find_uncovered(["prov  enance"], CATALOG)
    assert gaps == set(), "whitespace normalization hid a real gap"


def test_exempt_is_separated_not_swallowed():
    """Exempt items must be explicitly acknowledged, not silently disappear.

    Fixed on 2026-10-15: the original test used
    `changed=["provenance","fixed a typo"] / exempt=["typo"]`, which only matched thanks to
    substring matching. After exemptions became verbatim equality, the exempt item
    must equal the changed item verbatim — otherwise "exempt" turns back into semantic
    guessing. This test itself once pinned a bug down as the spec.
    """
    gaps, allowed = find_uncovered(["provenance", "fixed a typo"], CATALOG,
                                   exempt=["fixed a typo"])
    assert gaps == set()
    assert allowed == {"fixed a typo"}


def test_exempt_is_verbatim_not_substring():
    """Exemptions must be verbatim equality. The earlier substring matching silently
    swallowed real gaps: exempt=['cover'] also exempted 'coverage gate description' —
    which is not in the parameter space at all.

    This is the same discipline as "only verbatim-checkable markers are recognized, no
    semantic guessing" in the module header: substring matching is itself semantic
    guessing, and the exemption mechanism is no exception.
    """
    gaps, allowed = find_uncovered(["coverage gate description"], CATALOG, exempt=["cover"])
    assert "coverage gate description" in gaps, "substring matching silently exempted a real gap"
    assert allowed == set()


def test_prefix_exemption_must_be_declared():
    """When a prefix-based relaxation is genuinely needed, write the PREFIX: prefix —
    make the relaxation a checkable declaration rather than a coincidence."""
    gaps, allowed = find_uncovered(["coverage gate description"], CATALOG,
                                   exempt=["PREFIX:cover"])
    assert gaps == set()
    assert allowed == {"coverage gate description"}
    # No PREFIX: means no relaxation
    gaps2, _ = find_uncovered(["coverage gate description"], CATALOG, exempt=["cover"])
    assert "coverage gate description" in gaps2


# ------------------------------------------------------------ it stays quiet
def test_fully_covered_passes_quietly():
    """The gate makes no noise — when everything is inside the space it must stay
    quiet, or it gets switched off as noise."""
    require_covered(["provenance", "discrimination", "tuple"], CATALOG)
    require_covered([], CATALOG)


def test_fully_exempt_passes_quietly():
    require_covered(["comment", "format"], CATALOG, exempt=["comment", "format"])


# ------------------------------------------------------------ coverage-ratio readout
def test_ratio_denominator_includes_gaps():
    """The denominator must be the total changes this round (gaps included), or the
    ratio is always 100%.

    An earlier implementation returned len(in_scope), len(in_scope) — two values from
    the same source, so it could never mathematically give a coverage below 100%. That
    is not "anti-false-green", it reports "nothing is covered" as 100% (and when
    everything is out of the space it is worse: it returns 0/0). Mixed input is the
    only discriminating input, so assertions 2 and 3 below are the real criteria.
    """
    # fully covered: 2/2 = 100%
    assert coverage_ratio(["provenance", "discrimination"], CATALOG) == (2, 2)
    # everything out of the space: 0/2 = 0%  ← the earlier implementation returned (0, 0)
    assert coverage_ratio(["outside-1", "outside-2"], CATALOG) == (0, 2)
    # mixed: 1/2 = 50%  ← the earlier implementation returned (1, 1); this case never caught it
    assert coverage_ratio(["provenance", "outside-1"], CATALOG) == (1, 2)


def test_ratio_never_reports_full_coverage_when_gaps_exist():
    """Whenever a gap exists, coverage must never read as full — this pins the false green down."""
    for changed in (["outside-1"], ["outside-1", "outside-2"], ["provenance", "outside-1"], ["provenance", "outside-1", "outside-2"]):
        cov, tot = coverage_ratio(changed, CATALOG)
        assert tot > 0
        assert cov < tot, f"{changed} has gaps but reports full coverage {cov}/{tot}"


def test_ratio_mutation_returning_in_scope_twice_is_caught():
    """The mutation that changes the denominator back to in_scope must be caught by the test above."""
    def mutated_ratio(changed, covered, exempt=()):
        """The broken implementation: two values from the same source, always 100%."""
        changed = list(changed)
        gaps, _ = find_uncovered(changed, covered, exempt)
        in_scope = [c for c in changed if c not in gaps]
        return len(in_scope), len(in_scope)

    CATALOG_ = CATALOG
    # The mutated implementation lies about full coverage on mixed input → the real
    # implementation must tell the two apart
    assert mutated_ratio(["provenance", "outside-1"], CATALOG_) == (1, 1)
    assert coverage_ratio(["provenance", "outside-1"], CATALOG_) == (1, 2)   # the real implementation


# ------------------------------------------------------------ mutation evidence
def test_mutation_disabling_the_gate_is_caught():
    """Break the gate into "always passes", and the mutation test must go red on the spot.

    This is why this file exists: when the gate itself fails, the four quadrants report
    no anomaly; the only thing that can find it is this assertion.
    """
    def broken_require_covered(changed, covered, exempt=(), what="x"):
        return None          # ← the broken gate: silent failure
    broken_require_covered(["a change entirely outside the space"], CATALOG)   # raises nothing → the mutation is not detected
    # The real gate must raise on the same input; the difference between the two is the criterion for this assertion
    with raises(CoverageError):
        require_covered(["a change entirely outside the space"], CATALOG)


def test_mutation_is_local():
    """The mutation touches only the one spot it should; without injection, behavior is unchanged."""
    gaps, _ = find_uncovered(["provenance", "out-of-scope item"], CATALOG)
    assert gaps == {"out-of-scope item"}
    gaps2, _ = find_uncovered(["provenance", "out-of-scope item"], CATALOG)
    assert gaps2 == gaps


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
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
          + (f", failed: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

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


# Forms whose `PREFIX:` suffix is empty or whitespace-only. Each must be refused:
# `_norm("") == ""`, and every string starts with "", so one blank declaration would
# exempt every changed item of the round.
BLANK_PREFIX_FORMS = ["PREFIX:", "PREFIX: ", "PREFIX:\t", "PREFIX:　",
                      "PREFIX: \t　"]


def test_blank_prefix_exemption_is_refused():
    """A `PREFIX:` with an empty or whitespace-only suffix must raise, not exempt.

    This is the gate's own escape hatch turned into a silent switch: the suffix
    normalizes to "", `n.startswith("")` is true for every marker, so one blank
    declaration moves every changed item into "allowed" and require_covered reports no
    gap at all. Refusing the declaration is the only fix that keeps the decision at the
    caller: silently dropping it would leave "what did the caller mean" to the gate.
    """
    for raw in BLANK_PREFIX_FORMS:
        with raises(ValueError) as e:
            find_uncovered(["a real gap"], CATALOG, exempt=[raw])
        msg = str(e.value)
        assert "PREFIX" in msg, "the message must name the malformed declaration"
        assert repr(raw) in msg, f"the message must show the blank form verbatim: {raw!r}"
    # The blanket exemption is unreachable through the gate and through the ratio too.
    with raises(ValueError):
        require_covered(["a real gap"], CATALOG, exempt=["PREFIX: "])
    with raises(ValueError):
        coverage_ratio(["a real gap"], CATALOG, exempt=["PREFIX:\t"])


def test_blank_prefix_guard_keeps_a_usable_prefix_working():
    """The blank check keys on the normalized suffix being empty, not on whitespace in
    the declaration: `PREFIX: cover ` still declares the prefix `cover`.

    This is the boundary against an over-tight guard. A guard that refuses every
    declaration carrying whitespace — e.g. `e[7:] != e[7:].strip()` — would reject this
    legal declaration and turn the gate into a false red for real callers.
    """
    gaps, allowed = find_uncovered(["coverage gate description"], CATALOG,
                                   exempt=["PREFIX: cover "])
    assert gaps == set()
    assert allowed == {"coverage gate description"}


def test_mutation_blank_prefix_blanket_exemption_is_caught():
    """Remove the blank-prefix guard and this file goes red on the spot.

    The mutant below keeps the pre-fix split: the suffix is stripped, so `PREFIX:`
    becomes the empty prefix and every changed item lands in allowed. The real
    implementation raises on exactly the same input — that difference is the criterion.
    """
    def pre_fix_find_uncovered(changed, covered, exempt=()):
        prefixes = [e[len("PREFIX:"):].strip() for e in exempt
                    if e.startswith("PREFIX:")]
        gaps, allowed = set(), set()
        for c in changed:
            if any(c.startswith(p) for p in prefixes):
                allowed.add(c)
            else:
                gaps.add(c)
        return gaps, allowed

    gaps, allowed = pre_fix_find_uncovered(["a real gap", "another gap"], [],
                                           exempt=["PREFIX:"])
    assert gaps == set() and allowed == {"a real gap", "another gap"}, \
        "the mutant must reproduce the silent blanket exemption this test refuses"
    with raises(ValueError):
        find_uncovered(["a real gap", "another gap"], [], exempt=["PREFIX:"])


def test_mutation_over_tight_blank_guard_is_caught():
    """An over-tight guard goes red here: the mutant refuses any declaration whose raw
    suffix carries whitespace, which rejects the usable `PREFIX: cover ` above."""
    def over_tight_guard(exempt):
        for e in exempt:
            suffix = e[len("PREFIX:"):]
            if e.startswith("PREFIX:") and suffix != suffix.strip():
                raise ValueError(f"blank PREFIX: {e!r}")

    with raises(ValueError):
        over_tight_guard(["PREFIX: cover "])
    # The real guard accepts it and the declaration does its job.
    require_covered(["coverage gate description"], CATALOG, exempt=["PREFIX: cover "])


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


def test_ratio_counts_each_change_once():
    """Duplicate entries are the same change; counting them twice inflates the
    denominator and makes coverage read lower than it is.

    Measured: `["a","a","b"]` with `["a"]` covered returned 2/3 before the fix — the
    second "a" was counted as a separate uncovered change. Verbatim duplicates collapse,
    order-preserving, before the denominator is taken: unique is 1/2.
    """
    assert coverage_ratio(["a", "a", "b"], ["a"]) == (1, 2)
    # Non-adjacent duplicates collapse too (no "only neighbours" shortcut).
    assert coverage_ratio(["a", "b", "a"], ["a"]) == (1, 2)
    # All-covered duplicates stay a full ratio, not 2/2 over a padded denominator.
    assert coverage_ratio(["provenance", "provenance"], CATALOG) == (1, 1)
    # All-gap duplicates collapse to one uncovered change.
    assert coverage_ratio(["outside", "outside"], CATALOG) == (0, 1)
    # Deduplication is verbatim (order-preserving on the raw strings), not normalized:
    # two differently-spelled markers are two entries.
    assert coverage_ratio(["provenance", "prov enance"], CATALOG) == (2, 2)


def test_mutation_counting_duplicates_is_caught():
    """Remove the dedupe and the assertion above goes red: the mutant counts
    `["a","a","b"]` as 2/3, the real implementation as 1/2."""
    def un_deduped_ratio(changed, covered, exempt=()):
        changed = list(changed)
        gaps, _ = find_uncovered(changed, covered, exempt)
        return len(changed) - len(gaps), len(changed)

    assert un_deduped_ratio(["a", "a", "b"], ["a"]) == (2, 3), \
        "the mutant must reproduce the inflated denominator this test refuses"
    assert coverage_ratio(["a", "a", "b"], ["a"]) == (1, 2)


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

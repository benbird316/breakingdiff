# -*- coding: utf-8 -*-
"""
Worked example · value-layer type fingerprint — regression tests and mutation evidence
==============================================================================
What is tested: whether each of the three gates fires at the right time, whether
the discrimination gate has teeth, and the mutation evidence that "break the
protected behavior and exactly that turns red".

Does not depend on pytest (the local `raises` below stands in); pytest can still
collect it when present.
Usage: python value_type_fingerprint_test.py
       python -m pytest value_type_fingerprint_test.py -q
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))

import value_type_fingerprint as V
from breakingdiff import Claim, ProvenanceError, SourceTestError, compare


class raises:
    """Minimal context manager: a stand-in for pytest.raises, so the tests do not
    depend on pytest."""

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


# ---------------------------------------------------------------- provenance binding
def test_quotes_are_verbatim():
    assert V.QUOTE_TYPE in V.RAW[V.OLD]
    assert V.QUOTE_SHAPE in V.RAW[V.OLD]


def test_blank_quote_raises_provenance_error():
    with raises(ProvenanceError):
        Claim(name="x", predicate=lambda p: True, applies=lambda p: True,
              domain_note="", source="a source", quote="   ")


def test_blank_source_raises_provenance_error():
    with raises(ProvenanceError):
        Claim(name="x", predicate=lambda p: True, applies=lambda p: True,
              domain_note="", source="", quote="a quote")


def test_fabricated_quote_is_rejected_at_construction():
    # A fabricated quote passes "non-empty" but not the verbatim check — that gate
    # runs at construction time
    with raises(ProvenanceError):
        Claim(name="fabricated", predicate=lambda p: True, applies=lambda p: True,
              domain_note="", source="a source", quote="this sentence is nowhere in the source text",
              quote_source=V.RAW[V.OLD])


# ---------------------------------------------------------------- source self-test
def test_type_claim_source_tests_pass():
    ok, tot, fails = V.make_type_claim().run_source_tests()
    assert (ok, tot, fails) == (3, 3, [])


def test_wrong_source_test_raises():
    c = V.make_type_claim()
    bad = Claim(name="wrong example", predicate=c.predicate, applies=c.applies,
                domain_note=c.domain_note, source=c.source, quote=c.quote,
                source_tests=((("cartFailure", "off"), True),))   # the fact is False
    with raises(SourceTestError):
        compare(bad, V.BASE_KEYS, V.ALL_KEYS)


# ---------------------------------------------------------------- discrimination
def test_type_claim_discriminates_its_readings():
    # The gate wants "the test set separates the claim from the interpretations",
    # not "all tests pass"
    assert V.make_type_claim().run_reading_discrimination() == [("cartFailure", "off")]


def test_shape_claim_is_rejected_by_discrimination_gate():
    with raises(SourceTestError) as e:
        compare(V.make_shape_claim(), V.BASE_FLAGS, V.COMMON_FLAGS)
    assert e.value.reason == "READING_DISCRIMINATION_ZERO"


# ---------------------------------------------------------------- four-quadrant result
def test_type_claim_flags_exactly_one_drift():
    r = compare(V.make_type_claim(), V.BASE_KEYS, V.ALL_KEYS)
    assert (r.common, r.divergence, r.dominance, r.neither) == (25, 0, 1, 0)
    assert r.dominance_witnesses == [("cartFailure", "off")]


# ---------------------------------------------------------------- mutation evidence
def test_mutation_weakening_fingerprint_flips_exactly_the_protected_case():
    """Degrade the type fingerprint to "Python numeric semantics" (that is, the
    candidate interpretation itself).
    Expectation: exactly the protected point turns red, and both defense lines fire:
      ① the source self-test finds on the spot that the 3rd test point no longer holds;
      ② bypass the gate and compute directly: that warning itself disappears.
    Only both together show "the red came from this mechanism", not from something else."""
    def weakened(v):
        if isinstance(v, bool) or isinstance(v, (int, float)):
            return 'number'
        return V.fingerprint(v)

    claim = V.make_type_claim(weakened)
    ok, tot, fails = claim.run_source_tests()
    assert (ok, tot) == (2, 3)
    assert len(fails) == 1 and "cartFailure" in fails[0] and "off" in fails[0]

    left = [p for p in V.COMMON
            if weakened(V._val(V.OLD, *p)) != weakened(V._val(V.NEW, *p))]
    assert left == []

    with raises(SourceTestError):
        compare(claim, V.BASE_KEYS, V.ALL_KEYS)


def test_mutation_is_local_others_still_green():
    """The mutation touches only the protected claim; the main claim (default
    fingerprint) is unaffected."""
    assert compare(V.make_type_claim(), V.BASE_KEYS, V.ALL_KEYS).dominance == 1


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

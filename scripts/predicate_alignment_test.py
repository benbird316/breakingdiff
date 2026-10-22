# -*- coding: utf-8 -*-
"""
predicate_alignment red-first tests (1.3 predicate distortion self-check · dual calibration points)
==========================================================
Frozen contract (this repository's refinement plan landing batch §1.3; see the
matching CHANGELOG.md entry):
  · an independent helper check_predicate_alignment(P, Q, pre_point, post_point),
    not stuffed into the Claim dataclass;
  · a self-check before compare: P and Q predicates all false against both
    calibration fixtures (known pre-change state + known post-change state) →
    report "predicate distortion" and block, do not land in neither;
  · calibration points do not enter the four-quadrant counts;
  · the calibration gate must itself carry mutation evidence: break the predicate's
    key-shape expectation and the calibration gate must go red.

This file is a red-first test: scripts/predicate_alignment.py did not exist yet, and
each test goes explicitly red with NotImplementedError (each red cause maps to a
contract clause, see the section headings in the module docstring). Once the
implementation lands, the guard stops applying automatically and all assertions
below take real effect — no always-true placeholder anywhere.

Test contract (the API shape the implementation must obey, frozen by this test):

    from predicate_alignment import check_predicate_alignment
    res = check_predicate_alignment(P, Q, pre_point, post_point)

  · res.aligned  : bool   True = calibration passed; False = predicate distortion
  · res.blocking : bool   True on distortion (blocking semantics: the caller must
                          not continue with compare); False on pass
  · res.message  : str    a readable message on distortion, must contain
                          "predicate distortion"
  · the returned object must not carry four-quadrant semantics: it is not a
    DiffResult and has no common/divergence/dominance/neither/out_of_domain
    fields — calibration points do not enter the four-quadrant counts.

Fixture design (domain-agnostic minimal shape, mapping one class of real distortion:
key-shape 2-tuple → 3-tuple, P/Q are both membership checks, both false against the
post-change cache):
  PRE_POINT / POST_POINT are two parameter points and the predicates are membership
  checks. When the predicate's key-shape expectation is out of step with the fixture
  key shape, P and Q are both false against both fixtures → the calibration gate
  must report distortion.

No pytest dependency. Usage: python predicate_alignment_test.py
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from breakingdiff import Claim, DiffResult

try:
    from predicate_alignment import check_predicate_alignment
except ImportError:
    check_predicate_alignment = None   # red-first phase: the implementation module does not exist yet


def _require_impl():
    """Red-first guard: go explicitly red when the module is missing; the cause is
    "not implemented" rather than an ImportError crashing the whole file — that way
    each test's red cause maps to its own contract clause, and we can verify every
    assertion is loaded with live ammunition. Once the implementation lands, this
    guard stops applying automatically."""
    if check_predicate_alignment is None:
        raise NotImplementedError(
            "predicate_alignment.check_predicate_alignment is not implemented "
            "(1.3 predicate distortion self-check red-first phase)")


# ── calibration fixtures: known pre-change state + known post-change state (domain-agnostic minimal shape) ──────────
PRE_KEYS = frozenset({("timeout", 30)})           # pre-change state: rule inventory stores 2-tuple keys
POST_KEYS = frozenset({("timeout", 30, "s")})     # post-change state: post-change cache stores 3-tuple keys
PRE_POINT = ("timeout", 30)                       # calibration fixture one: known pre-change state point
POST_POINT = ("timeout", 30, "s")                 # calibration fixture two: known post-change state point

# A key set completely out of step with both fixtures (the keys the predicate looks for
# match neither the fixture key shape nor the fixture key value)
MISALIGNED_KEYS = frozenset({("retries", 3)})


def member_check(keys):
    return lambda pt: pt in keys


QUOTE_FROM_PLAN = '"predicate distortion" and block, do not land in neither'


def mk_claim(name, predicate):
    return Claim(name=name, predicate=predicate, applies=lambda x: True,
                 domain_note="calibration fixture point",
                 source="this repository's refinement plan landing batch §1.3 (matching CHANGELOG.md entry)",
                 quote=QUOTE_FROM_PLAN)


QUADRANT_FIELDS = ("common", "divergence", "dominance", "neither",
                   "out_of_domain")


def assert_no_quadrant_semantics(res):
    """Contract: calibration points do not enter the four-quadrant counts — the
    calibration result must carry no four-quadrant semantics at all. A calibration
    point is not a comparison-domain sample: once it enters the four quadrants, the
    neither count is contaminated by predicate distortion (this is exactly how such
    distortion reads out as a false third shape)."""
    assert not isinstance(res, DiffResult), (
        "the calibration result must not be a DiffResult: calibration points are not "
        "part of the comparison domain; entering the four-quadrant counts treats a "
        "calibration point as a differential sample")
    for f in QUADRANT_FIELDS:
        assert not hasattr(res, f), (
            f"the calibration result carries the four-quadrant field {f!r}: a calibration point leaked into the four-quadrant counts")


# ── 1. alignment passes (contract: P and Q not all false against the two fixtures → calibration passes, no distortion) ──
def test_alignment_passes_when_predicates_fire_on_fixtures():
    _require_impl()
    P = mk_claim("P pre-change account", member_check(PRE_KEYS))
    Q = mk_claim("Q post-change account", member_check(POST_KEYS))
    res = check_predicate_alignment(P, Q, PRE_POINT, POST_POINT)
    assert res.aligned is True, (
        "P(pre_point)=True and Q(post_point)=True, the predicates hit the fixtures, "
        "so calibration must pass; got aligned=" + repr(res.aligned))
    assert res.blocking is False, "a passing calibration must not block"
    assert_no_quadrant_semantics(res)


# ── 2. all-false distortion (contract: all false → report "predicate distortion" and block, do not land in neither) ─
def test_all_false_reports_distortion_and_blocks():
    _require_impl()
    P = mk_claim("P misaligned", member_check(MISALIGNED_KEYS))
    Q = mk_claim("Q misaligned", member_check(MISALIGNED_KEYS))
    res = check_predicate_alignment(P, Q, PRE_POINT, POST_POINT)
    assert res.aligned is False, (
        "the P and Q predicates are all false against both the pre-change and "
        "post-change fixtures; this must be judged predicate distortion; got aligned="
        + repr(res.aligned))
    assert res.blocking is True, (
        "predicate distortion must carry blocking semantics (the caller must not "
        "continue with compare) — reporting without blocking fails to stop the "
        "neither contamination")
    assert res.reason == "PREDICATE_DISTORTION", (
        "a distortion verdict goes through the structured reason; got: " + repr(res.reason))
    assert_no_quadrant_semantics(res)


# ── 3. a false on one side is a normal differential signal, not distortion (contract boundary) ────────────────
def test_single_side_false_is_normal_signal_not_distortion():
    _require_impl()
    # variant a: the Q side is all false (Q is all false against both fixtures, but P
    # hits) — in the differ this is the normal entry of a one-sided account, and the
    # calibration gate must not block it
    P = mk_claim("P normal", member_check(PRE_KEYS))
    Q = mk_claim("Q all false", member_check(frozenset()))
    res = check_predicate_alignment(P, Q, PRE_POINT, POST_POINT)
    assert res.aligned is True, (
        "only one side's predicate is all false against the fixtures while the other "
        "side hits; that is a normal differential signal and the calibration gate must "
        "not report distortion; got aligned=" + repr(res.aligned))
    assert res.blocking is False
    # variant b: both predicates are true on one fixture and false on the other (a
    # pre-change account being false against the post-change fixture is routine)
    res2 = check_predicate_alignment(
        mk_claim("P pre-change account", member_check(PRE_KEYS)),
        mk_claim("P2 same account", member_check(PRE_KEYS)),
        PRE_POINT, POST_POINT)
    assert res2.aligned is True, (
        "each of the two predicates is true on one fixture and false on the other; "
        "neither is all false against the fixtures, so calibration must pass")
    assert res2.blocking is False


# ── 3M. mirror: the P side all false is likewise not blocked (symmetric discrimination, N1 supplementary case) ────────────
def test_mirror_p_side_all_false_with_q_hit_is_normal_signal():
    """The mirror of 3a: P is all false against both fixtures and Q hits the post
    fixture → calibration passes.

    Symmetric discrimination: 3a can only catch the mutation "check only the Q side,
    miss the P side" (it goes red when Q all false is misjudged as distortion); the
    mutation "check only the P side, miss the Q side" escapes all green under the
    original 5 cases — this case closes the net: that mutation misjudges this
    scenario as distortion, so this case goes red. With both in place, no one-sided
    miss can escape the case net (see the mutation matrix in the results file)."""
    _require_impl()
    P = mk_claim("P all false", member_check(MISALIGNED_KEYS))
    Q = mk_claim("Q post-change account", member_check(POST_KEYS))
    res = check_predicate_alignment(P, Q, PRE_POINT, POST_POINT)
    assert res.aligned is True, (
        "the P side is all false against both fixtures while Q hits the post fixture; "
        "isomorphic to 3a this is a one-sided false (a normal differential signal), and "
        "the calibration gate must not report distortion; got aligned="
        + repr(res.aligned))
    assert res.blocking is False, "a one-sided false must not block"
    assert_no_quadrant_semantics(res)


# ── 4. the helper is a free function, not stuffed into the Claim dataclass (contract implementation shape) ───
def test_helper_is_free_function_not_claim_method():
    _require_impl()
    assert not hasattr(Claim, "check_predicate_alignment"), (
        "the contract pins an independent helper: the calibration self-check must not "
        "be stuffed into the Claim dataclass (Claim only owns claim semantics; "
        "calibration is caller orchestration before compare)")


# ── 5. mutation hook: break the predicate's key-shape expectation and the calibration gate must go red ────────────────
def test_calibration_gate_catches_broken_predicate_expectation():
    _require_impl()
    # Simulate one class of real distortion: after a key-shape 2-tuple → 3-tuple drift,
    # the predicate's key-shape expectation did not follow (it still judges by the old
    # key shape / a wrong key value), so it is all false against both the pre-change and
    # post-change fixtures. With a correct implementation this case is green (the
    # calibration gate catches the broken predicate); when the calibration gate is
    # mutated to miss it (turning a blind eye to all false), this case goes red — that
    # is the mutation-evidence entry point of the calibration gate.
    def broken_shape(pt):
        return isinstance(pt, tuple) and len(pt) == 3 and pt[0] == "retries"

    P = mk_claim("P broken key shape", broken_shape)
    Q = mk_claim("Q broken key shape", broken_shape)
    res = check_predicate_alignment(P, Q, PRE_POINT, POST_POINT)
    assert res.aligned is False, (
        "a predicate whose key-shape expectation is broken (all false against both "
        "fixtures) must be caught by the calibration gate — a calibration gate that "
        "passes it is a false-green calibration gate")
    assert res.blocking is True, "catching distortion must block at the same time"
    assert res.reason == "PREDICATE_DISTORTION"


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

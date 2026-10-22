# -*- coding: utf-8 -*-
"""
predicate_alignment — predicate distortion self-check (dual calibration points)
==============================================
A self-check gate before compare. Give a Claim pair two calibration fixtures (a known
pre-change state + a known post-change state). When the P and Q predicates judge both
fixtures false, the predicates are looking for something that matches neither known
state of the data — typically the predicate's key-shape expectation did not follow a
key-shape drift (instance: key-shape 2-tuple → 3-tuple, P/Q both false against the
post-change cache). Such a predicate only ever outputs false for any point in compare;
the neither readout is a product of distortion, not a third shape. So all false →
report "predicate distortion" and block; do not land in neither.

Calibration points are not comparison-domain samples: a calibration conclusion carries
only aligned/blocking/message, none of the four-quadrant fields — once calibration
points enter the four-quadrant counts, neither is contaminated.
"""
from dataclasses import dataclass

from breakingdiff import Claim


@dataclass(frozen=True)
class AlignmentResult:
    aligned: bool     # True = calibration passed; False = predicate distortion
    blocking: bool    # True on distortion: the caller must not continue with compare
    message: str
    reason: str = "UNSPECIFIED"   # i18n Phase 0 decision code: ALIGNED / PREDICATE_DISTORTION


def check_predicate_alignment(P: Claim, Q: Claim,
                              pre_point, post_point) -> AlignmentResult:
    """Dual calibration point self-check: distortion only when all four verdicts
    (P/Q × pre/post fixture) are false.

    A false on one side is a normal differential signal (one account not hitting one
    state is entry semantics); two predicates each true on one fixture and false on
    the other is even more routine. Only all four false means the predicates are
    completely out of step with both known states, and at that point the readout is
    no longer trustworthy.
    """
    hits = (bool(P.predicate(pre_point)), bool(P.predicate(post_point)),
            bool(Q.predicate(pre_point)), bool(Q.predicate(post_point)))
    if any(hits):
        return AlignmentResult(True, False,
                               "[PA:ALIGNED] calibration passed: the P and Q predicates are not all false against the calibration fixtures",
                               reason="ALIGNED")
    return AlignmentResult(
        False, True,
        f"[PA:PREDICATE_DISTORTION] predicate distortion: the predicates of {P.name} and {Q.name} "
        f"are all false against both the pre-change and post-change calibration fixtures, "
        f"suspected key-shape expectation left behind by a key-shape drift. Blocking compare: a "
        f"distorted point must not land in neither; calibrate the predicates before rerunning",
        reason="PREDICATE_DISTORTION")

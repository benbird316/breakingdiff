# -*- coding: utf-8 -*-
"""
Plan vs realization · a frozen plan against the artifact that landed
==============================================================================
The change here raises no error: the plan says what should happen, the artifact
does what it does, and both can be true. What is missing is an independent side
of the comparison. Freezing the plan before the work starts supplies it; recomputing
that freeze at compare time is the check that the plan was not edited afterwards.

  Q plan         = what was frozen before the work (the promise)
  P realization  = what the landed artifact actually does

In the four quadrants:
  common      P∧Q   promised and landed — the plan held
  dominance  ¬P∧Q   promised and did not land — the plan's shortfall
  divergence  P∧¬Q  landed and was not promised — work outside the plan
  neither    ¬P∧¬Q  absent from both accounts

This file is a synthetic, redacted instance: four CLI flags, no real project, repository,
customer, or dataset content. It exists so the method can be run and read, not so a
real change can be quoted here. Test: `python plan_vs_realization_test.py`.
"""
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from breakingdiff import Claim, DiffResult, compare

# Synthetic fixture. One flag per quadrant is the point of the instance.
FLAGS = ("--json", "--dry-run", "--resume", "--quiet")

REALIZATION_TEXT = """fixture artifact, observed after the work landed
- --json: machine-readable output is present
- --dry-run: a dry-run flag exists and was never promised
"""

PLAN_QUOTE = "- --resume: resume from a checkpoint is promised"
REALIZATION_QUOTE = "- --dry-run: a dry-run flag exists and was never promised"

# Appended only after a successful compare; a freeze mismatch must raise before any
# readout is produced. Tests read this list to prove the ordering.
READOUTS: List[DiffResult] = []


class FreezeError(ValueError):
    def __init__(self, msg: str, reason: str):
        super().__init__(msg)
        self.reason = reason


def digest_of(text: str) -> str:
    """The freeze record for a digest pin: `sha256:<hex>` over the full text."""
    return "sha256:" + hashlib.sha256(text.encode('utf-8')).hexdigest()


def p6_status(freeze: Optional[dict]) -> str:
    """How this pair got its independence. Wording is the contract: without a freeze
    the pair is the same hand writing both accounts, never verification."""
    if freeze is None:
        return "same-source self-consistency (no freeze recorded before the work)"
    return ("contract vs realization (the plan was frozen before the work; "
            "independence comes from that freeze, not from the two accounts differing in wording)")


def verify_freeze(plan_text: str, freeze: Optional[dict]) -> str:
    """Check the freeze before comparing. Returns the status line.

    Two accepted freeze forms:
      {"kind": "digest", "value": "sha256:<hex>"}      recomputed here
      {"kind": "commit", "commit": "<40 lowercase hex>", "text": "<the pinned plan>"}
    The commit form is accepted as-is: a commit already pins the text, and demanding a
    digest on top of it would be tighter than the exception needs to be.
    """
    if freeze is None:
        raise FreezeError(
            "[BD:PLAN_NOT_FROZEN] the plan was not frozen before the work: this pair is "
            "same-source self-consistency, not verification. One hand can write both "
            "accounts afterwards, at any time, and agreement then proves nothing",
            reason="NOT_FROZEN")

    kind = freeze.get("kind") if isinstance(freeze, dict) else None
    if kind == "digest":
        expected = freeze.get("value", "")
        actual = digest_of(plan_text)
        if expected != actual:
            raise FreezeError(
                f"[BD:PLAN_FREEZE_MISMATCH] the plan no longer matches its digest freeze "
                f"(frozen {expected!r}, now {actual!r}). An edit after the freeze is a new "
                f"round: freeze the edited plan, do not compare this one under the old freeze",
                reason="MISMATCH")
        return p6_status(freeze)

    if kind == "commit":
        commit = freeze.get("commit", "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise FreezeError(
                f"[BD:PLAN_COMMIT_FORMAT] a commit freeze needs a full 40-char lowercase hex "
                f"sha (a short sha is ambiguous), got {commit!r}",
                reason="BAD_FREEZE")
        if plan_text != freeze.get("text", ""):
            raise FreezeError(
                "[BD:PLAN_FREEZE_MISMATCH] the plan text differs from the text pinned by the "
                "commit freeze. An edit after the freeze is a new round: freeze the edited plan",
                reason="MISMATCH")
        return p6_status(freeze)

    raise FreezeError(
        f"[BD:PLAN_FREEZE_KIND] unknown freeze kind {kind!r}: use a digest or a commit pin",
        reason="BAD_FREEZE")


@dataclass
class Readout:
    status: str
    result: DiffResult


def _claims(plan_text: str):
    # Neither side hard-codes booleans: the predicates read the frozen plan and the
    # observed artifact. The flags are the parameter points; provenance quotes are
    # verbatim fragments of each side.
    q = Claim(
        name="plan-frozen(Q)",
        predicate=lambda flag: flag in ("--json", "--resume"),
        applies=lambda flag: flag in FLAGS,
        domain_note="flags the plan was frozen over",
        source="fixture/plan#L2-L3",
        quote=PLAN_QUOTE,
        quote_source=plan_text,
        source_tests=(("--json", True), ("--resume", True), ("--dry-run", False)),
    )
    p = Claim(
        name="realization(P)",
        predicate=lambda flag: flag in ("--json", "--dry-run"),
        applies=lambda flag: flag in FLAGS,
        domain_note="flags the landed artifact was observed to support",
        source="fixture/realization#L2-L3",
        quote=REALIZATION_QUOTE,
        quote_source=REALIZATION_TEXT,
        source_tests=(("--json", True), ("--dry-run", True), ("--resume", False)),
    )
    return p, q


def run(plan_text: str, freeze: Optional[dict]) -> Readout:
    """Freeze check first, comparison second, readout last. The order is the point:
    an amended plan must raise before any number is printed."""
    status = verify_freeze(plan_text, freeze)
    p, q = _claims(plan_text)
    result = compare(p, q, FLAGS)
    READOUTS.append(result)
    return Readout(status=status, result=result)

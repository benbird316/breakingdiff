# -*- coding: utf-8 -*-
"""
Plan-vs-realization instance — regression tests and mutation evidence
==============================================================================
Pins four things: a frozen plan vs the landed artifact yields all four quadrants;
a commit pin supplies the same independence; a plan edited after the freeze raises
before anything is compared; and an unfrozen pair falls back to same-source
self-consistency instead of being read as verification.

Mutation evidence (kept here, not in SKILL.md or the reference article): short-circuit
the digest comparison inside `verify_freeze` (return immediately instead of recomputing
and comparing) and `test_plan_edited_after_freeze_raises_before_comparing` must turn
red — the amended plan would pass silently. Restoring the comparison must turn it
green again; the byte-level hash of the module is checked against the backup.

Does not depend on pytest (the local `raises` stands in); pytest can still collect it.
Usage: python plan_vs_realization_test.py
       python -m pytest plan_vs_realization_test.py -q
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))

import plan_vs_realization as M


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


# Synthetic, redacted fixture: no real project, repository, or customer content.
# Four flags are enough to land one point in each quadrant.
FLAGS = ("--json", "--dry-run", "--resume", "--quiet")

PLAN_TEXT = """fixture plan, frozen before the work began
- --json: machine-readable output is promised
- --resume: resume from a checkpoint is promised
"""

REALIZATION_TEXT = """fixture artifact, observed after the work landed
- --json: machine-readable output is present
- --dry-run: a dry-run flag exists and was never promised
"""


def _digest_freeze():
    return {"kind": "digest", "value": M.digest_of(PLAN_TEXT)}


def _commit_freeze():
    return {"kind": "commit", "commit": "a" * 40, "text": PLAN_TEXT}


def test_frozen_digest_yields_four_quadrants():
    """A digest recorded before the work, recomputed at compare time, buys an
    independent pair. Exactly one flag per quadrant, and the plan's promise that did
    not land is the dominance witness."""
    out = M.run(PLAN_TEXT, _digest_freeze())
    assert out.status.startswith("contract vs realization"), out.status
    r = out.result
    assert (r.common, r.divergence, r.dominance, r.neither) == (1, 1, 1, 1), \
        f"expected 1/1/1/1, got {r.common}/{r.divergence}/{r.dominance}/{r.neither}"
    assert r.out_of_domain == 0
    assert r.dominance_witnesses == ["--resume"], \
        f"the promised-but-not-landed flag should be --resume, got {r.dominance_witnesses}"
    assert r.divergence_witnesses == ["--dry-run"], \
        f"the landed-but-not-promised flag should be --dry-run, got {r.divergence_witnesses}"


def test_commit_pin_also_supplies_independence():
    """The exception accepts either form: a commit pin (40-char lowercase hex) is
    enough, and does not need to be tighter than a digest."""
    out = M.run(PLAN_TEXT, _commit_freeze())
    assert out.status.startswith("contract vs realization"), out.status
    r = out.result
    assert (r.common, r.divergence, r.dominance, r.neither) == (1, 1, 1, 1)


def test_plan_edited_after_freeze_raises_before_comparing():
    """Editing the plan after the freeze is a new round, not a revision of this one.
    The mismatch must raise, and no readout may be produced first."""
    before = len(M.READOUTS)
    amended = PLAN_TEXT + "- --full: full output is promised\n"
    with raises(M.FreezeError) as e:
        M.run(amended, _digest_freeze())
    assert e.value.reason == "MISMATCH", e.value.reason
    assert len(M.READOUTS) == before, \
        "a readout was produced for an amended plan: the comparison ran before the freeze check"


def test_unfrozen_pair_falls_back_to_self_consistency():
    """No freeze means one hand can write both accounts afterwards; the tool must
    refuse to read agreement as verification (the old defense line stays)."""
    with raises(M.FreezeError) as e:
        M.run(PLAN_TEXT, None)
    assert e.value.reason == "NOT_FROZEN", e.value.reason
    assert "same-source self-consistency" in str(e.value), \
        f"the unfrozen fallback must name same-source self-consistency: {e.value}"


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

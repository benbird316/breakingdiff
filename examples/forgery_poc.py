# -*- coding: utf-8 -*-
"""
Forged PoC · capability declaration table: the permanent baseline for "the three
gates are effective against sloppiness, ineffective against deliberate forgery"
==============================================================================
Measured baseline: a forged Claim built from a few dozen lines passes the
provenance binding, the source self-test, and the discrimination gate. This file
takes those moves in and pins the fact rather than tolerating a defect — each move
declares "can this currently fool the gate", and the test only reconciles the
declaration against the measurement.

Why a declaration table instead of a "cannot block" ledger: a ledger means every
defense landing requires hand-editing the expectation, so the moment "the
improvement turns red" arrives the screen fills with confusion. With a declaration
table, an improvement = confirm the block by measurement + graduate the move, and
not one existing assertion has to change.

Graduation mechanism (three steps when a defense lands):
  1. Run the move for real and watch the gate block it — the red state must be
     seen, not inferred;
  2. Delete the move from MOVES/CAPABILITY and add an independent regression
     test_<move>_raises_<specific error> to forgery_poc_test.py, pinning the
     concrete exception type;
  3. The graduated item is from then on guarded by a regression test; only moves
     not yet blocked remain in the table.
Residual risk: silently deleting an un-graduated table item = the declaration
surface shrinks; known and accepted (graduated items cannot be deleted, they have
a name in the test file).

Usage: python forgery_poc.py
"""
import sys
import traceback

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'scripts'))
from breakingdiff import Claim, compare

DOMAIN = ("json", "csv", "parquet")

# One shared set of fabricated corpus text for all moves. Note the relation between
# FORGED_QUOTE and FORGED_SOURCE_TEXT: the "full source text" is fabricated too, and
# conveniently wraps the quote — the verbatim check verifies the containment relation
# between two strings; it cannot see whether the text is real.
FORGED_SOURCE = "The Authoritative Configuration Guide, chapter 3 (this book does not exist)"
FORGED_QUOTE = "export capability takes json as the only recommended format; csv is deprecated"
FORGED_SOURCE_TEXT = f"before...{FORGED_QUOTE}...after"


def _forged(**kw):
    """Shared skeleton for a forged Claim. A move only changes the one spot it aims
    to fool; every other field is supplied as usual — that is exactly the gates'
    blind spot: every field they check is present, only the content is made up."""
    d = dict(name="forged claim",
             predicate=lambda cap: cap == "json",
             applies=lambda cap: cap in DOMAIN,
             domain_note="fabricated domain note",
             source=FORGED_SOURCE,
             quote=FORGED_QUOTE,
             quote_source=FORGED_SOURCE_TEXT)
    d.update(kw)
    return Claim(**d)


def _summary(r):
    return (f"four quadrants {r.common}/{r.divergence}/{r.dominance}/{r.neither}, "
            f"out of domain {r.out_of_domain}")


def forge_fabricated_source():
    """Move one: fabricate the provenance. The provenance gate only checks that
    source and quote are non-empty — the source is made up and the text is made up;
    as long as quote_source is absent, the verbatim check never starts."""
    r = compare(_forged(quote_source=""),
                _forged(name="control baseline", predicate=lambda cap: cap == "csv"),
                DOMAIN)
    return _summary(r)


def forge_mutual_containment_swap():
    """Move two: quote and quote_source contain each other (swap) — the object being
    checked and the basis for checking it are both fabrications, and the "full source
    text" conveniently wraps the quote. The gate sees "the quote is inside
    quote_source" and lets it through: it verifies internal consistency, not
    consistency with the outside world."""
    r = compare(_forged(),
                _forged(name="control baseline", predicate=lambda cap: cap == "csv"),
                DOMAIN)
    return _summary(r)


def forge_tautology():
    """Move three: a tautological predicate with all-True test points. The source
    self-test checks "the predicate agrees with the expectations"; write True
    everywhere, have the predicate always return True, and the self-test scores 3/3.
    The discrimination gate only cares about claims that supply interpretations —
    supply none and it stays silent. A tautological claim is therefore "equivalent"
    to everything in the comparison domain."""
    r = compare(_forged(name="tautological claim", predicate=lambda cap: True,
                        source_tests=(("json", True), ("csv", True), ("parquet", True)),
                        quote_source=""),
                _forged(name="control baseline", predicate=lambda cap: cap == "csv"),
                DOMAIN)
    return _summary(r)


def forge_straw_variants():
    """Move four: feed the discrimination gate fabricated straw-man interpretations.
    The gate only asks "can the test points separate the claim from the candidate
    interpretations" — stuff in a straw man that is false everywhere and the
    distinguishing points are immediately full marks. None of the real
    formalization drift (say, reading "recommended" as "the only supported format")
    is examined."""
    straw = _forged(name="straw-man interpretation: nothing is supported", predicate=lambda cap: False)
    r = compare(_forged(name="formalization of the recommended format",
                        predicate=lambda cap: cap == "json",
                        source_tests=(("json", True), ("csv", False)),
                        reading_variants=(straw,),
                        quote_source=""),
                _forged(name="control baseline", predicate=lambda cap: cap == "csv"),
                DOMAIN)
    return _summary(r)


def forge_empty_domain():
    """Move five: make applies always false to empty the comparison domain. A zero
    readout of 0/0/0/0 gets read as "no divergence" — the quietest tier of
    three-level silence; no gate checks whether applies is honest."""
    r = compare(_forged(name="defines nothing", applies=lambda cap: False,
                        quote_source=""),
                _forged(name="control baseline", predicate=lambda cap: cap == "csv"),
                DOMAIN)
    return _summary(r)


# The move surface and the declaration surface must coincide (the test pins this).
# There are only two states: passes = it can currently fool the gate and finish
# compare; blocked = a gate stops it. Graduation removes the whole item; no third
# state is written.
MOVES = {
    "fabricated source": forge_fabricated_source,
    "quote and quote_source mutually contain (swap)": forge_mutual_containment_swap,
    "tautology with all-True test points": forge_tautology,
    "straw-man interpretations fool discrimination": forge_straw_variants,
    "empty comparison domain yields a zero readout": forge_empty_domain,
}
CAPABILITY = {name: "passes" for name in MOVES}


def run(name):
    """Run one move and return the readout summary it got away with; if a gate blocks
    it, the exception is re-raised untouched."""
    return MOVES[name]()


def measure(name):
    """Measured state: a two-state binary. The exception type and message are left to
    the graduation-time regression test; here only "did it finish" counts — swallowing
    the exception is fine, the declaration reconciliation turns it red."""
    try:
        MOVES[name]()
        return "passes"
    except Exception:
        return "blocked"


def main():
    print()
    print("#" * 74)
    print("# Forged PoC: measured vs declared per move (passes = can currently fool the gate)")
    print("#" * 74)
    for name in MOVES:
        try:
            print(f"  [passes] {name}\n      {run(name)}")
        except Exception:
            print(f"  [blocked] {name}")
            traceback.print_exc()
    print()
    print("  Graduation rule: once a defense lands, remove the move from MOVES/CAPABILITY")
    print("  and pin the concrete error with an independent regression test — an improvement")
    print("  = one fewer declaration + one more regression.")
    print()


if __name__ == '__main__':
    main()

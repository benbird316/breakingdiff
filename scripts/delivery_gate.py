# -*- coding: utf-8 -*-
"""
delivery_gate — the delivery gate for code-writing scenarios
==================================================
Turn breakingdiff from "a tool the agent uses when it remembers" into "a checkpoint
that must pass before delivery".

## Why a gate cannot rely on "comparing before and after the refactor"

The naive idea: compress the implementation before and after the refactor into one
claim each and compare point by point. That **fails P6** among breakingdiff's six
structural preconditions — both sides were written by the same agent, so agreement is
only same-source self-consistency, not cross-verification. Such a gate produces a
false green, and a false green is worse than no gate: it makes people believe it
verified something.

So this gate **swaps the opponent**: it does not compare against "your own past", but
against an independent source.

    Q spec account   = specs, contracts, type definitions, and actual consumer
                       dependencies written by a human or upstream
    P claim account  = this change plus the behavior the tests actually uphold

The dominance quadrant reads as **"the spec required it and the test does not uphold
it"** — that is what should be blocked before delivery. In such a comparison Q comes
from a human or upstream and P from the agent, so **P6 holds**.

## Three disciplines (copied from breakingdiff, not reinvented)

1. **The gate raises, never warns**: a zero readout must carry a non-zero cost, or it
   is still read as a pass.
2. **No change to the surface under test means no pass**: a change outside the coverage
   catalog → CoverageError, no "everything is normal" appearance. This mirrors the
   three-level silence in SKILL.md.
3. **Report only, never adjudicate**: in the divergence quadrant, "the test is finer
   than the spec" is usually hardening, not a defect. The tool does not judge right or
   wrong; it lays out the positions for a human to see.

## Usage

Create `bd_gate.py` in your project, then:

    from delivery_gate import GateSpec, require_spec_alignment

    out = require_spec_alignment(GateSpec(
        name="this delivery",   # goes into the report title
        spec_claims=[...],      # Q side: spec/contract commitments, each with a verbatim quote
        test_claims=[...],      # P side: behavior the tests actually uphold
        catalog=[...],          # surface under test: items this round commits to compare
    ))

`out` is a structured readout (total/dominance/dominance_witnesses/out_of_domain/report).
It raises DeliveryError when the comparison domain is empty, dominance > 0, or
out-of-domain skip > 0; when the readout does not decide, call check_alignment(spec)
directly.

When files change, they must pass the coverage gate: pass changed_files and declare
{filename: touched commitment items} via file_coverage (unregistered files are
blocked). Register items explicitly not upheld in
unguarded=[UnguardedItem("item", "reason")]; without a reason they are blocked as
out-of-domain skips.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from breakingdiff import Claim, compare, render
from coverage_guard import CoverageError, _norm, require_covered


class DeliveryError(ValueError):
    """The delivery gate did not pass. Raise instead of warn — a zero-cost gate is no gate.

    Structured fields (i18n Phase 0):
      reason               stable criterion code (EMPTY_CATALOG / GATE_FAILED)
      problems             per-problem entries (kind + witnesses/count); tests assert them
      counters             four-quadrant counter snapshot
      unguarded_registered registered-not-upheld items (sequence of (item, reason))
    The message text is translated; criterion codes and structured fields never change.
    """

    def __init__(self, message: str, *, reason: str, problems=(),
                 counters=None, unguarded_registered=(), report: str = ""):
        super().__init__(message)
        self.reason = reason
        self.problems = tuple(problems)
        self.counters = dict(counters or {})
        self.unguarded_registered = tuple(unguarded_registered)
        self.report = report


# Explicit not-upheld register: items the spec promised but this batch explicitly
# does not deliver. Previously the only way through was to hand-write a fake claim
# on the P side — dishonest and unrecorded. Registration must carry a reason:
# a not-upheld item without one is indistinguishable from "forgot to list it", so it
# is downgraded to an out-of-domain skip and blocked, forcing the reason to be added.
class UnguardedItem(NamedTuple):
    """One explicit not-upheld registration: (item name, reason), constructed positionally in that order."""
    item: str
    reason: str


# Catalog: what the delivery gate compares. It is not proof of "already covered";
# it declares "what this round commits to compare".
#
# ★ The catalog is itself the judge; review it as carefully as a predicate:
#   write one fewer item = that item falls outside the surface under test = the gate
#   is completely blind to it (three-level silence in SKILL.md).
#   write one more item = that item enters the surface under test = the four
#   quadrants really go and compare it.
@dataclass
class GateSpec:
    """Input for one delivery-gate check."""
    name: str                                  # name of this delivery, goes into the report title
    spec_claims: List[Claim]                   # Q: spec/contract account
    test_claims: List[Claim]                   # P: test-assertion account
    catalog: Sequence[str]                     # surface under test: markers the catalog recognizes (commitment items)
    unguarded: Sequence[UnguardedItem] = ()    # explicit not-upheld register: (item name, reason)
    changed_files: Sequence[str] = ()          # files changed this round
    file_coverage: Dict[str, Sequence[str]] = field(default_factory=dict)
    exempt: Sequence[str] = ()                 # explicitly exempt files (verbatim equality)
    spec_note: str = "spec / contract / upstream commitment"
    test_note: str = "behavior the tests actually uphold"


# Wrapper around the coverage gate: every changed file must have a corresponding
# commitment item on the surface under test.
#
# ★ Dimension discipline: file paths and commitment items are two different things and
#   cannot go into the same set for comparison. An earlier implementation threw
#   changed_files=['src/auth.py'] and catalog=['R1',...] straight into require_covered,
#   so every run reported "out of scope" — 100% gate noise, switched off after two uses.
#   The correct structure has two levels:
#       file → item (which commitment covers this file's change)
#       item → four quadrants (does the test uphold this commitment)
#   The first level uses the explicit file_coverage mapping, not string luck.
def require_change_coverage(changed_files: Sequence[str],
                            file_coverage: Dict[str, Sequence[str]],
                            exempt: Sequence[str] = ()) -> None:
    """Every changed file must be able to name the commitment items it corresponds to.

    file_coverage — {filename: commitment items it touches}
    exempt        — files genuinely unrelated to this gate (verbatim equality; use PREFIX: to relax)

    Matching rules. An exact exemption is verbatim equality: it names one path, so it
    matches that path or nothing. A `PREFIX:` declaration is a pattern, so it is
    normalized with the same `_norm` as coverage_guard (`_norm` on both sides): a prefix
    means the same thing however whitespace / full-width spaces are spelled, and the two
    gates cannot drift apart on what a declared prefix covers.
    A `PREFIX:` whose normalized suffix is empty is refused (ValueError): an empty
    prefix matches every file, so one blank declaration would silently switch the whole
    file-level gate off while it still looks enabled.

    A file not registered in file_coverage → raise. This differs from "the file is
    registered but the item is not in the catalog": the former is a missing
    declaration, the latter a missing parameter space. Both block, but the wording
    differs.
    """
    exempt_exact, exempt_prefix = set(), []
    for e in exempt:
        if not e.startswith("PREFIX:"):
            exempt_exact.add(e)
            continue
        prefix = _norm(e[len("PREFIX:"):])
        if not prefix:
            raise ValueError(
                f"[DG:EMPTY_PREFIX] [coverage gate] exemption {e!r} declares PREFIX: "
                "with a blank prefix (empty, whitespace, or a full-width space).\n"
                "  An empty prefix matches every changed file, so this declaration "
                "would silently exempt the whole round.\n"
                "  Write the prefix you mean after PREFIX: (it is normalized by "
                "removing whitespace and full-width spaces).")
        exempt_prefix.append(prefix)

    unknown = []
    for f in changed_files:
        if f in file_coverage:
            continue
        if f in exempt_exact:
            continue
        if any(_norm(f).startswith(p) for p in exempt_prefix):
            continue
        unknown.append(f)
    if unknown:
        raise CoverageError(
            f"[DG:FILE_UNREGISTERED] [coverage gate] {len(unknown)} changed file(s) this round are not registered in file_coverage, "
            f"so the commitment items they correspond to cannot be determined:\n"
            + "\n".join(f"    · {f}" for f in sorted(unknown))
            + "\n\n  Two ways to fix it:\n"
            "    ① Register the items it touches in file_coverage, then rerun\n"
            "    ② If it really is unrelated to this gate, add it to exempt (verbatim equality)\n"
            + "\n  Criterion: if this file's change were wrong, would the existing readout move at all? "
              "No → it is not inside the surface under test.",
            reason="FILE_UNREGISTERED")


def _unguarded_claim(item: str, reason: str) -> Claim:
    """The explicit negative P-side claim for a registered not-upheld item.

    A predicate that is always false = the P side explicitly says "not upheld" for
    this item; applies recognizes only this item.
    The provenance is the registration reason itself: quote and quote_source are the
    same text, so the construction-time verbatim check holds by construction.
    """
    registered_line = f"unguarded[{item}]: {reason}"
    return Claim(
        name=item,
        predicate=lambda key: False,
        applies=lambda key, _item=item: key == _item,
        domain_note="registered as not upheld (promised by the spec, explicitly not delivered this batch)",
        source="delivery_gate/unguarded",
        quote=registered_line, quote_source=registered_line,
    )


def _with_unguarded_section(report: str, registered: Sequence) -> str:
    """Insert the "registered as not upheld" section before the report's closing bar,
    so a human can audit the debt this batch carries."""
    bar = "=" * 74                      # same width as render's closing bar
    head, _, tail = report.rpartition(bar)
    lines = ["[Registered not upheld]"]
    lines += [f"  · {item}: {reason}" for item, reason in registered]
    lines.append("  (explicitly not delivered this batch; excluded from the dominance/out-of-domain dimensions, reason on record for audit)")
    return head.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n" + bar + tail


def check_alignment(spec: GateSpec) -> Dict[str, Any]:
    """Run one delivery-gate check and return a structured readout. The pass/fail
    decision and blocking live in require_spec_alignment.

    unguarded items: those with a reason are excluded from the dominance/out-of-domain
    dimensions and placed in a separate "registered as not upheld" report section;
    those without a reason are downgraded to an out-of-domain skip, the same blocking
    path as "forgot to list it".
    """
    # 1. Coverage gate first — judge "does the surface under test still cover the
    #    change" before the readout.
    #    Two levels: is the file registered (declaration completeness), is the item in
    #    the catalog (space completeness)
    if spec.changed_files:
        require_change_coverage(spec.changed_files, spec.file_coverage, spec.exempt)
        # Items declared by a file must all be in the catalog, or compare cannot see them
        declared = {k for f in spec.changed_files
                    for k in spec.file_coverage.get(f, ())}
        missing = declared - set(spec.catalog)
        if missing:
            raise CoverageError(
                f"[DG:CLAIM_NOT_IN_CATALOG] [coverage gate] changed files declare {len(missing)} commitment item(s), "
                f"but these items are not in the catalog (the surface under test); the readout is invalid for them:\n"
                + "\n".join(f"    · {k}" for k in sorted(missing))
                + "\n\n  A zero readout is not a pass: fold these items into the catalog and rerun.",
                reason="CLAIM_NOT_IN_CATALOG")

    # 2. Split unguarded registrations: with a reason, explicitly not upheld; without
    #    one, downgraded to out of domain.
    #    Both paths first strip the item's old P-side claim — registered not-upheld
    #    items get an explicit negative claim; downgraded ones stay "P side undefined",
    #    so compare records an out-of-domain skip for the undefined point.
    registered, degraded = [], []
    for entry in spec.unguarded:
        item, reason = entry
        if reason and str(reason).strip():
            registered.append((item, reason))
        else:
            degraded.append(item)
    registered_keys = {item for item, _ in registered}
    stripped_keys = registered_keys | set(degraded)
    p_claims = [c for c in spec.test_claims if c.name not in stripped_keys]
    p_claims += [_unguarded_claim(item, reason) for item, reason in registered]

    # 3. Four quadrants. Q = spec, P = tests
    P = _as_one(p_claims, spec.name, "P", spec.test_note)
    Q = _as_one(spec.spec_claims, spec.name, "Q", spec.spec_note)
    # Dimension exclusion applies only to registered items: they enter neither dominance
    # nor out of domain, but a separate report section.
    # Downgraded items stay in the comparison domain — the P side is already undefined,
    # so they naturally fall into the out-of-domain skip.
    r = compare(P, Q, [k for k in spec.catalog if k not in registered_keys])

    out = {
        "total": r.total,
        "common": r.common,
        "divergence": r.divergence,
        "dominance": r.dominance,
        "neither": r.neither,
        "out_of_domain": r.out_of_domain,
        "dominance_witnesses": list(r.dominance_witnesses),
        "divergence_witnesses": list(r.divergence_witnesses),
        "report": render(P, Q, r,
                         p_label="test account", q_label="spec account",
                         meaning_divergence="the test is finer than the spec (mostly hardening, no change needed)",
                         meaning_dominance="⚠️ the spec required it but the test does not uphold it — block before delivery"),
    }
    # List "registered as not upheld" structurally: tests assert this field and do not
    # search the full report for a section title.
    out["registered_unguarded"] = [(item, reason) for item, reason in registered]
    if registered:
        out["report"] = _with_unguarded_section(out["report"], registered)
    return out


def _as_one(claims: List[Claim], name: str, label: str, note: str) -> Claim:
    """Combine N single-point claims into one composite claim judged per parameter point.

    Why not use compare_n directly: the delivery gate wants "which spec items the tests
    do not uphold", and that readout is most visible in the four-quadrant dominance.
    compare_n's shape classification fits version-chain scenarios better.
    """
    if len(claims) == 1:
        return claims[0]
    by_key = {c.name: c for c in claims}

    def combined(key):
        for c in claims:
            if c.name == key:
                return bool(c.predicate(key))
        return False

    return Claim(
        name=f"{label} {name} ({len(claims)} claims conjoined)",
        predicate=combined,
        applies=lambda key: key in by_key,
        domain_note=note,
        source=claims[0].source, quote=claims[0].quote,
        quote_source=claims[0].quote_source,
        source_tests=claims[0].source_tests,
    )


def require_spec_alignment(spec: GateSpec) -> Dict[str, Any]:
    """The pass/fail decision of the delivery gate.

    Rules (deliberately conservative):
      · **Empty comparison domain → reject**. A zero readout is not a pass: catalog=[]
        makes all four quadrant counts 0, so the readout looks like "everything is
        normal" while actually "nothing was compared".
        This is the same path as forgery_poc move five (an always-false applies
        manufactures a zero readout); only the entrance changes from "applies is
        always false" to "the catalog is empty".
      · dominance > 0 → **fail**. The spec required it and the test does not uphold it;
        handle it before delivery. Note: this is "not upheld", not "wrong" — the fix
        can be adding a test, or amending the spec to say this is not a commitment, but
        that is a human's job; the tool does not adjudicate.
      · out-of-domain skip > 0 → **fail**. Some items never entered the comparison
        domain, so the readout is invalid for them.
      · otherwise → pass.

    Why divergence does not block: the test being finer than the spec is usually
    hardening; rewriting the spec to match the test treats a weakening as an
    enhancement. The tool only reports positions; a human chooses the direction.
    """
    # The empty comparison domain must be judged first: when the domain is empty,
    # dominance/out-of-domain/common are all 0, and every later check passes naturally
    # — "all 0" looks too much like "all agree".
    if not spec.catalog:
        raise DeliveryError(
            "[DG:EMPTY_CATALOG] [delivery gate] not passed\n"
            f"  The comparison domain is empty (catalog has {len(spec.catalog)} items).\n\n"
            "  A zero readout is not a pass: when the catalog is empty, all four quadrant counts are 0,\n"
            "  so the readout looks like \"everything is normal\" while actually \"nothing was compared\".\n"
            "  This is the same path as forgery_poc move five (an always-false applies manufactures\n"
            "  a zero readout): different entrance, same consequence.\n\n"
            "  Two ways to fix it:\n"
            "    ① Fill in the commitment items to compare this round (even just one)\n"
            "    ② If there really is nothing to compare this round, that is \"no deliverable behavior change\",\n"
            "       and it should not go through the delivery gate — first confirm the change really needs a gate",
            reason="EMPTY_CATALOG",
            problems=({"kind": "EMPTY_CATALOG", "count": 0},),
            counters={"total": 0, "common": 0, "divergence": 0,
                      "dominance": 0, "neither": 0, "out_of_domain": 0},
            report="")

    out = check_alignment(spec)

    problem_texts, problem_entries = [], []
    if out["total"] == 0:
        problem_texts.append(
            f"The comparison domain is effectively empty (four quadrants total {out['total']} points) —\n"
            f"  catalog has {len(spec.catalog)} items, but no item is defined by both accounts.\n"
            "  A zero readout is not a pass. Check whether applies was set to always false.")
        problem_entries.append({"kind": "EMPTY_EFFECTIVE_DOMAIN",
                                "count": out["total"]})
    if out["dominance"] > 0:
        problem_texts.append(
            f"dominance {out['dominance']} points — the spec required them and the tests do not uphold them:\n"
            + "\n".join(f"      · {w}" for w in out["dominance_witnesses"]))
        problem_entries.append({"kind": "DOMINANCE", "count": out["dominance"],
                                "witnesses": list(out["dominance_witnesses"])})
    if out["out_of_domain"] > 0:
        problem_texts.append(
            f"out-of-domain skip {out['out_of_domain']} points — these items never entered the comparison domain, "
            f"so the readout is invalid for them (a zero readout is not a pass)")
        problem_entries.append({"kind": "OUT_OF_DOMAIN",
                                "count": out["out_of_domain"]})

    if problem_texts:
        raise DeliveryError(
            "[DG:GATE_FAILED] [delivery gate] not passed\n"
            + "\n".join(problem_texts)
            + "\n\n"
            + "  Criterion: the spec says X, and no test pins X down.\n"
            "  Two ways to handle it (a human decides; the tool does not adjudicate):\n"
            "    ① Add a test that pins it down\n"
            "    ② Amend the spec to state this is not a commitment (and remove it from the catalog)\n"
            + out["report"],
            reason="GATE_FAILED",
            problems=tuple(problem_entries),
            counters={key: out[key] for key in
                      ("total", "common", "divergence", "dominance",
                       "neither", "out_of_domain")},
            unguarded_registered=out["registered_unguarded"],
            report=out["report"])

    return out

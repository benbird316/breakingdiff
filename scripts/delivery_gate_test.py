# -*- coding: utf-8 -*-
"""
delivery_gate's own regression tests and mutation evidence
==================================================
The delivery gate is the gate against self-deception, so it must itself be pinned
down first.

This file answers one question: **what happens if someone changes the delivery gate
to always let things through?** The answer must be "the test goes red on the spot",
or the gate is a mere formality — and the most dangerous kind of formality: the report
still prints, the format still matches, it just no longer blocks anything.

No pytest dependency. Usage: python delivery_gate_test.py
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# examples/ must also be importable: test_gate_blocks_forgery_poc_move_five builds
# the PoC's original construction
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "examples"))

from breakingdiff import Claim, SourceTestError
from coverage_guard import CoverageError
from delivery_gate import (DeliveryError, GateSpec, check_alignment,
                           require_change_coverage, require_spec_alignment)


class raises:
    """Minimal context manager: a stand-in for pytest.raises."""
    def __init__(self, exc):
        self.exc, self.value = exc, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"expected {self.exc.__name__} to be raised, but nothing was raised")
        self.value = ev
        return issubclass(et, self.exc)


# ── Corpus: one spec (written upstream) and one set of tests (written locally) ──
# A parameter point = one behavior commitment listed in the spec. CATALOG is
# "which items this round compares".
SPEC_TEXT = """# auth service spec (maintained upstream)

## Behavior commitments
- R1: a wrong password returns 401
- R2: a correct password returns 200
- R3: an unknown account returns 404
- R4: a locked account returns 423
- R5: five consecutive failures lock the account
"""

TEST_TEXT = """# test_auth.py

def test_wrong_password_401(): assert login('u', 'bad') == 401
def test_right_password_200(): assert login('u', 'ok') == 200
def test_missing_user_404(): assert login('nope', 'x') == 404
"""

SPEC_QUOTE = "- R5: five consecutive failures lock the account"
TEST_QUOTE = "def test_wrong_password_401"


def spec_claims(*extra_ok: str):
    """Q side: which items the spec promises. Items named in extra_ok also count as promises."""
    promised = {"R1", "R2", "R3"} | set(extra_ok)
    specs = [
        ("R1", "- R1: a wrong password returns 401"),
        ("R2", "- R2: a correct password returns 200"),
        ("R3", "- R3: an unknown account returns 404"),
        ("R4", "- R4: a locked account returns 423"),
        ("R5", "- R5: five consecutive failures lock the account"),
    ]
    out = []
    for key, quote in specs:
        if key == "R1":
            continue                      # R1 is handled separately by make_claims (see below)
        out.append(Claim(
            name=key,
            predicate=lambda k, _k=key: k == _k and k in promised,
            applies=lambda k: k.startswith("R"),
            domain_note="spec item",
            source="auth-spec/SPEC.md",
            quote=quote, quote_source=SPEC_TEXT,
        ))
    return out


def make_claims(promised=None, tested=None):
    """Build the two composite accounts, Q and P.

    promised — what the spec promises (a subset of R1..R5)
    tested   — what the tests uphold (a subset of R1..R5)
    """
    promised = promised or {"R1", "R2", "R3", "R4", "R5"}
    tested = tested if tested is not None else {"R1", "R2", "R3"}

    all_keys = ["R1", "R2", "R3", "R4", "R5"]
    q_claims = [
        Claim(name=k,
              predicate=lambda x, _k=k: x == _k and _k in promised,
              applies=lambda x: x in all_keys,
              domain_note="spec item",
              source="auth-spec/SPEC.md",
              quote=f"- {k}: ", quote_source=SPEC_TEXT)
        for k in all_keys
    ]
    p_claims = [
        Claim(name=k,
              predicate=lambda x, _k=k: x == _k and _k in tested,
              applies=lambda x: x in all_keys,
              domain_note="spec item",
              source="tests/test_auth.py",
              quote=TEST_QUOTE, quote_source=TEST_TEXT)
        for k in all_keys
    ]
    return q_claims, p_claims


CATALOG = ["R1", "R2", "R3", "R4", "R5"]
# Explicit file → item mapping (different dimensions; a path cannot go straight into catalog comparison)
FILE_COVERAGE = {"src/auth.py": ["R1", "R2", "R3", "R4", "R5"]}


# ── it blocks ────────────────────────────────────────────────
def test_uncovered_spec_item_blocks_delivery():
    """The spec promises R4/R5 and the tests do not uphold them → the delivery gate must reject.

    This is the entire reason the gate exists: the spec said it, the tests did not pin it
    down, and shipping it means passing "CI all green" off as "behavior verified".
    """
    q, p = make_claims(promised={"R1", "R2", "R3", "R4", "R5"},
                       tested={"R1", "R2", "R3"})
    spec = GateSpec(name="auth refactor", spec_claims=q, test_claims=p,
                    catalog=CATALOG, changed_files=["src/auth.py"],
                    file_coverage=FILE_COVERAGE)
    with raises(DeliveryError) as e:
        require_spec_alignment(spec)
    msg = str(e.value)
    assert "R4" in msg and "R5" in msg, "dominance witnesses must name the specific items"
    assert "does not uphold" in msg


def test_fully_aligned_spec_passes():
    """Every item the spec promises is pinned by a test → let it through. The gate makes no noise."""
    q, p = make_claims(promised={"R1", "R2"}, tested={"R1", "R2"})
    spec = GateSpec(name="small auth change", spec_claims=q, test_claims=p,
                    catalog=["R1", "R2"], changed_files=["src/auth.py"],
                    file_coverage={"src/auth.py": ["R1", "R2"]})
    out = require_spec_alignment(spec)
    assert out["dominance"] == 0
    assert out["out_of_domain"] == 0


def test_divergence_does_not_block():
    """The test is finer than the spec (it pins R5, which the spec never promised) → let it through.

    Deliberately not blocked: rewriting a weakened spec to look like the test treats
    hardening as a defect. The tool only reports positions; a human chooses the direction.
    """
    q, p = make_claims(promised={"R1", "R2"}, tested={"R1", "R2", "R5"})
    spec = GateSpec(name="hardening", spec_claims=q, test_claims=p,
                    catalog=["R1", "R2", "R5"], changed_files=["src/auth.py"],
                    file_coverage={"src/auth.py": ["R1", "R2", "R5"]})
    out = require_spec_alignment(spec)
    assert out["divergence"] >= 1, "the divergence quadrant should read 'the test is finer than the spec'"


def test_file_not_registered_blocks():
    """A changed file not registered in file_coverage → raise.

    Dimension discipline: file paths and commitment items are two different things. An
    early implementation compared changed_files=['src/auth.py'] directly against
    catalog=['R1',...], so every run reported out of scope — 100% gate noise, switched
    off after two uses.
    """
    q, p = make_claims(promised={"R1"}, tested={"R1"})
    spec = GateSpec(name="unregistered", spec_claims=q, test_claims=p,
                    catalog=["R1"],
                    changed_files=["src/auth.py", "src/payment.py"],
                    file_coverage={"src/auth.py": ["R1"]})
    with raises(CoverageError) as e:
        require_spec_alignment(spec)
    assert "src/payment.py" in str(e.value)


def test_declared_item_outside_catalog_blocks():
    """An item a file declares it touches is not in the catalog → raise.

    This is a different path from the previous one: that one is "the file is not
    registered" (missing declaration), this one is "the item is not on the surface under
    test" (missing space). Both produce a false green and both block, but the wording
    must differ.
    """
    q, p = make_claims(promised={"R1"}, tested={"R1"})
    spec = GateSpec(name="item out of scope", spec_claims=q, test_claims=p,
                    catalog=["R1"],
                    changed_files=["src/auth.py"],
                    file_coverage={"src/auth.py": ["R1", "R7"]})
    with raises(CoverageError) as e:
        require_spec_alignment(spec)
    assert "R7" in str(e.value)


def test_change_outside_catalog_blocks():
    """Items a changed file declares are not in the catalog → CoverageError.

    This is tier three of the three-level silence: the change is entirely outside the
    surface under test, so the four quadrants quietly give "zero change", and zero change
    gets read as "verified". The delivery gate must block here.
    """
    q, p = make_claims(promised={"R1"}, tested={"R1"})
    spec = GateSpec(name="out-of-scope change", spec_claims=q, test_claims=p,
                    catalog=["R1"],
                    changed_files=["src/auth.py"],
                    file_coverage={"src/auth.py": ["R1", "R8"]})
    with raises(CoverageError) as e:
        require_spec_alignment(spec)
    assert "A zero readout is not a pass" in str(e.value)


def test_out_of_domain_blocks_delivery():
    """Some item never entered the comparison domain → the readout is invalid for it; must block.

    The difference from the previous test: that one is "the change did not enter the
    surface under test", this one is "an item was never compared". Both produce a false
    green through different paths.
    """
    q, p = make_claims(promised={"R1"}, tested={"R1"})
    # Put an item that neither account applies into the catalog → out-of-domain skip > 0
    spec = GateSpec(name="out of domain", spec_claims=q, test_claims=p,
                    catalog=["R1", "R9"], changed_files=[])
    with raises(DeliveryError) as e:
        require_spec_alignment(spec)
    # Short literals on purpose: a long verbatim phrase here would be collected
    # by leak_guard rule one and flagged as grading-side text leaking into SKILL prose.
    assert "out-of-domain" in str(e.value) and "skip" in str(e.value)


def test_exempt_uses_verbatim_matching():
    """Exemptions must be verbatim equality — follow the discipline changed in coverage_guard, do not invent another one here."""
    with raises(CoverageError):
        require_change_coverage(["src/notes.md"], {"src/a.py": ["R1"]},
                                exempt=["notes"])
    require_change_coverage(["src/notes.md"], {"src/a.py": ["R1"]},
                            exempt=["src/notes.md"])


# Forms whose `PREFIX:` suffix is empty or whitespace-only. Each must be refused:
# an empty prefix matches every changed file, so one blank declaration silently
# switches the whole file-level gate off.
BLANK_PREFIX_FORMS = ["PREFIX:", "PREFIX: ", "PREFIX:\t", "PREFIX:　",
                      "PREFIX: \t　"]


def test_exempt_prefix_matching_is_normalized():
    """A `PREFIX:` exemption is matched under the same `_norm` normalization as
    coverage_guard: whitespace and full-width-space differences must not make a declared
    prefix miss a file that is really under it.

    The exact (verbatim) form stays verbatim — a different discipline, pinned by
    test_exempt_uses_verbatim_matching above. A prefix is a declared pattern, so it gets
    the pattern-level normalization; an exact exemption names one path, so it stays
    exact.
    """
    require_change_coverage(["src/gen/parser.py"], {},
                            exempt=["PREFIX: src/gen/ "])
    # full-width space inside the declaration normalizes away too (str.split() treats
    # it as whitespace, so it is joined out rather than kept inside the prefix)
    require_change_coverage(["src/gen/parser.py"], {},
                            exempt=["PREFIX: src　/gen/"])
    # and a prefix that really does not cover the file still blocks
    with raises(CoverageError):
        require_change_coverage(["src/other/parser.py"], {},
                                exempt=["PREFIX: src/gen/ "])


def test_exempt_prefix_matches_normalized_changed_path():
    """The changed-file side is normalized too, not only the declaration: a path carrying
    stray whitespace is the same file, so a cleanly declared prefix still exempts it.

    File-side half of the rule pinned by test_exempt_prefix_matching_is_normalized above
    (that one pads only the declaration and leaves the changed path clean). Revert the
    match to raw `f.startswith(p)` — dropping `_norm(f)` — and this test goes red while
    the declaration-side test stays green; that asymmetry is why the two cases live in
    two tests. A regression in either half must leave a red somewhere.
    """
    # Stray half-width space inside the path: "src/ auth.py" is "src/auth.py".
    require_change_coverage(["src/ auth.py"], {}, exempt=["PREFIX:src/auth"])
    # Full-width space is removed by the same normalization.
    require_change_coverage(["src/　auth.py"], {}, exempt=["PREFIX:src/auth"])
    # Normalization must not invent a match: a path really elsewhere still blocks.
    with raises(CoverageError):
        require_change_coverage(["vendor/auth.py"], {}, exempt=["PREFIX:src/auth"])


def test_blank_prefix_file_exemption_is_refused():
    """A `PREFIX:` with a blank suffix exempts every file — refuse it instead.

    Pre-fix, `exempt=["PREFIX:"]` made require_change_coverage accept any unregistered
    file: the file-level gate was fully off while still looking enabled. The message must
    name the raw declaration so the broken line is findable.
    """
    for raw in BLANK_PREFIX_FORMS:
        with raises(ValueError) as e:
            require_change_coverage(["src/payment.py"], {"src/a.py": ["R1"]},
                                    exempt=[raw])
        msg = str(e.value)
        assert "PREFIX" in msg, "the message must name the malformed declaration"
        assert repr(raw) in msg, f"the message must show the blank form verbatim: {raw!r}"


def test_mutation_blank_prefix_accepting_all_files_is_caught():
    """Remove the blank-prefix guard and this file goes red: the pre-fix mutant accepts
    every unregistered file on `exempt=["PREFIX:"]`, the real gate raises."""
    def pre_fix_require_change_coverage(changed_files, file_coverage, exempt=()):
        unknown = [f for f in changed_files
                   if f not in file_coverage and f not in set(exempt)
                   and not any(e.startswith("PREFIX:") and f.startswith(e[7:])
                               for e in exempt)]
        return unknown

    assert pre_fix_require_change_coverage(
        ["src/payment.py"], {"src/a.py": ["R1"]}, exempt=["PREFIX:"]) == [], \
        "the mutant must reproduce the silent blanket exemption this test refuses"
    with raises(ValueError):
        require_change_coverage(["src/payment.py"], {"src/a.py": ["R1"]},
                                exempt=["PREFIX:"])


def test_mutation_raw_prefix_matching_is_caught():
    """Revert prefix matching to raw `f.startswith(e[7:])` and this file goes red: the
    padded declaration `PREFIX: src/gen/ ` no longer matches the file it declares."""
    def raw_prefix_require_change_coverage(changed_files, file_coverage, exempt=()):
        unknown = [f for f in changed_files
                   if f not in file_coverage and f not in set(exempt)
                   and not any(e.startswith("PREFIX:") and f.startswith(e[7:])
                               for e in exempt)]
        return unknown

    padded = ["PREFIX: src/gen/ "]
    assert raw_prefix_require_change_coverage(["src/gen/parser.py"], {},
                                              exempt=padded) == ["src/gen/parser.py"], \
        "the raw mutant must miss the declaration it was given"
    # The real gate normalizes both sides and matches it.
    require_change_coverage(["src/gen/parser.py"], {}, exempt=padded)


# ── it stays quiet ────────────────────────────────────────────────
def test_empty_spec_is_not_a_pass_by_default():
    """An empty spec must not be read as "everything passes".

    This is a trap specific to the delivery gate: if spec_claims is empty, a naive
    implementation computes dominance 0 and lets it through — that is "nothing was
    promised", not "every promise was upheld". The caller must explicitly declare an
    empty catalog for this to count as intentional.
    """
    q, p = make_claims(promised=set(), tested=set())
    spec = GateSpec(name="empty spec", spec_claims=q, test_claims=p,
                    catalog=["R1"], changed_files=[])
    # out-of-domain skip 1 (no account applies R1) → block
    with raises(DeliveryError):
        require_spec_alignment(spec)


def test_empty_catalog_is_refused():
    """An empty catalog must be refused; it cannot be read as "zero divergence = pass".

    This is the hole found by live testing on 2026-10-15; it is the same path as move
    five "empty the comparison domain to manufacture a zero readout" in
    examples/forgery_poc.py:
      · move five's entrance: applies is always false → out-of-domain skip 3 → blocked by "out-of-domain > 0 is a fail"
      · this test's entrance: the catalog is empty → all four quadrants are 0 and out-of-domain is 0 too → nothing blocks it
    "All 0" looks too much like "all agree". When the domain is empty,
    dominance/out-of-domain/common are all 0, so every later check passes naturally —
    which is why this one must be judged first.

    ★ The assertion must check the error message, not just assertRaises:
      if you only verify "a DeliveryError was raised", the empty catalog would be caught
      incidentally by the "out-of-domain skip" branch and the test would still be green —
      while the real empty-catalog defense is not working at all.
      Mutation evidence (changing `if not spec.catalog` to False) measured it: the
      assertRaises-only version stays green under the mutant; it is a fake test.
    """
    q, p = make_claims(promised={"R1"}, tested={"R1"})
    spec = GateSpec(name="empty catalog", spec_claims=q, test_claims=p,
                    catalog=[], changed_files=[])
    with raises(DeliveryError) as e:
        require_spec_alignment(spec)
    msg = str(e.value)
    assert e.value.reason == "EMPTY_CATALOG", "it must be the empty-catalog defense that blocked it (criterion code names it)"
    assert "[DG:EMPTY_CATALOG]" in msg, "the message must carry the stable criterion code; the message language may vary"


def test_zero_quadrant_reading_is_refused():
    """A non-empty catalog whose four quadrants total 0 (applies always false) must also be refused.

    The difference from the previous test: that one is "the catalog is empty", this one
    is "there is a catalog but no item entered the domain". Both produce 0/0/0/0; the
    readout is identical, but the fix differs, so the wording must distinguish them.
    ★ As above: the message must be checked, or the "out-of-domain skip" branch catches
    it incidentally and the test becomes fake.
    """
    def no_apply_Q():
        return Claim(name="defines nothing", predicate=lambda k: False,
                     applies=lambda k: False, domain_note="spec item",
                     source="forged/SPEC.md", quote="- R1: ",
                     quote_source="- R1: a wrong password returns 401\n")

    def real_P():
        return Claim(name="test upholds R1", predicate=lambda k: k == "R1",
                     applies=lambda k: k in CATALOG, domain_note="spec item",
                     source="tests/test_x.py", quote="def test_r1",
                     quote_source="def test_r1(): assert True")

    spec = GateSpec(name="empty domain", spec_claims=[no_apply_Q()],
                    test_claims=[real_P()], catalog=CATALOG)
    with raises(DeliveryError) as e:
        require_spec_alignment(spec)
    msg = str(e.value)
    assert e.value.reason == "GATE_FAILED"
    assert any(p["kind"] == "EMPTY_EFFECTIVE_DOMAIN" for p in e.value.problems), \
        "it must be the empty-domain defense that blocked it (problems.kind names it, not the message)"


def test_gate_blocks_forgery_poc_move_five():
    """Throw forgery_poc's move five at the delivery gate unchanged; it must be blocked.

    This connects the two files: the PoC records "which moves can fool a gate", and the
    delivery gate is the real gate. The PoC says move five passes (it can fool compare),
    and the delivery gate must prove it can block it — otherwise the capability
    declaration table is self-referential.
    """
    from forgery_poc import forge_empty_domain, measure
    # Precondition: move five really can fool compare (otherwise this test is meaningless)
    assert measure("empty comparison domain yields a zero readout") == "passes", "move five's premise changed; re-evaluate"

    # Move five's core trick: applies always false → four quadrants 0/0/0/0, out-of-domain = 3
    forged = Claim(name="defines nothing", predicate=lambda cap: False,
                   applies=lambda cap: False, domain_note="spec item",
                   source="forged/SPEC.md", quote="- R1: promised before",
                   quote_source="")
    real = Claim(name="test upholds R1", predicate=lambda k: k == "R1",
                 applies=lambda k: k in CATALOG, domain_note="spec item",
                 source="tests/test_x.py", quote="def test_r1",
                 quote_source="def test_r1(): assert True")
    spec = GateSpec(name="move five measured", spec_claims=[forged],
                    test_claims=[real], catalog=CATALOG)
    with raises(DeliveryError) as e:
        require_spec_alignment(spec)
    kinds = {p["kind"] for p in e.value.problems}
    assert kinds & {"OUT_OF_DOMAIN", "EMPTY_EFFECTIVE_DOMAIN"}, \
        f"move five must be blocked by the empty-domain/out-of-domain defense; got {kinds}"


def test_guards_still_apply_through_the_gate():
    """The three gates still bite through the delivery gate — the delivery gate must not bypass the underlying gates."""
    liar = Claim(name="liar", predicate=lambda x: True,
                 applies=lambda x: x in CATALOG,
                 domain_note="spec item", source="auth-spec/SPEC.md",
                 quote="- R1: ", quote_source=SPEC_TEXT,
                 source_tests=(("R1", False),))     # R1 is clearly there in the corpus
    with raises(SourceTestError):
        check_alignment(GateSpec(name="x", spec_claims=[liar],
                                 test_claims=[liar], catalog=CATALOG))


# ── mutation evidence ──────────────────────────────────────────────
def test_mutation_always_passing_gate_is_caught():
    """Change the delivery gate to always let things through, and the test must go red on the spot.

    This is why this file exists. Once the delivery gate silently fails, the report still
    prints, the format still matches, it just no longer blocks anything — the most
    dangerous failure mode: it disguises itself as a pass.
    """
    def broken_gate(spec):
        return {"common": 0, "divergence": 0, "dominance": 0,
                "neither": 0, "out_of_domain": 0,
                "dominance_witnesses": [], "divergence_witnesses": [],
                "report": "(looks perfect)"}

    # The broken gate: no reaction to the R4/R5 gaps
    q, p = make_claims(promised={"R1", "R2", "R3", "R4", "R5"},
                       tested={"R1", "R2", "R3"})
    spec = GateSpec(name="m", spec_claims=q, test_claims=p,
                    catalog=CATALOG, changed_files=["src/auth.py"],
                    file_coverage=FILE_COVERAGE)
    broken_gate(spec)                        # the mutant: silently lets it through

    # The real gate must block; the difference between the two is the criterion
    with raises(DeliveryError):
        require_spec_alignment(spec)


def test_mutation_removing_coverage_gate_is_caught():
    """Remove the coverage gate, and the test must go red."""
    def broken_require_change_coverage(changed_files, file_coverage, exempt=()):
        return None
    # The mutant has no reaction to an unregistered file
    broken_require_change_coverage(["src/payment.py"], {"src/a.py": ["R1"]})
    # The real gate must raise
    with raises(CoverageError):
        require_change_coverage(["src/payment.py"], {"src/a.py": ["R1"]})


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


# ── 2.1 GateSpec unguarded field (red-first tests) ────────────────
# Contract source: this repository's refinement landing batch §2.1 (frozen; see the
# corresponding CHANGELOG.md entry)
#   · GateSpec gains unguarded: Sequence[UnguardedItem] = (), whose elements carry
#     (item name, reason)
#   · require_spec_alignment automatically generates an explicit negative P-side claim
#     for unguarded items, with a separate report section "registered as not upheld"
#   · unguarded items must carry a reason; those without one are downgraded to out_of_domain
#   · dimension: legitimate unguarded items are excluded from both out_of_domain and
#     dominance and placed in a separate report section
# This section is the independent acceptance gate for the test→implementation phase:
# the implementer follows it, and a red result must point at a missing capability.

def _mk_unguarded(item, reason):
    """Construct an unguarded item (contract-frozen order: item name first, reason second).

    Prefer the implementer's exported UnguardedItem (positional construction, no
    dependency on field names); fall back to a plain two-tuple when it is not
    implemented — a red-first failure must point at "the field/behavior does not exist",
    not die while constructing the fixture.
    """
    try:
        from delivery_gate import UnguardedItem
    except ImportError:
        return (item, reason)
    return UnguardedItem(item, reason)


def test_unguarded_with_reason_registers_and_passes():
    """An unguarded item with a reason: the gate lets it through + the report has a separate "registered as not upheld" section.

    R4 is promised by the spec and not upheld by the tests — originally a dominance gap
    (which blocks delivery). After explicit registration as not upheld (with a reason),
    it is removed from dominance, the delivery gate lets it through, and the report lists
    it separately for a human to audit "what debt this batch carries".
    """
    q, p = make_claims(promised={"R1", "R2", "R3", "R4"},
                       tested={"R1", "R2", "R3"})
    spec = GateSpec(name="registered not upheld", spec_claims=q, test_claims=p,
                    catalog=["R1", "R2", "R3", "R4"],
                    unguarded=[_mk_unguarded("R4", "not consumed downstream; not delivered this batch")])
    out = require_spec_alignment(spec)
    assert out["dominance"] == 0, "a registered not-upheld item must not count as a dominance gap"
    assert out["out_of_domain"] == 0, "a registered not-upheld item must not count as an out-of-domain skip"
    assert [item for item, _ in out["registered_unguarded"]] == ["R4"], \
        "registered not-upheld items travel in structured fields, not as a section title scraped from the report"


def test_unguarded_without_reason_degrades_to_out_of_domain():
    """An unguarded item without a reason: downgraded to out_of_domain, not listed in the "registered as not upheld" section.

    A not-upheld item without a reason is indistinguishable from "forgot to list it" —
    block it as an out-of-domain skip, forcing the reason to be supplied.
    An empty reason string counts as absent (this test anchors the empty-string form).
    """
    q, p = make_claims(promised={"R1", "R2", "R3", "R4"},
                       tested={"R1", "R2", "R3"})
    spec = GateSpec(name="missing reason", spec_claims=q, test_claims=p,
                    catalog=["R1", "R2", "R3", "R4"],
                    unguarded=[_mk_unguarded("R4", "")])
    with raises(DeliveryError) as e:
        require_spec_alignment(spec)
    msg = str(e.value)
    assert any(p["kind"] == "OUT_OF_DOMAIN" for p in e.value.problems), \
        "a missing reason must be downgraded to OUT_OF_DOMAIN (criterion code names it)"
    assert e.value.unguarded_registered == (), "a downgraded item must not enter the 'registered as not upheld' structured list"


def test_unguarded_excluded_from_out_of_domain_and_dominance_counts():
    """Dimension exclusion: legitimate unguarded items do not mix into the out_of_domain / dominance counts.

    R9 is a genuine out-of-domain item (neither account recognizes it), and R4 is
    registered as not upheld. The two must be counted separately: the out-of-domain count
    contains only R9, and dominance does not contain R4.
    """
    q, p = make_claims(promised={"R1", "R2", "R3", "R4"},
                       tested={"R1", "R2", "R3"})
    spec = GateSpec(name="dimension exclusion", spec_claims=q, test_claims=p,
                    catalog=["R1", "R2", "R3", "R4", "R9"],
                    unguarded=[_mk_unguarded("R4", "a reason")])
    out = check_alignment(spec)
    assert out["dominance"] == 0, "R4 is registered as not upheld; it must not enter dominance"
    assert out["out_of_domain"] == 1, (
        "the out-of-domain count should contain only R9; R4 must not mix into out_of_domain")
    assert [item for item, _ in out["registered_unguarded"]] == ["R4"], \
        "registered not-upheld items travel in structured fields (no section search in the full report)"


def test_unguarded_absent_keeps_current_behavior():
    """Defaults unchanged: without unguarded, behavior matches the status quo exactly (regression protection).

    Dominance gaps still block and still name items; the report must not grow a
    "registered as not upheld" section out of nowhere.
    """
    q, p = make_claims(promised={"R1", "R2", "R3", "R4", "R5"},
                       tested={"R1", "R2", "R3"})
    spec = GateSpec(name="default regression", spec_claims=q, test_claims=p,
                    catalog=CATALOG, changed_files=["src/auth.py"],
                    file_coverage=FILE_COVERAGE)
    with raises(DeliveryError) as e:
        require_spec_alignment(spec)
    msg = str(e.value)
    witnesses = [w for p in e.value.problems if p["kind"] == "DOMINANCE"
                 for w in p.get("witnesses", ())]
    assert {"R4", "R5"} <= set(witnesses), f"dominance witnesses must name items; got {witnesses}"
    assert e.value.unguarded_registered == (), "without unguarded registrations the structured list must be empty"




def test_unguarded_degraded_strips_same_name_p_claim():
    """A downgraded item must strip the old P-side claim with the same name — otherwise it appears twice and pollutes the dimension.

    R4 without a reason is downgraded to out-of-domain on the premise that the P side has
    "no definition" for it. If the old P claim (applies=True, predicate false for R4) is
    not stripped, R4 lands in dominance: the correct version gives out_of_domain=1 /
    dominance=0, the mutant (no stripping) gives 0/1.
    ★ Judge with structured counts, not a substring of the full report — DeliveryError
    always appends the complete report, and "out-of-domain skip" satisfies any
    blocking-style implementation, so it has no discriminating power
    (mutation C lesson: 19/19 false green).
    """
    q, p = make_claims(promised={"R1", "R2", "R3", "R4"},
                       tested={"R1", "R2", "R3"})
    spec = GateSpec(name="downgrade stripping", spec_claims=q, test_claims=p,
                    catalog=["R1", "R2", "R3", "R4"],
                    unguarded=[_mk_unguarded("R4", "")])
    out = check_alignment(spec)
    assert out["out_of_domain"] == 1, (
        "after stripping the old P claim, R4 should be undefined and fall into the out-of-domain skip (out-of-domain count = 1)")
    assert out["dominance"] == 0, (
        "an unstripped same-name old P-side claim would judge R4 as dominance (dimension pollution)")


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
breakingdiff core red-first tests: zero valid comparison points, double-negative
equivalence, witness truncation
================================================================================
The core (`scripts/breakingdiff.py`) is the one module every consumer shares —
delivery_gate, the casestudy port reference, the receipt writers, forgery_poc.
These three silences are all "the readout looks normal while nothing was
compared", which is why they are pinned here and not in a consumer's test:

  A1  a comparison domain that contributes zero valid points still rendered a
      normal four-quadrant report and a `Disjoint over the comparison domain`
      verdict. The readout must say "zero valid comparison points" at the top,
      and `verdict()` must not reuse the disjoint wording. It must keep
      returning instead of raising: delivery_gate/forgery_poc consume the
      return value of an empty-domain compare on purpose.
  A2  an all-false domain (P and Q both false everywhere: common = divergence =
      dominance = 0, neither = total) is not "disjoint over the domain" — both
      accounts agree, they agree on "no". `verdict_key()` stays `disjoint` (the
      cross-language contract in casestudy/port/claims.json), only the
      human-readable wording gains the double-negative note.
  A5  witnesses are truncated at `max_witness` silently; the report must name
      the remainder (`… first N of M, K not listed`), for the pairwise
      divergence/dominance columns and for compare_n's split witnesses.
  N   the same zero-domain silence on the N-account path, where it must
      distinguish "the parameter domain is empty" from "every point fell out of
      domain".

Contract shape pinned here (backward compatible, no consumer breakage):

    DiffResult.domain_total   int   every parameter point iterated, skips included
    DiffResult.in_domain      int   points that entered the four quadrants (= total)
    NWayResult.domain_total   int   every parameter point iterated, skips included
    NWayResult.in_domain      int   points that entered the shape statistics (= total)

First red: this file was run before the core fix and every one of the tests
below failed (AttributeError for the new fields, assertion failures for the
wording/banner). The implementation landed only after that red was recorded; the
mutation evidence for each protection is in the task report, not in this file.

No pytest dependency. Usage: python scripts/breakingdiff_test.py
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from breakingdiff import (Claim, DiffResult, NWayResult, compare, compare_n,
                          render, render_n, verdict, verdict_key)  # noqa: E402


# ── fixtures: ordinary claims with nothing to prove but the readout shape ──────
def all_true(_x):
    return True


def all_false(_x):
    return False


def mk_claim(name, predicate, applies=None):
    """A minimal well-formed Claim: provenance binding satisfied, no source_tests
    (the source self-test gate is silent on a claim with zero examples, as
    designed), no interpretations."""
    return Claim(
        name=name,
        predicate=predicate,
        applies=applies if applies is not None else all_true,
        domain_note="scripts/breakingdiff_test.py fixture domain",
        source="scripts/breakingdiff_test.py (unit-test fixture, not an external claim)",
        quote="readout-shape fixture (unit test)",
    )


def report_lines(text):
    return [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]


def top_banner(text):
    """The first warning line of the report; '' when the report carries none."""
    for line in report_lines(text):
        if line.lstrip().startswith("⚠️"):
            return line.strip()
    return ""


def banner_index(text):
    """Position of the top banner among the non-blank lines (0-based)."""
    for i, line in enumerate(report_lines(text)):
        if line.lstrip().startswith("⚠️"):
            return i
    return -1


# ═══════════════════════════════════════════════════════════════════════════════
# A1 — zero valid comparison points: pair/counter accounting, banner, verdict
# ═══════════════════════════════════════════════════════════════════════════════
def test_zero_domain_compare_returns_for_consumers():
    """Empty domain: compare returns a DiffResult, it does not raise.

    delivery_gate (an empty effective catalog becomes a reasoned refusal, not an
    exception from the core) and forgery_poc move five (an always-false applies
    manufactures the zero readout) both call compare and consume its return
    value. Raising here would move a readout problem into an uncaught crash."""
    P = mk_claim("P defines nothing", all_true, applies=all_false)
    Q = mk_claim("Q ordinary", all_false)
    r = compare(P, Q, [])
    assert isinstance(r, DiffResult), f"compare must return a DiffResult on an empty domain, got {type(r)!r}"
    assert r.domain_total == 0, f"an empty domain iterates zero points, got domain_total={r.domain_total}"
    assert r.in_domain == 0, f"no point entered the quadrants, got in_domain={r.in_domain}"
    assert r.total == 0, f"total stays the quadrant sum and must be 0, got {r.total}"
    assert r.out_of_domain == 0, f"an empty domain has no skips, got {r.out_of_domain}"


def test_empty_domain_banner_is_at_top_and_names_the_zero():
    """The empty domain gets the exact top banner A1 specifies, above provenance.

    `out-of-domain 0` and `domain 0 points` must both be present: an empty
    parameter domain and an all-skipped domain are different causes, and reading
    "0 out-of-domain" tells the operator it is the caller's domain that is empty,
    not applies. The report must also stop offering a four-quadrant story as if
    it had one: the dedicated verdict wording replaces the disjoint wording."""
    P = mk_claim("P defines nothing", all_true, applies=all_false)
    Q = mk_claim("Q ordinary", all_false)
    out = render(P, Q, compare(P, Q, []))
    want = "⚠️ zero valid comparison points: domain 0 points, 0 entering the quadrant map (out-of-domain 0)"
    assert top_banner(out) == want, f"empty-domain banner drifted: got {top_banner(out)!r}, want {want!r}"
    assert banner_index(out) == 3, (
        "the zero-domain banner must sit at the top of the report (after the two title rules), "
        f"got non-blank line index {banner_index(out)}")
    assert "Disjoint over the comparison domain" not in out, (
        "an empty domain must not be rendered as 'disjoint over the comparison domain': nothing was compared")


def test_all_out_of_domain_banner_names_the_skips():
    """Every point skipped by applies: banner N/M counts and dedicated verdict."""
    P = mk_claim("P applies only to a", all_true, applies=lambda x: x == "a")
    Q = mk_claim("Q ordinary", all_false)
    domain = ["x", "y"]
    r = compare(P, Q, domain)
    assert (r.domain_total, r.in_domain, r.out_of_domain) == (2, 0, 2), (
        "all points must be counted as iterated and skipped, none as in-domain: "
        f"got domain_total={r.domain_total} in_domain={r.in_domain} out_of_domain={r.out_of_domain}")
    out = render(P, Q, r)
    want = "⚠️ zero valid comparison points: domain 2 points, 0 entering the quadrant map (out-of-domain 2)"
    assert top_banner(out) == want, f"all-out-of-domain banner drifted: got {top_banner(out)!r}, want {want!r}"


def test_zero_domain_verdict_has_dedicated_wording():
    """verdict() gets its own "no valid comparison points" wording, not disjoint."""
    P = mk_claim("P defines nothing", all_true, applies=all_false)
    Q = mk_claim("Q ordinary", all_false)
    r = compare(P, Q, ["x"])
    v = verdict(r, P, Q)
    assert "no valid comparison points" in v.lower(), (
        f"the zero-domain verdict must say there are no valid comparison points, got {v!r}")
    assert "Disjoint" not in v, f"the zero-domain verdict must not reuse the disjoint wording, got {v!r}"


def test_domain_total_counts_iterated_points_and_in_domain_matches_quadrants():
    """The accounting contract on a normal mixed domain (backward compatible).

    domain_total counts every iterated point (skips included); in_domain is the
    quadrant sum, i.e. the number that the percentages are taken over. Keeping
    both means a consumer can reconcile 'nothing was compared' without re-counting
    the domain itself."""
    P = mk_claim("P applies to a,b,c", lambda x: x == "b", applies=lambda x: x in ("a", "b", "c"))
    Q = mk_claim("Q applies to b,c,d", lambda x: x in ("b", "c"), applies=lambda x: x in ("b", "c", "d"))
    r = compare(P, Q, ["a", "b", "c", "d"])
    assert r.domain_total == 4, f"domain_total must count every iterated point, got {r.domain_total}"
    assert r.out_of_domain == 2, f"a and d are skipped, got out_of_domain={r.out_of_domain}"
    assert r.in_domain == 2, f"only b and c enter the quadrants, got in_domain={r.in_domain}"
    assert r.in_domain == r.total == r.common + r.divergence + r.dominance + r.neither, (
        "in_domain and total must both stay the quadrant sum: "
        f"in_domain={r.in_domain} total={r.total}")
    assert r.domain_total == r.in_domain + r.out_of_domain, (
        "every iterated point is either in-domain or skipped: "
        f"{r.domain_total} != {r.in_domain} + {r.out_of_domain}")


def test_normal_report_has_no_zero_domain_banner():
    """Boundary: a domain with valid points must not grow the zero-domain banner."""
    P = mk_claim("P true on a", lambda x: x == "a")
    Q = mk_claim("Q true on a", lambda x: x == "a")
    out = render(P, Q, compare(P, Q, ["a", "b"]))
    assert "zero valid comparison points" not in out, (
        "a two-point domain with valid comparison points must not claim a zero-domain readout")
    assert banner_index(out) == -1, "the normal report must not start with a warning banner"


# ═══════════════════════════════════════════════════════════════════════════════
# A2 — all-false domain: double negative, key unchanged
# ═══════════════════════════════════════════════════════════════════════════════
def test_all_false_domain_verdict_is_double_negative():
    """P and Q both false everywhere: "equivalent (double negative)", not disjoint.

    This is the same quadrant shape as a genuinely disjoint domain — zero in
    common/divergence/dominance and everything in neither — so only the wording
    can tell the two apart. The cross-language key stays `disjoint` (that is the
    stable contract); the human wording must not claim the accounts disagree."""
    P = mk_claim("P false everywhere", all_false)
    Q = mk_claim("Q false everywhere", all_false)
    r = compare(P, Q, ["a", "b", "c"])
    assert (r.common, r.divergence, r.dominance, r.neither) == (0, 0, 0, 3), (
        "fixture precondition: every point lands in neither, "
        f"got {(r.common, r.divergence, r.dominance, r.neither)}")
    assert verdict(r, P, Q) == "Equivalent over the comparison domain (double negative)", (
        f"all-false domain wording drifted: {verdict(r, P, Q)!r}")
    assert "Equivalent over the comparison domain (double negative)" in render(P, Q, r), (
        "the report's verdict line must carry the double-negative wording")


def test_all_false_domain_keeps_the_disjoint_verdict_key():
    """Stability: the fix is presentation only; the cross-language key does not move.

    casestudy/port, the Go and Rust ports and casestudy/port/claims.json all read
    `verdict_key()`. Changing it for the all-false shape would be port drift."""
    P = mk_claim("P false everywhere", all_false)
    Q = mk_claim("Q false everywhere", all_false)
    assert verdict_key(compare(P, Q, ["a", "b"])) == "disjoint", (
        "verdict_key() must stay 'disjoint' for the all-false shape (cross-language contract)")


def test_partial_equivalence_keeps_the_plain_equivalent_wording():
    """Boundary: only neither == total gets the double-negative note.

    Ordinary equivalence (some common points, some neither) must keep the plain
    wording; painting every equivalence as "double negative" would erase the
    distinction the note exists to draw."""
    P = mk_claim("P true on a,b", lambda x: x in ("a", "b"))
    Q = mk_claim("Q true on a,b", lambda x: x in ("a", "b"))
    r = compare(P, Q, ["a", "b", "c"])
    assert (r.common, r.neither) == (2, 1), f"fixture precondition broken: {(r.common, r.neither)}"
    assert verdict(r, P, Q) == "Equivalent over the comparison domain", (
        f"ordinary equivalence wording must stay plain, got {verdict(r, P, Q)!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# A5 — witness truncation must name the remainder
# ═══════════════════════════════════════════════════════════════════════════════
def test_witness_truncation_is_announced_for_both_columns():
    """Divergence 12, dominance 10, cap 4: both columns carry the remainder line."""
    domain = list(range(30))
    P = mk_claim("P covers 0..11", lambda x: x < 12)
    Q = mk_claim("Q covers 20..29", lambda x: x >= 20)
    r = compare(P, Q, domain, max_witness=4)
    assert (r.divergence, r.dominance) == (12, 10), f"fixture precondition broken: {(r.divergence, r.dominance)}"
    assert len(r.divergence_witnesses) == len(r.dominance_witnesses) == 4, (
        "fixture precondition: both witness lists are capped at 4, "
        f"got {len(r.divergence_witnesses)} / {len(r.dominance_witnesses)}")
    out = render(P, Q, r)
    assert "… first 4 of 12, 8 not listed" in out, (
        "the divergence witness remainder is silent: the report must say how many are not listed")
    assert "… first 4 of 10, 6 not listed" in out, (
        "the dominance witness remainder is silent: the report must say how many are not listed")


def test_witnesses_under_the_cap_carry_no_truncation_notice():
    """Boundary: no cap hit, no remainder line (the notice is a fact, not decoration)."""
    P = mk_claim("P true on a,c", lambda x: x in ("a", "c"))
    Q = mk_claim("Q true on b,c", lambda x: x in ("b", "c"))
    out = render(P, Q, compare(P, Q, ["a", "b", "c"], max_witness=8))
    assert "not listed" not in out, (
        "the report claims truncated witnesses although both lists fit under the cap")


# ═══════════════════════════════════════════════════════════════════════════════
# N — the N-account path: zero-domain banner distinguishes the two causes
# ═══════════════════════════════════════════════════════════════════════════════
def nway_claims():
    return [mk_claim("v1", all_true), mk_claim("v2", all_true), mk_claim("v3", all_true)]


def test_nway_empty_domain_banner_says_the_domain_is_empty():
    """Empty parameter domain: banner names the empty domain, total semantics intact."""
    claims = nway_claims()
    r = compare_n(claims, [])
    assert isinstance(r, NWayResult), f"compare_n must return an NWayResult, got {type(r)!r}"
    assert (r.domain_total, r.in_domain, r.total, r.out_of_domain) == (0, 0, 0, 0), (
        "an empty domain must count nothing and stay total=0: "
        f"got domain_total={r.domain_total} in_domain={r.in_domain} total={r.total} out={r.out_of_domain}")
    out = render_n(claims, r)
    banner = top_banner(out)
    assert banner.startswith("⚠️ zero valid comparison points:"), (
        f"the empty N-way domain must start with the zero-domain banner, got {banner!r}")
    assert "parameter domain is empty" in banner, (
        f"the banner must distinguish the empty domain from a fully skipped one, got {banner!r}")
    assert banner_index(out) == 3, (
        "the N-way zero-domain banner must sit at the top (after the two title rules), "
        f"got line index {banner_index(out)}")


def test_nway_all_out_of_domain_banner_says_every_point_fell_out():
    """All-skipped domain: same banner family, different cause, counts named."""
    claims = [mk_claim("v1", all_true, applies=lambda x: x == "a"),
              mk_claim("v2", all_true, applies=lambda x: x == "a"),
              mk_claim("v3", all_true, applies=lambda x: x == "a")]
    r = compare_n(claims, ["x", "y", "z"])
    assert (r.domain_total, r.in_domain, r.total, r.out_of_domain) == (3, 0, 0, 3), (
        "every point must be counted as iterated and skipped: "
        f"got domain_total={r.domain_total} in_domain={r.in_domain} total={r.total} out={r.out_of_domain}")
    out = render_n(claims, r)
    banner = top_banner(out)
    assert banner.startswith("⚠️ zero valid comparison points:"), (
        f"the fully skipped N-way domain must start with the zero-domain banner, got {banner!r}")
    assert "0 entering the shape map" in banner and "all 3 point(s) fell out of domain" in banner, (
        f"the banner must name the all-skipped cause and the count, got {banner!r}")


def test_nway_total_semantics_unchanged_while_domain_total_counts_every_point():
    """Backward compatibility: total stays the in-domain count; domain_total is new."""
    claims = [mk_claim("v1", lambda x: x % 2 == 0),
              mk_claim("v2", lambda x: x > 2),
              mk_claim("v3", lambda x: x < 5, applies=lambda x: x != 3)]
    r = compare_n(claims, [1, 2, 3, 4, 5, 6])
    assert r.domain_total == 6, f"domain_total must count every iterated point, got {r.domain_total}"
    assert r.out_of_domain == 1, f"x=3 is skipped by v3, got out_of_domain={r.out_of_domain}"
    assert r.in_domain == r.total == 5, (
        f"in_domain and total stay the in-domain count, got in_domain={r.in_domain} total={r.total}")
    shape_sum = (r.all_true + r.all_false + r.split
                 + sum(r.outliers.values()) + sum(r.pioneers.values()))
    assert shape_sum == r.total, f"the shape table must still sum to total: {shape_sum} != {r.total}"
    assert r.domain_total == r.in_domain + r.out_of_domain, (
        f"each iterated point is in-domain or skipped: {r.domain_total} != {r.in_domain} + {r.out_of_domain}")


def test_nway_split_witness_truncation_is_announced():
    """compare_n's split witnesses are capped too; the remainder must be named.

    Four accounts, 12 points, exactly two true per point → every point is split.
    Cap 3 leaves 9 unlisted; a silent cap would read as "only 3 split points"."""
    claims = []
    for j in range(4):
        claims.append(mk_claim(f"v{j}", (lambda jj: (lambda x: (x + jj) % 2 == 0))(j)))
    r = compare_n(claims, list(range(12)), max_witness=3)
    assert r.split == 12, f"fixture precondition: every point should be split, got split={r.split}"
    assert len(r.split_witnesses) == 3, f"fixture precondition: cap 3, got {len(r.split_witnesses)}"
    out = render_n(claims, r)
    assert "… first 3 of 12, 9 not listed" in out, (
        "the split witness remainder is silent: the report must say how many are not listed")


# ── harness (same shape as the other script-level tests in this repo) ──────────
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

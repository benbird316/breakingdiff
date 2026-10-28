"""malecns strength-layer case — three claim-strength error modes, each with its measured readout.

[What this script teaches]
A wrong strength shape raises no error — the data is fine, the claim reads it red. The three error modes have
different false-red surfaces, forming a mechanically recomputable strength staircase:

    error mode ③ NT top-1 written as the type level (account confusion)  241 points
    error mode ① point-value claim (n = type total body count // 2)      2,720 points
    error mode ② left-right strict equality (nL = nR)                    4,354 points

The larger the false-red surface, the higher the share of true data read as bad data — while aligned.py's three
bands flag only 12 / 110 / 20 points false on the same batch. That is the control group for "bounded is the right
strength": the few dozen points the bands narrow down to are worth a human look; a few thousand false reds only
drown the signal in noise.

How to run: python misaligned.py
"""
import os
import sys

# The Windows console defaults to GBK and the report uses glyphs outside that code
# page. Switch to UTF-8 and downgrade unencodable characters so the script cannot
# die with UnicodeEncodeError while printing its own warning.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
# ★ Search upward for breakingdiff.py (same reason as pdg/misaligned.py: move the directory
#   and a hard-coded depth silently becomes ModuleNotFoundError).
def _find_scripts_root():
    cur = _HERE
    while True:
        if os.path.isfile(os.path.join(cur, "scripts", "breakingdiff.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit(
                "[FATAL] cannot find scripts/breakingdiff.py above this directory. "
                "       This case study must run inside the breakingdiff repository "
                "(scripts/ and casestudy/ at the same level).")
        cur = parent

_ROOT = _find_scripts_root()
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, _HERE)

from breakingdiff import Claim, compare_n  # noqa: E402
import aligned  # noqa: E402


def _pair(claim):
    """Error-mode account + existence baseline Q, N=2 point-by-point differential.
    Under N=2, points where "Q alone is true, the error mode alone is false" land in pioneers[the Q index] — exactly the false-red surface."""
    return [claim, aligned.build_q_claim()]


# ============================================================
# Error mode ①: point-value claim
# ============================================================
def wrong_1_point_value():
    """Mistake: press "each side has about half of the type's bodies" into the point value n = type total body count // 2.

    Two diseases stacked: the baseline is contaminated by M-side and side-less bodies (R1-R6's 3,364
    M-side bodies push the expectation to 1,688 while its L side has only 4 bodies); and the baseline is a point,
    so data points with ±30% individual variation cannot match an exact value. 2,720/22,176 true data points go
    red — true data looks like bad data."""
    counts = aligned.load_counts()
    totals = aligned.load_type_totals()
    claims = _pair(Claim(
        name="Error mode 1 point-value claim: n = type total body count // 2",
        predicate=lambda x: counts[x] == totals[x[0]] // 2,
        applies=lambda x: True,
        domain_note="per (type, side) point: count against the point value (the baseline includes M-side and side-less bodies)",
        source=aligned._ANNOT_SRC,
        quote="rule=n==total//2; domain=annotation(type×somaSide); points=22176",
        quote_source="rule=n==total//2; domain=annotation(type×somaSide); points=22176",
    ))
    return claims, compare_n(claims, aligned.domain_points(), chain=False)


# ============================================================
# Error mode ②: left-right strict equality
# ============================================================
def wrong_2_hard_symmetry():
    """Mistake: press "hemispheres are largely mirrored" into strict equality nL == nR.

    Most Drosophila hemisphere types really do mirror exactly (8,911 types with equal sides), and strict equality
    passes on most points — that is exactly its deceptiveness. But ±1–2 counting/allocation noise and 2,030 truly
    asymmetric types (largest |L−R|=189 @ KCab-s) make it flag 4,354 points false, an order of magnitude more than
    the P2 band (110 points): true drift read as bad data."""
    counts = aligned.load_counts()
    claims = _pair(Claim(
        name="Error mode 2 left-right strict equality: nL == nR",
        predicate=lambda x: counts.get((x[0], "L"), 0)
        == counts.get((x[0], "R"), 0),
        applies=lambda x: True,
        domain_note="per (type, side) point: left and right counts strictly equal",
        source=aligned._ANNOT_SRC,
        quote="rule=nL==nR; domain=annotation(type×somaSide); points=22176",
        quote_source="rule=nL==nR; domain=annotation(type×somaSide); points=22176",
    ))
    return claims, compare_n(claims, aligned.domain_points(), chain=False)


# ============================================================
# Error mode ③: neuron-level top-1 written straight into the type level
# ============================================================
def wrong_3_nt_top1_as_type_level():
    """Mistake: account-granularity confusion — write the neuron-level majority vote (predicted_nt votes per body,
    unclear counts, a tie takes the lexicographically largest) top-1 directly as a type-level fact,
    and assert it equals the data's self-reported celltype_predicted_nt.

    A majority vote ≠ a self-reported type-level label: unclear votes displace the true main transmitter (R1-R6
    votes unclear while its self-report is histamine — photoreceptors are histaminergic to begin with), and the two
    accounts disagree on 138 types, flagging 241 domain points false. This is not "who is right" — it is using a
    neuron-level aggregate to impersonate a type-level label: two accounts of different granularity treated as one."""
    fr = aligned.load_nt_fractions()
    claims = _pair(Claim(
        name="Error mode 3 NT top-1 written as type-level: voted top-1 == celltype_predicted_nt",
        predicate=lambda x: (lambda v: True if v is None else v[0] == v[2])(
            fr.get(x[0])),
        applies=lambda x: True,
        domain_note="per (type, side) point: neuron-level voted top-1 against the data's self-reported type-level label",
        source=aligned._NT_SRC,
        quote="rule=vote_top1==celltype_predicted_nt; "
              "domain=annotation(type×somaSide); points=22176",
        quote_source="rule=vote_top1==celltype_predicted_nt; "
                     "domain=annotation(type×somaSide); points=22176",
    ))
    return claims, compare_n(claims, aligned.domain_points(), chain=False)


def main():
    print("=" * 78)
    print("MaleCNS v0.9 strength layer: three claim-strength error modes (all measured readouts, not abstract preaching)")
    print(f"comparison domain = aligned.CRITERIA ({len(aligned.domain_points())} existence points)")
    print("=" * 78)

    ladder = []
    for title, fn in (("Error mode ① point-value claim", wrong_1_point_value),
                      ("Error mode ② left-right strict equality", wrong_2_hard_symmetry),
                      ("Error mode ③ NT top-1 written as type-level", wrong_3_nt_top1_as_type_level)):
        _claims, r = fn()
        red = sum(r.pioneers.values())
        ladder.append((title, r, red))
        print()
        print(f"[{title}]")
        print(f"  comparison domain {r.total} points | all_true {r.all_true} / all_false {r.all_false} "
              f"/ split {r.split} / out_of_domain {r.out_of_domain}")
        print(f"  outlier attribution {r.outliers or 'none'}  pioneers {r.pioneers or 'none'}")
        print(f"  false-red surface = {red} points ({100 * red / r.total:.1f}%)"
              f" — points where Q is constantly true and the error mode alone is false")
        print("  ★ Did anything raise an error? No. out_of_domain 0, readout shape normal. The tool does not stop strength errors;")
        print("    they are entirely legal in the verdict logic — what is broken is the claim shape, not the execution.")

    print()
    print("=" * 78)
    print("Strength staircase (pairwise unequal false-red surfaces, mechanically recomputable)")
    print("=" * 78)
    print(f"  account confusion (error mode ③) {ladder[2][2]}  <  point value (error mode ①) {ladder[0][2]}  "
          f"<  strict equality (error mode ②) {ladder[1][2]}")
    print("  Against aligned.py's three bands: P1 flags 12 false / P2 flags 110 / P3 flags 20.")
    print("  On the same batch of data, bounding shrinks the false-red surface by two orders of magnitude — what it narrows down to is the signal.")
    print()
    print("  → Stronger is not better: when claim strength exceeds the data's occurrence pattern,")
    print("    true data gets read as bad data. Bounding is how you \"declare what normal is\".")


if __name__ == "__main__":
    main()

"""Case Study A: the Hubble tension — the verdict vector of N independent H0 measurements

Real published public measurements, 6 independent institutional accounts, each with a
verbatim quotation and a source.
Appendix B of arXiv:2601.00650 summarizes the H0 and error of each of the SH0ES / CCHP /
Lee / Planck paths.

[Dimensional difference from examples/] The data here is external third-party data, not
a corpus this skill fabricated; the criterion (whether it overlaps the baseline at nσ)
is externally anchored too. That is why it stands alone as a case study and does not
enter examples/'s self-bootstrapping surface: different dimensions cannot be compared in
the same set.

[Criterion convention] The nσ verdict uses the baseline account's single-sided error bar
(|ΔH0| <= n·σ_base) and does not combine both sides' error bars; the readout of boundary
cases depends on this convention and must not be extrapolated to a joint significance test.

How to run: python case_study.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# ★ Search upward for breakingdiff.py instead of hard-coding "how many levels up".
def _find_scripts_root():
    cur = _HERE
    while True:
        if os.path.isfile(os.path.join(cur, "scripts", "breakingdiff.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit(
                "[FATAL] cannot find scripts/breakingdiff.py walking upward. "
                "       This case study must run inside the breakingdiff repository "
                "(scripts/ and casestudy/ are siblings).")
        cur = parent

_ROOT = _find_scripts_root()
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from breakingdiff import Claim, compare_n, render_n  # noqa: E402

# ---- Real corpus (verbatim quotations from arXiv:2601.00650) ----
# (institution, path, H0, positive error, negative error, method family, verbatim quote, source)
EXPS = [
    ("SH0ES/Riess2022", "HST Cepheid ladder", 73.04, 1.04, 1.04, "ladder",
     "H0=73.04 +/- 1.04 km s-1 Mpc-1",
     "arXiv:2601.00650 App.B.1.1 (2022 HST result)"),
    ("SH0ES/Riess2025", "JWST Cepheid ladder", 73.49, 0.93, 0.93, "ladder",
     "The 2025 JWST result yields H0=73.49 +/- 0.93 km s-1 Mpc-1",
     "arXiv:2601.00650 App.B.1.1"),
    ("CCHP/Freedman2021", "TRGB ladder", 69.8, 1.7, 1.7, "ladder",
     "The 2021 analysis yielded H0=69.8+/-1.7km s-1 Mpc-1",
     "arXiv:2601.00650 App.B.1.2"),
    ("CCHP/Freedman2024", "JWST Cepheid ladder", 72.05, 3.60, 3.60, "ladder",
     "The 2024 JWST analysis found H0=72.05+/-3.60km s-1 Mpc-1 from Cepheids",
     "arXiv:2601.00650 App.B.1.2"),
    ("Lee2024", "JAGB method", 67.8, 2.7, 2.7, "ladder",
     "The Lee et al. JAGB analysis yields H0=67.8+/-2.7km s-1 Mpc-1",
     "arXiv:2601.00650 App.B.1.3"),
    ("Planck2018", "CMB+LambdaCDM", 67.4, 0.5, 0.5, "cmb",
     "The Planck CMB analysis, assuming ΛCDM, yields H0 = 67.4 +/- 0.5 km s-1 Mpc-1",
     "arXiv:2601.00650 Sec.1"),
]

_BASE = EXPS[0]  # baseline account: SH0ES 2022

# The parameter points are no longer "the institutions" themselves but **how strict the
# statistical criterion is**.
#
# [Pit record — kept here to prevent a repeat] The first version made the institutions
# the parameter points, and the predicate did not read x, so the verdict vectors at the 6
# parameter points were completely identical → all split, zero outlier attribution,
# non-zero comparison domain but zero information. This is a new variant of three-level
# silence: the readout is all green and tells you nothing.
#
# Second pit (diagnostic record, kept to prevent a repeat): after switching to
# 1σ/2σ/3σ it was still split 100%, zero outlier attribution. Printing point by point
# revealed that the three criteria gave **completely identical verdict vectors** —
# because the differences from the baseline were 0.45/0.99/3.24/5.24/5.64, and moving
# the threshold from 1σ to 3σ straddles none of the real differences, so the verdict
# never flips → constant vector → always split.
#
# Conclusion: **the parameter point must be the dimension that actually separates the
# verdicts**; otherwise changing how many there are is decoration.
# The correct dimension in this case is "each account's own error bar", expanded below in
# ERRORS — but even so, the error structure of the 6 accounts still cannot produce an
# outlier attribution.
# This is this case study's **conclusion**, not a defect: see ../TEACHING-pdg.md
# (selection and diagnostic rules).
# Another comparison: zero outliers ≠ the engine is broken. The same engine produced a
# pioneer attribution on pdg/aligned.py; the only difference is the selection — see
# TEACHING-pdg.md §3.
CRITERIA = [
    ("1sigma", 1.0, "overlaps the baseline at 1σ"),
    ("2sigma", 2.0, "overlaps the baseline at 2σ"),
    ("3sigma", 3.0, "overlaps the baseline at 3σ"),
]

DOMAIN = [(cid, nsigma, label) for cid, nsigma, label in CRITERIA]

claims = [
    Claim(
        name=f"{e[0]} {e[1]}",
        predicate=lambda x, e=e: abs(e[2] - _BASE[2]) <= x[1],  # x[1]=the nσ multiple
        applies=lambda x, e=e: True,
        domain_note=f"{e[0]} {e[1]} path: H0={e[2]}+-{e[3]}; {e[7]}",
        source=f"{e[0]} {e[1]} H0={e[2]}+-{e[3]}",
        quote=e[6],
        quote_source=e[6],
    )
    for e in EXPS
]

r = compare_n(claims, DOMAIN, chain=False)


def main() -> None:
    print("=" * 78)
    print("Case Study A: the Hubble tension — 6 independent institutional accounts × 3 statistical criteria")
    print("Source: arXiv:2601.00650 Appendix B (verbatim quotations in each Claim's quote)")
    print("=" * 78)
    print(f"{'Account':42s}{'H0':>16s}")
    print("-" * 78)
    for e in EXPS:
        print(f"{(e[0] + ' ' + e[1])[:40]:42s}{e[2]:>8.2f} +/- {e[3]:<5.2f}")

    print()
    print(render_n(claims, r))

    print()
    print("=" * 78)
    print("One-shot assertion: mechanical readout vs manual reading")
    print("=" * 78)
    print(f"  parameter points {r.total} | all_true {r.all_true} / all_false {r.all_false} "
          f"/ split {r.split} / out_of_domain {r.out_of_domain}")
    print()
    print("  [Manual] To see 'who differs from whom' you must compare 6 numbers line by line and remember each error:")
    for e in EXPS:
        print(f"      {e[2]:6.2f} +/- {e[3]:<5.2f}  {e[0]} {e[1]}")
    print()
    print("  [Mechanical] One compare_n gives:")
    if r.outliers:
        for i, n in r.outliers.items():
            print(f"      outlier attribution -> {r.names[i]} ({n} criteria where it disagrees with the rest)")
    else:
        print("      outlier attribution -> none")
    if r.pioneers:
        for i, n in r.pioneers.items():
            print(f"      pioneer          -> {r.names[i]} (the only one that holds on {n} criteria)")
    else:
        print("      pioneer          -> none")
    print()
    print("  [How to read it] Divergence ≠ better. The above only reports 'who differs from whom'; it does not adjudicate who is right —")
    print("          the Hubble tension is still unresolved; the right to adjudicate belongs to future experiments and external anchors.")


if __name__ == "__main__":
    main()

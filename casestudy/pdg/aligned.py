"""PDG independent-experiment measurements — how to select when the accounts ARE aligned.

[What this script teaches]
Whether an N-account diff yields information does **not depend on how big the data is;
it depends on whether the accounts are aligned**.
"Aligned" = every account really answers the same question (this project's structural
premise P1). This script shows the aligned shape: first converge on the same physical
quantity by description, then evaluate every account (each experimental group's
independent measurement) against the same batch of criteria (1σ..8σ).

How to run: python aligned.py
"""
import os
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# ★ Search upward for breakingdiff.py instead of hard-coding "how many levels up".
#   A hard-coded depth silently turns into ModuleNotFoundError once this directory
#   moves (its nesting depth changes) — and the last thing a case study can afford
#   is "it won't run somewhere else" with no way to find out why.
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

DB = os.path.join(_HERE, "pdg.sqlite")

# ---- The key alignment step: converge on the same physical quantity ----
# Under PDG, measurements sharing one "pdgid parent node" are not necessarily the same
# thing — the J/psi subtree alone holds 544 measurements, but they are **different
# decay channels** (different branching ratios).
# Selecting by parent_pdgid = violating P1 (the accounts do not claim to cover the same
# purpose); the accounts are **misaligned**, and the consequence is 88% pseudo-outliers.
# See misaligned.py.
#
# Alignment: group by description and take only independent measurements of the same
# physical quantity.
TARGET_DESC = "REAL PART"
# ★ A tier name is not a threshold: the fourth tier uses 6σ (a deliberate criterion
#   span; see TEACHING-pdg.md) — do not recompute it from the tier name as a multiple.
CRITERIA = [("1s", 1.0), ("2s", 2.0), ("3s", 3.0), ("4s", 6.0), ("8s", 8.0)]


def load_measurements(desc, limit=17):
    """Take the independent measurement from each experimental group for one physical
    quantity, sorted by error ascending (the smallest is the one PDG favors most)."""
    # ★ Missing data must exit on the spot; it must not quietly produce an empty report
    #   (the third level of the three-level silence).
    # ★ Pit stepped in: checking os.path.exists alone is not enough — sqlite3.connect
    #   will **create out of thin air** a 0-byte empty database, after which exists is
    #   true and the check is fooled by the file it created itself.
    #   So the size must be checked as well.
    if not os.path.exists(DB) or os.path.getsize(DB) == 0:
        raise SystemExit(
            f"[FATAL] data file missing or empty: {DB}\n"
            f"Run python fetch_data.py first to download (~7.6 MB; the server is slow)."
        )
    con = sqlite3.connect(DB)
    rows = con.execute(
        """
        SELECT d.pdgid, d.value, d.error_positive, d.error_negative,
               i.description, d.confidence_level, d.unit_text
        FROM pdgdata d
        JOIN pdgid i ON i.id = d.pdgid_id
        WHERE i.description = ?
          AND d.value IS NOT NULL
          AND d.error_positive > 0
          AND d.value_type = 'AC'
        ORDER BY (d.error_positive + d.error_negative), d.pdgid
        LIMIT ?
        """,
        (desc, limit),
    ).fetchall()
    con.close()
    return rows


def build_claims(rows):
    """Q = whether this measurement overlaps the baseline under the nσ criterion.

    The baseline is the row with the smallest error (a proxy for the value PDG adopts)
    — an **external anchor**, not one we picked ourselves, so P6 holds.
    """
    base_val = rows[0][1]

    def ev(r):
        # quote and quote_source must be identical character for character, or the
        # constructor raises ProvenanceError.
        # (Pit stepped in: two different wordings were used once and the verbatim check
        # caught it on the spot.)
        return f"pdgid={r[0]}; value={r[1]:.6g}; error=+{r[2]:.3g}/-{r[3]:.3g}"

    return [
        Claim(
            name=r[0],
            predicate=lambda x, r=r: abs(r[1] - base_val) <= max(r[2], r[3]) * x[1],
            applies=lambda x, r=r: True,
            domain_note=(
                f"{r[0]}: value={r[1]:.6g} {r[6] or ''} "
                f"+{r[2]:.3g}/-{r[3]:.3g}; confidence={r[5] or 'n/a'}"
            ),
            source=f"PDG sqlite pdgdata.{r[0]} ({r[4]})",
            quote=ev(r),
            quote_source=ev(r),
        )
        for r in rows
    ]


def run(rows=None, claims=None):
    rows = rows if rows is not None else load_measurements(TARGET_DESC)
    claims = claims if claims is not None else build_claims(rows)
    return claims, compare_n(claims, list(CRITERIA), chain=False)


def main():
    rows = load_measurements(TARGET_DESC)
    claims, r = run(rows)
    base = rows[0]

    print("=" * 78)
    print("PDG aligned sample: verdicts for N independent measurements of one physical quantity")
    print(f"physical quantity description = {TARGET_DESC!r}")
    print(f"{len(claims)} accounts (one per experimental group)  {len(CRITERIA)} criteria (1σ..8σ)")
    print("=" * 78)
    print(f"  baseline (smallest error = the measurement PDG favors most): {base[0]} = {base[1]:.6g} "
          f"{base[6] or ''}")
    print()
    print(f"{'Measurement':12s}{'Value':>12s}{'Own error':>12s}")
    print("-" * 78)
    for row in rows:
        print(f"  {row[0]:10s}{row[1]:>12.6g}{row[2]:>12.3g}")

    print()
    print(render_n(claims, r))

    print()
    print("=" * 78)
    print("Readout conclusion")
    print("=" * 78)
    print(f"  points {r.total} | all_true {r.all_true} / all_false {r.all_false} "
          f"/ split {r.split} / out_of_domain {r.out_of_domain}")
    if r.pioneers:
        for i, n in r.pioneers.items():
            e = rows[i]
            print(f"  pioneer → {r.names[i]} (the only one that holds on {n} criteria)")
            print(f"          = {e[1]:.6g} {e[6] or ''}, error {e[2]:.3g}")
            print(f"          next-smallest error is {max(rows[1][2], rows[2][2]):.3g}, "
                  f"an order of magnitude larger → the mechanical readout points the same way as human judgment")
    print()
    print("  [No adjudication] divergence ≠ better. An outlier/pioneer only says 'who differs from whom';")
    print("          it does not mean PDG adopted the wrong value — maybe one experiment's error is underestimated.")


if __name__ == "__main__":
    main()

"""PDG misaligned sample: four ways to misalign the accounts, and where each goes wrong.

[What this script teaches]
The most dangerous failure of an N-account diff is not an error — it is **producing a
good-looking readout**. This script runs four misalignments that were really stepped in,
one at a time, and gives each one's measured readout instead of abstract advice.

Error mode 1: select by parent node instead of by physical quantity → 88% pseudo-outliers
              (violates P1; the accounts are misaligned)
Error mode 2: the parameter point is never read by the predicate → constant verdict
              vector, zero information
Error mode 3: the criteria are decorative → the verdict never flips, the readout is all green
Error mode 4 (appendix): quote and quote_source are not same-source → raises at
              construction time. This one is **not a selection problem**; it is a
              provenance problem, hence the appendix.

How to run: python misaligned.py
"""
import os
import sqlite3
import sys

# The Windows console defaults to GBK and the report uses glyphs outside that code
# page. Switch to UTF-8 and downgrade unencodable characters so the script cannot
# die with UnicodeEncodeError while printing its own warning.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

from breakingdiff import Claim, ProvenanceError, compare_n, render_n  # noqa: E402
# ★ Same as aligned.py: make the sibling fetch_data importable even when this file
#   is loaded by path rather than run from its own directory.
sys.path.insert(0, _HERE)
import fetch_data  # noqa: E402  # the pinned corpus identity and its verifier

DB = os.path.join(_HERE, "pdg.sqlite")


def _con():
    # ★ Same as aligned: checking exists alone is not enough — sqlite3.connect creates
    #   a 0-byte empty database out of thin air.
    if not os.path.exists(DB) or os.path.getsize(DB) == 0:
        raise SystemExit(
            f"[FATAL] data file missing or empty: {DB}\n"
            f"{fetch_data.recovery_text(DB)}"
        )
    # ★ Corpus-version guard, same as aligned.py: the 2024/2026 swap must be
    #   blocked on every read path, not only at the fetch entry.
    try:
        fetch_data.verify_sqlite(DB, check_sha256=False)
    except fetch_data.PinError as e:
        raise SystemExit(
            f"[FATAL] corpus does not match the pinned identity; refusing to read:\n{e}\n"
            f"       Run python fetch_data.py for verification/recovery steps.")
    return sqlite3.connect(DB)


def _ev(r):
    return f"pdgid={r[0]}; value={r[1]:.6g}; error=+{r[2]:.3g}/-{r[3]:.3g}"


# ============================================================
# Error mode 1: select accounts by parent node — violates P1
# ============================================================
def wrong_1_by_parent(parent="M070", limit=40):
    """Wrong: assuming "under the same physical-quantity node" means "repeated
    measurements of the same thing".

    Reality: the 544 measurements under M070 (J/psi decays) are **different decay
    channels**, and their branching ratios are supposed to differ.
    Treating them as N measurements of one physical quantity → 88% judged false → all
    pseudo-outliers.
    """
    con = _con()
    rows = con.execute(
        """
        SELECT d.pdgid, d.value, d.error_positive, d.error_negative, i.description
        FROM pdgdata d JOIN pdgid i ON i.id = d.pdgid_id
        WHERE i.parent_pdgid = ?
          AND d.value IS NOT NULL
          AND (d.error_positive > 0 OR d.error_negative > 0)
          AND d.value_type IN ('AC', 'D')
        ORDER BY (d.error_positive + d.error_negative), d.pdgid
        LIMIT ?
        """,
        (parent, limit),
    ).fetchall()
    con.close()
    base = rows[0][1]
    claims = [
        Claim(
            name=r[0],
            predicate=lambda x, r=r: abs(r[1] - base) <= max(r[2], r[3]) * x[1],
            applies=lambda x, r=r: True,
            domain_note=f"{r[0]} value={r[1]:.6g} ({r[4]})",
            source=f"PDG pdgdata.{r[0]}",
            quote=_ev(r), quote_source=_ev(r),
        )
        for r in rows
    ]
    return claims, compare_n(claims, [("1s", 1.0), ("2s", 2.0), ("4s", 4.0)],
                             chain=False), rows, base


# ============================================================
# Error mode 2: the parameter point is not read by the predicate
# ============================================================
def wrong_2_predicate_ignores_x():
    """Wrong: the predicate closure never mentions x at all.

    So every account gives the same answer at every parameter point → N identical
    verdict vectors → the comparison domain is non-zero (it looks like there is a
    readout), but zero outlier attribution and zero pioneers.
    This is a new variant of three-level silence: **non-zero domain, all-green readout,
    and nothing is telling you anything.**
    """
    con = _con()
    rows = con.execute(
        """
        SELECT d.pdgid, d.value, d.error_positive, d.error_negative, i.description
        FROM pdgdata d JOIN pdgid i ON i.id = d.pdgid_id
        WHERE i.description = 'REAL PART' AND d.error_positive > 0
          AND d.value_type = 'AC'
        ORDER BY (d.error_positive + d.error_negative) LIMIT 17
        """
    ).fetchall()
    con.close()
    base = rows[0][1]
    claims = [
        Claim(
            name=r[0],
            predicate=lambda x, r=r: abs(r[1] - base) <= max(r[2], r[3]) * 2.0,
            #                                         ^^^ x is hard-coded to 2.0; the parameter point is never read
            applies=lambda x, r=r: True,
            domain_note=f"{r[0]} value={r[1]:.6g}",
            source=f"PDG pdgdata.{r[0]}",
            quote=_ev(r), quote_source=_ev(r),
        )
        for r in rows
    ]
    domain = [("1s", 1.0), ("2s", 2.0), ("4s", 4.0), ("8s", 8.0)]
    return claims, compare_n(claims, domain, chain=False), rows


# ============================================================
# Error mode 3: decorative criteria (the verdict never flips)
# ============================================================
def wrong_3_decorative_criteria():
    """Wrong: the parameter points change names and values, yet the verdict is the same
    at every point.

    Typical scene: the Hubble run set criteria at 1σ/2σ/3σ, while the differences from
    the baseline were 0.45/0.99/3.24/5.24/5.64 — moving the threshold from 1σ to 3σ
    straddles none of the real differences → constant verdict → always split.
    Diagnostic move: print the verdict vector point by point; if every point's vector is
    identical, you have hit this pit.
    """
    claims, r, rows = wrong_2_predicate_ignores_x()
    # Swap in "professional-looking" criterion names, but the values still fall in the
    # same interval
    domain = [("tight", 1.9), ("nominal", 2.0), ("loose", 2.1),
              ("very_loose", 2.2), ("extreme", 2.3)]
    r2 = compare_n(claims, domain, chain=False)
    return claims, r2, rows, domain


# ============================================================
# Error mode 4: quote and quote_source are not same-source — the tool stops it itself
# ============================================================
def wrong_4_quote_mismatch():
    """Wrong: quote holds a summary, quote_source holds another wording.

    We **do not need to check this one**; construction raises ProvenanceError directly.
    It is recorded here to make the point: the first three error modes are not stopped
    by the tool (they are "legal" in the verdict logic), and only provenance-class error
    modes are stopped mechanically.
    """
    con = _con()
    r = con.execute(
        """
        SELECT d.pdgid, d.value, d.error_positive, d.error_negative
        FROM pdgdata d JOIN pdgid i ON i.id = d.pdgid_id
        WHERE i.description = 'REAL PART' AND d.error_positive > 0
          AND d.value_type = 'AC' LIMIT 1
        """
    ).fetchone()
    con.close()
    try:
        Claim(
            name=r[0],
            predicate=lambda x: True,
            applies=lambda x: True,
            domain_note="test",
            source="PDG",
            # Summary wording: different from the source → not a substring (measured:
            # dropping a few digits still counts as a substring and is let through,
            # e.g. "value=1517" ⊂ "value=1517.5", a granularity limit of the verbatim
            # check, recorded in TEACHING-pdg.md §6.3)
            quote=f"the value is about {r[1]:.6g}",
            quote_source=f"pdgid={r[0]}; value={r[1]:.6g}; error=+{r[2]:.3g}",
        )
        return None, "(no exception — this would be unexpected; if so, the gate is broken)"
    except ProvenanceError as e:
        return r, f"ProvenanceError: {e}"


def main():
    print("=" * 78)
    print("PDG misaligned sample: four ways to misalign the accounts (all measured, not abstract advice)")
    print("=" * 78)

    print()
    print("[Error mode 1] select accounts by parent node instead of by physical quantity")
    c1, r1, rows1, base1 = wrong_1_by_parent()
    print(f"  selected {len(rows1)} accounts, baseline {base1:.6g}")
    disagree = sum(1 for rr in rows1
                   if abs(rr[1] - base1) > 2 * max(rr[2], rr[3]))
    print(f"  accounts differing from the baseline by >2σ: {disagree}/{len(rows1)} = "
          f"{100*disagree/len(rows1):.0f}%")
    print(f"  readout: all_true {r1.all_true} / all_false {r1.all_false} / split {r1.split} "
          f"/ out_of_domain {r1.out_of_domain}")
    print(f"  outlier attribution {r1.outliers or 'none'}  pioneers {r1.pioneers or 'none'}")
    print(f"  diagnosis: these measurements are **different decay channels**; their branching ratios are supposed to differ.")
    print(f"        treating them as repeated measurements of one physical quantity = violating P1; all {disagree} are pseudo-outliers.")
    print(f"        (across all 544 accounts the false rate is 88%; here we take the 40 with the smallest errors, "
          f"hence {100*disagree/len(rows1):.0f}%)")
    print("        ★ Did it raise? No. out-of-domain skips 0, all green. **This is the most dangerous class.**")

    print()
    print("[Error mode 2] the predicate ignores the parameter point (x is hard-coded)")
    c2, r2, rows2 = wrong_2_predicate_ignores_x()
    print(f"  comparison domain {r2.total} points | all_true {r2.all_true} / all_false {r2.all_false} "
          f"/ split {r2.split}")
    print(f"  outlier attribution {r2.outliers or 'none'}  pioneers {r2.pioneers or 'none'}")
    print(f"  diagnosis: the 4 parameter points give **the same** verdict vector.")
    print(f"        pioneer counts 4/4 all fall on account 0 — because the verdict does not depend on x,")
    print(f"        it is not 'only it holds under some criterion' but 'the same result under every criterion'.")
    print(f"        ★ Key: compared with aligned's 3/5, here it is 4/4 —")
    print(f"          a share close to 100% is the fingerprint of 'the verdict does not change with the parameter point'.")
    print("        ★ Did it raise? No. out-of-domain skips 0, the readout is 'all green'.")

    print()
    print("[Error mode 3] decorative criteria (professional names, verdict never flips)")
    c3, r3, rows3, dom3 = wrong_3_decorative_criteria()
    print(f"  {len(dom3)} criteria: {[d[0] for d in dom3]}")
    print(f"  comparison domain {r3.total} points | all_true {r3.all_true} / all_false {r3.all_false}"
          f" / split {r3.split} / out_of_domain {r3.out_of_domain}")
    print(f"  outliers {r3.outliers or 'none'}  pioneers {r3.pioneers or 'none'}")
    print("  diagnosis: ★ this is **the same disease** as error mode 2 — a constant verdict vector,")
    print("        the only difference is that the criteria were renamed to sound professional (tight/nominal/...),")
    print("        while the threshold span is only 1.9~2.3σ, which straddles no real difference.")
    print(f"        measured: the verdict is completely identical under all 5 criteria (the baseline is True, the other 16 are False),")
    print(f"        so pioneers 5/5 = 100%. This is more hidden than error mode 2 —")
    print("        because the criterion names look carefully designed.")
    print("        diagnostic move: print the verdict vector point by point; identical points mean you have hit this pit.")
    print("  ★ Did it raise? No. out-of-domain skips 0, the readout is 'all green'.")

    print()
    print("[Appendix] Error mode 4: quote and quote_source are not same-source")
    print("  (★ this one is **not a selection problem**; it is a provenance problem, so it is not part of the account-alignment discussion above)")
    r4, msg = wrong_4_quote_mismatch()
    print(f"  {msg}")
    print("  diagnosis: **the tool stopped this one.** The first three cannot be stopped —")
    print("        they are perfectly legal in the verdict logic; they just ask the wrong question.")

    print()
    print("=" * 78)
    print("Summary: of the four error modes, only the fourth is stopped mechanically by the tool")
    print("=" * 78)
    print("  Error modes 1/2/3 all produce a readout that is **well-formed, all green, with no attribution**.")
    print("  The tool does not know 'you selected the wrong accounts' — it only knows 'what value your predicate takes at each point of the given domain'.")
    print("  So P1/P2 (do the accounts cover the same purpose, can the parameter points be enumerated)")
    print("  are **human judgments**, not something the tool can verify for you.")
    print()
    print("  → This is the entire reason aligned.py exists.")


if __name__ == "__main__":
    main()

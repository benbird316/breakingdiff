"""llama.cpp case — the four failure modes of the probe layer, each with its measured readout.

[What this script teaches]
The first case (PDG) taught "how to take P/Q": it read data straight from a database and had **no probe layer**.
Industrial settings are different: nobody can treat a 700 MB binary as evidence directly;
there is always a layer of "extraction + processing" in between. That layer is unique to industrial settings,
and it is **the layer most likely to break without looking broken**.

This script runs the four failure modes that layer has hit, one by one, each with its measured readout.

Error mode 1: checking the wrong file (stub vs real implementation) → falsely all-False
Error mode 2: a silent probe (recording "cannot measure" as "absent") → symptoms indistinguishable from a real gap
Error mode 3: mixed dimensions (artifact fact + official promise stuffed into one account) → verdict degenerates into a constant, readout all zero (total > 0)
Error mode 4 (appendix): a forged anchor (ledger sha disagrees with the artifact's self-report) → the provenance gate stops it on the spot

How to run: python misaligned.py
"""
import os
import sys

# The Windows console defaults to GBK and the report uses glyphs outside that code
# page. Switch to UTF-8 and downgrade unencodable characters so the script cannot
# die with UnicodeEncodeError while printing its own warning.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
# ★ Search upward for breakingdiff.py instead of hard-coding "how many levels up".
#   With a hard-coded depth, moving this directory (changing the nesting depth)
#   silently turns into ModuleNotFoundError — and the last thing a case study can afford is
#   "it will not run from another location" with no way to find out why.
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

import aligned  # noqa: E402
from breakingdiff import Claim, ProvenanceError, compare_n  # noqa: E402


# ============================================================
# Error mode 1: checking the wrong file — a stub is not the implementation
# ============================================================
def wrong_1_wrong_file():
    """Mistake: checking `llama-server.exe`.

    It is only 9216 bytes — a stub whose only job is to load the real dll.
    The real code is in `llama-server-impl.dll` (8851968 bytes, a factor of 960).

    Consequence: the official notes say b10595 "add LLAMA_SERVER_SLOTS_N_DIFF",
    but checking the stub gives **0 hits on all three builds** →
    the readout says "none of the three builds has this feature",
    and **the conclusion looks entirely reasonable**: the vendor says it was added, the measurement finds nothing, the vendor is lying.
    The truth is that the probe checked the wrong file.
    """
    rows = []
    for build in aligned.BUILDS:
        stub = os.path.join(aligned.build_dir(build), "llama-server.exe")
        impl = os.path.join(aligned.build_dir(build),
                            "llama-server-impl.dll")
        rows.append((build,
                     os.path.getsize(stub),
                     int(aligned._file_has(stub, "LLAMA_SERVER_SLOTS_N_DIFF")),
                     os.path.getsize(impl),
                     int(aligned._file_has(impl, "LLAMA_SERVER_SLOTS_N_DIFF"))))
    return rows


# ============================================================
# Error mode 2: a silent probe — "cannot measure" recorded as "absent"
# ============================================================
def wrong_2_silent_probe():
    """Mistake: return False silently when the probe fails, with no explanation.

    Compare the probes in aligned.py: `probe_template_analysis` returns
    `(False, "missing")` when the file does not exist — **with an explanation**;
    `probe_slots_n_diff` returns `(False, "impl dll not found: <path>")`
    when impl.dll is absent.

    The silent version collapses both into the same False. So in the readout:
      "this build does not have this feature"   ← it really is absent
      "my probe did not find the file"         ← my tool is broken
    **Completely indistinguishable**. And the differential engine only sees what the predicate returns;
    it cannot tell which cause sits behind that False.

    ★ This is the most essential difference between this case and the first one:
      the PDG case read a database, and a failed read raises a SQL error —
      failure is **loud**. Here failure is **quiet**,
      so quiet that it looks exactly like "the fact is false".
    """
    results = []
    for build in aligned.BUILDS:
        # silent version: failure and "really absent" both return False, saying nothing
        results.append(("real probe", build,
                        aligned.probe_slots_n_diff(build)[0]))
    return results


def wrong_2b_silent_vs_real():
    """Build the "silent version", run it to a readout, and compare with the real probe."""
    def silent_probe(build):
        p = os.path.join(aligned.build_dir(build),
                         "llama-server-impl.dll")
        if not os.path.exists(p):
            return False, ""            # ← silent: no explanation
        return bool(aligned._file_has(p, "LLAMA_SERVER_SLOTS_N_DIFF")), ""

    claims = []
    for build in aligned.BUILDS:
        ok, _ = silent_probe(build)
        claims.append(
            Claim(name=build, predicate=lambda x, v=ok: v,
                  applies=lambda x: True, domain_note="silent probe",
                  source="llama", quote="x", quote_source="x")
        )
    r = compare_n(claims, list(aligned.CRITERIA), chain=False)
    return claims, r


# ============================================================
# Error mode 3: mixed dimensions — artifact fact + official promise in one account
# ============================================================
def wrong_3_mixed_quantity():
    """Mistake: treat "artifact fact" and "official promise" as the same account.

    That is how the first version of aligned.py was written: 9 accounts (3 probes × 3 builds),
    with a predicate like `ok and x[0] >= claimed_at` —
    but `ok` is the probe result, `claimed_at` is a string, the comparison is always true,
    and the verdict degenerates into a constant.

    ★ The measured symptom **differs from the first case**, and deserves its own record:
      PDG's "predicate does not read x" reads out "all_true 3/3 = 100%" —
      all accounts agree, which at least looks like a checkup result.
      Here it reads out "all_true 0 / all_false 0 / split 0" — **not a single point of agreement**.
      Different builds naturally give different probe results, so once dimensions are mixed
      every account becomes an independent constant: the verdict vector is constant across builds and split across accounts.
      **All zero is more dangerous than all true**: all true at least looks self-consistent; all zero looks like "nothing was measured".
    """
    rows = []
    for build in aligned.BUILDS:
        vec = []
        for probe in (aligned.probe_slots_n_diff,
                      aligned.probe_mellum,
                      aligned.probe_template_analysis):
            vec.append(bool(probe(build)[0]))
        rows.append((build, vec))

    claims = []
    for build in aligned.BUILDS:
        ok = bool(aligned.probe_slots_n_diff(build)[0])
        claims.append(
            Claim(name=f"{build}/mixed",
                  # ★ The counter-example: that `and True` in the predicate is the swallowed promise condition.
                  #   The promise says "must hold from b10595 on", but the actual code folds it into a tautology.
                  predicate=lambda x, v=ok: v and True,
                  applies=lambda x: True, domain_note="mixed dimensions",
                  source="llama", quote="x", quote_source="x")
        )
    r = compare_n(claims, list(aligned.CRITERIA), chain=False)
    vectors = {c.name: [c.predicate(p) for p in aligned.CRITERIA]
               for c in claims}
    return rows, claims, r, vectors


# ============================================================
# Error mode 4 (appendix): a forged anchor — the ledger disagrees with the artifact's self-report
# ============================================================
def wrong_4_forged_anchor():
    """Mistake: put a sha in the ledger that disagrees with the artifact's self-reported commit.

    This one **does not belong to the probe layer**; it is the ledger layer, hence the appendix.
    But it is the root of trust for the whole case — if the ledger is wrong, everything after it is wrong,
    and wrong with no sign of it.

    This case really hit it: C1 originally quoted the b10595 statement on b10472,
    and b10595's source text is not in the b10472 record,
    so `ProvenanceError` was raised on the spot. **The gate works.**
    """
    led = aligned.load_ledger()
    b10472 = next(r for r in led["releases"] if r["tag"] == "b10472")
    b10595 = next(r for r in led["releases"] if r["tag"] == "b10595")
    try:
        Claim(
            name="forged anchor",
            predicate=lambda x: True, applies=lambda x: True,
            domain_note="test",
            source="github release b10472 notes",
            #★ passing b10595's text off as b10472's
            quote=b10595["body_details_verbatim"],
            quote_source=b10472["body_details_verbatim"],
        )
        return None, "(no error raised — which means the gate failed; that is a serious problem)"
    except ProvenanceError as e:
        return (b10472, b10595), f"ProvenanceError: {e}"


def _arg_root(argv):
    """Take --llama-root from the command line (tolerates argv=None)."""
    if not argv:
        return None
    if "--llama-root" in argv:
        i = argv.index("--llama-root")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv=None):
    # ★ The root must be written back to aligned's global — build_dir() reads LLAMA_ROOT there;
    #   setting a same-named global in this module does nothing (NameError).
    aligned.LLAMA_ROOT = aligned.resolve_root(_arg_root(argv))
    print("=" * 78)
    print("llama.cpp case: the four failure modes of the probe layer (all measured readouts, not abstract preaching)")
    print("=" * 78)

    print()
    print("[Error mode 1] checking the wrong file: a stub is not the implementation")
    rows = wrong_1_wrong_file()
    print(f"  {'build':10s}{'stub bytes':>12s}{'stub hit':>10s}"
          f"{'impl bytes':>12s}{'impl hit':>10s}")
    print("  " + "-" * 64)
    for b, ss, sh, is_, ih in rows:
        print(f"  {b:10s}{ss:>12d}{sh:>10d}{is_:>12d}{ih:>10d}")
    print("  (hit column 0/1 = whether that file contains the SLOTS_N_DIFF symbol)")
    print()
    print("  Readout: checking the stub → 0 hits on all three builds")
    print("        → the conclusion would be \"the vendor says SLOTS_N_DIFF was added, the measurement finds it in none of the three versions, the vendor is lying\"")
    print("        → the truth is that the probe checked the wrong file.")
    print("  ★ Did anything raise an error? No. The readout is entirely normal and the conclusion looks extremely reasonable.")
    print("★ This is the most dangerous class in this case: checking the wrong file **does not** make the readout look strange,")
    print("    it only leads you to a reversed wrong conclusion.")

    print()
    print("[Error mode 2] a silent probe: recording \"cannot measure\" as \"absent\"")
    _c2, r2 = wrong_2b_silent_vs_real()
    print("  Readout of the silent probe on each build:")
    for c in _c2:
        print(f"    {c.name:10s} {c.predicate(aligned.CRITERIA[0])}")
    print(f"  comparison domain {r2.total} points | all_true {r2.all_true} / all_false {r2.all_false}"
          f" / split {r2.split} / out_of_domain {r2.out_of_domain}")
    print()
    print("  ★ Note that the readout **itself is correct**: b10472 really does not have SLOTS_N_DIFF.")
    print("    The problem is that the silent probe and the real probe give **exactly the same readout**,")
    print("    which means: once the probe breaks, nothing in the readout tells you so.")
    print()
    print("  ★ The two kinds of False are indistinguishable in the readout:")
    print("      \"this build does not have this feature\"    ← it really is absent (fact)")
    print("      \"my probe did not find the file\"          ← my tool is broken (tool)")
    print("  ★ The essential difference from the first case: PDG read a database, and a failed read raises a SQL error,")
    print("    so failure is **loud**. Here failure is **quiet**,")
    print("    so quiet that it cannot be told apart from \"the fact is false\".")
    print("  → Fix: a probe must return (bool, explanation), and a False must carry a reason.")
    print("    All three probes in aligned.py follow this rule, for example:")
    print("      probe_slots_n_diff: when the impl dll is absent it returns")
    print("        (False, 'impl dll not found: <path>')")
    print("      probe_template_analysis: returns (False, 'missing')")

    print()
    print("[Error mode 3] mixed dimensions: artifact fact + official promise in one account")
    rows3, _c3, r3, vec3 = wrong_3_mixed_quantity()
    print("  Measurement of the three probe classes on the three builds:")
    for b, vec in rows3:
        flags = "  ".join("yes" if v else "—" for v in vec)
        print(f"    {b:10s} {flags}   (SLOTS / MELLUM / tpl-analysis)")
    print("  Verdict vectors after mixing dimensions:")
    for name, vec in vec3.items():
        print(f"    {name:16s} {vec}")
    print(f"  Readout: all_true {r3.all_true} / all_false {r3.all_false}"
          f" / split {r3.split} / out_of_domain {r3.out_of_domain}")
    print()
    print("  ★ Every account's verdict vector is a **constant** — it does not vary with the build.")
    print("    As a result the three accounts split into two camps, **with no point of agreement at all**,")
    print("    and the readout is all zero (all_true 0 / all_false 0 / split 0).")
    print()
    print("  ★ This symptom differs from the first case and deserves its own record:")
    print("    PDG's \"predicate does not read x\" reads out \"all_true 3/3 = 100%\" —")
    print("    all accounts agree, which at least looks like a checkup result.")
    print("    Here it reads out all zero — **all zero is more dangerous than all true**,")
    print("    because all true looks self-consistent while all zero looks like \"nothing was measured\".")
    print("★ Did anything raise an error? No. The tool cannot tell that \"not a single point of agreement\"")
    print("    means the construction is broken; it only reports honestly that \"there is no region of agreement\".")
    print("  → For the fix see aligned.py: one account = one official statement,")
    print("    with artifact facts only as evidence inside the predicate, never mixed into the promise.")

    print()
    print("[Appendix] Error mode 4: a forged anchor (ledger layer, not probe layer)")
    pair, msg = wrong_4_forged_anchor()
    print(f"  {msg}")
    print("  Diagnosis: **the tool stops this one.**")
    print("        The first three are not stopped — they are entirely legal in the verdict logic;")
    print("        they merely ask the wrong question or check the wrong thing.")

    print()
    print("=" * 78)
    print("Summary: of the four failure modes, only the fourth is stopped mechanically by the tool")
    print("=" * 78)
    print("  Error mode 1: checking the wrong file → normal readout, reversed conclusion (most dangerous)")
    print("  Error mode 2: a silent probe → \"cannot measure\" and \"absent\" are indistinguishable")
    print("  Error mode 3: mixed dimensions → verdict degenerates, readout all zero")
    print("  All three **raise no error**. Their only difference is the symptom:")
    print("    error modes 1 and 2 break the probe layer of the P account, where the differential engine cannot see it;")
    print("    error mode 3 breaks the construction layer of the Q account: the predicate becomes a constant.")
    print()
    print("  → This is the entire reason aligned.py exists.")
    print()
    print("  ★ Fingerprints of the four degenerate readouts (quick reference, all measured):")
    print("    ┌──────────────────────────────┬────────────┬────────────┬───────┬────────────────────────────┐")
    print("    │ Symptom                      │ all_true   │ all_false  │ total │ Cause                      │")
    print("    ├──────────────────────────────┼────────────┼────────────┼───────┼────────────────────────────┤")
    print("    │ all_true = total             │     3      │     0      │   3   │ predicate constantly true  │")
    print("    │                              │            │            │       │ (does not read x)          │")
    print("    │ all zero but total = 0       │     0      │     0      │   0   │ applies constantly false   │")
    print("    │ all zero but total > 0       │     0      │     0      │   3   │ account split: dimensions  │")
    print("    │                              │            │            │       │ mixed                      │")
    print("    │ readout normal,              │     —      │     —      │   —   │ probe checked the wrong    │")
    print("    │ conclusion reversed          │            │            │       │ file                       │")
    print("    └──────────────────────────────┴────────────┴────────────┴───────┴────────────────────────────┘")
    print("    ★ Key: the last two both show \"all zero\"; only total separates them.")
    print("      total = 0 means \"not a single point was compared\";")
    print("      total > 0 with all zero means \"comparison happened, but there is no region of agreement\".")
    print("      Neither is a \"pass\".")
    print()
    print("  ★ Contrast with the first case:")
    print("    PDG teaches \"how to take P/Q\" (data-extraction layer)")
    print("    This case teaches \"how evidence is extracted\" (probe layer + ledger layer)")
    print("    In industrial settings the latter breaks more easily, and breaks more quietly.")


if __name__ == "__main__":
    main()

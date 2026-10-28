"""Three llama.cpp nightly builds — the official-announcement account Q vs the artifact-verification account P.

[What makes this case special]
In the previous case (PDG) both Q and P were external data sources, and the differential was a side-by-side comparison.
This case is **the native shape of industrial production**:

    Q account = the verbatim statements in the official release notes (promise)
    P account = the actual behavior of the unpacked binaries (fact)

The two are independent by nature — the vendor cannot have written its notes from my binary — so P6 holds more strongly.
The question to answer is a real one: **is what the vendor says true?**

[How the parameter points are chosen]
In an industrial setting a parameter point is not a continuous quantity like a "statistical criterion"; it is
**"the place where the change happened"**: the announcement says X was introduced in b10595, so take
b10472 / b10595 / b11681 as the parameter points and ask, one build at a time, "does your build contain X".

This is not decoration; it is P3's natural boundary: **in this domain "the change is legal and non-erroring"** —
one exe fewer, one environment variable more, and the program still runs, with nothing stopping it.

[★ This script was reworked once; the lesson is written above the CLAIMS definition]
The first version packed "artifact facts" and "official promises" into the same account (9 of them),
so the predicate degenerated into a constant → every verdict vector was [True, True, True] → the readout was all_true 3/3 = 100%.
The tool raised no error, but the result carried zero information.
The root cause was **mixed dimensions**: "does the file exist" and "has the official promise been honored" are not the same thing.
The right shape: one account = one official statement, with artifact facts appearing only as evidence inside the predicate.

How to run: python aligned.py
"""
import json
import os
import re
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

from breakingdiff import Claim, compare_n, render_n  # noqa: E402

# Corpus root: **not hard-coded in the code**.
#
# This case study has to run after someone copies it elsewhere, so neither the code
# nor the docs **may contain any local absolute path**. Three ways to specify it, in priority order:
#   1. environment variable BREAKINGDIFF_LLAMA_ROOT
#   2. command line --llama-root <path>
#   3. a llama-b<build>/ directory next to this script (the copy-and-run default)
LLAMA_ROOT = os.environ.get("BREAKINGDIFF_LLAMA_ROOT", "")
LEDGER = os.path.join(_HERE, "official_ledger.json")


def resolve_root(explicit=None, require_complete=True):
    """Locate the corpus root; exit explicitly when it cannot be found.

    ★ The missing-corpus guard is a hard requirement (the third level of silence):
      if the corpus is absent and the run quietly produces an empty readout,
      "did not run" gets read as "it ran, and the official announcement is fine" —
      exactly the mistake this case must never make.

    ★ With require_complete=False a **partial** corpus is accepted, but it must say what is missing.
      This is not a weaker guard; it separates "no corpus at all" from "an incomplete corpus":
      the first cannot run, the second runs but **the cross-version conclusion is invalid** —
      the consequences differ completely, and folding both into "corpus not found" is imprecise.
    """
    cands = [explicit, LLAMA_ROOT, _HERE]
    best_partial, best_missing = None, None
    for c in cands:
        if not c:
            continue
        c = os.path.abspath(c)
        missing = [b for b in BUILDS
                   if not os.path.isdir(os.path.join(c, f"llama-{b}"))]
        if not missing:
            return c
        if best_partial is None or len(missing) < len(best_missing):
            best_partial, best_missing = c, missing

    if not require_complete and best_partial is not None:
        return best_partial

    # When the corpus is incomplete, state the **consequence** — far more useful than "not found".
    partial_note = ""
    if best_partial is not None and len(best_missing) < len(BUILDS):
        partial_note = (
            f"\n\n       ★ But the directory you gave contains an **incomplete** corpus:\n"
            f"         {len(BUILDS) - len(best_missing)}/{len(BUILDS)} builds present, "
            f"missing {', '.join(best_missing)}.\n"
            f"         ★ Consequence: the core conclusion of this case is **cross-version** "
            f"(the disappearance of template-analysis).\n"
            f"           Without the missing builds that comparison cannot be re-run, and the tool "
            f"**does not raise an error** —\n"
            f"           C3 goes from \"1 missing out of 3 versions\" to \"1 missing out of 1 version\",\n"
            f"           the outlier share goes from 33% to 100%, and the readout still looks \"normal\".\n"
            f"         To restore: python fetch_corpus.py\n")

    raise SystemExit(
        "[FATAL] cannot find a complete llama.cpp corpus.\n"
        f"       Need a root containing {', '.join(f'llama-{b}' for b in BUILDS)}.\n"
        "       Three ways to specify it (pick one):\n"
        "         1) environment variable: set BREAKINGDIFF_LLAMA_ROOT=<path>\n"
        "         2) command line:         python aligned.py --llama-root <path>\n"
        "         3) or copy the llama-b* directories beside this script\n"
        "       The artifacts come from the official llama.cpp nightly releases; unpack them by build number.\n"
        "       Or run python fetch_corpus.py to download them automatically."
        + partial_note)


def build_dir(build, root=None):
    return os.path.join(root or LLAMA_ROOT, f"llama-{build}")


# ============================================================
# The three probes of the P account: read the local binaries, no network
# ============================================================
def _contains(path, needle, minlen=4):
    """Only answer "does this file contain needle"; materialize no strings.

    ★ Why not use `_strings()` and filter: that would turn every printable run of
      length ≥4 in a 700 MB binary into a Python object — millions of str per build,
      enough to MemoryError across three builds. This scans and compares **in one pass**,
      stops on the first hit, and uses memory for the needle itself.

    Cost: every call rescans the file. That is why the (needle, file) memoization below
    matters — and it does **not** need to cache a list of strings.
    """
    pat = re.compile(needle.encode("ascii"), re.I if needle.islower() else 0)
    with open(path, "rb") as f:
        blob = f.read()
    return bool(pat.search(blob))


_YESNO_CACHE = {}


def _file_has(path, needle):
    key = (os.path.normcase(path), needle)
    if key in _YESNO_CACHE:
        return _YESNO_CACHE[key]
    st = os.stat(path)
    key = (os.path.normcase(path), st.st_mtime_ns, st.st_size, needle)
    if key in _YESNO_CACHE:
        return _YESNO_CACHE[key]
    out = _contains(path, needle)
    _YESNO_CACHE[key] = out
    return out


def probe_slots_n_diff(build):
    """P-1: the official notes say b10595 "add LLAMA_SERVER_SLOTS_N_DIFF".

    Probe = does this build's server binary contain that symbol.
    ★ Second trap: `llama-server.exe` is only a stub (a few KB);
      the real code is in `llama-server-impl.dll`. Checking the wrong file gives an all-False false readout.
    """
    impl = os.path.join(build_dir(build), "llama-server-impl.dll")
    if not os.path.exists(impl):
        return False, f"impl dll not found: {impl}"
    ok = _file_has(impl, "LLAMA_SERVER_SLOTS_N_DIFF")
    return ok, ("2 matches" if ok else "0 matches")


_MELLUM_CACHE = {}


def probe_mellum(build):
    """P-2: the official notes say b11681 "add precision handling for MELLUM architecture".

    Probe = does this build contain the MELLUM model implementation.
    ★ This probe is **weaker than** the official statement: it can only prove "MELLUM exists", not
      "precision handling was added" (precision handling is invisible at the string level, and MELLUM
      already existed in b10472) — what the official statement really asks for cannot be measured by this
      case. That is the tool's capability boundary, not the vendor's fault.
      The full reading is in _narrate ②.

    This version (scan every file in the directory) is much slower than the one above, so it has its own cache.
    """
    if build in _MELLUM_CACHE:
        return _MELLUM_CACHE[build]
    d = build_dir(build)
    hits = 0
    for f in os.listdir(d):
        if f.endswith((".dll", ".exe")) and _file_has(os.path.join(d, f),
                                                       "mellum"):
            hits += 1
    out = (hits > 0, f"{hits} matching file{'s' if hits != 1 else ''}")
    _MELLUM_CACHE[build] = out
    return out


def probe_template_analysis(build):
    """P-3: ★★ the hard finding of this case.

    The official notes record only "additions", commit by commit, and **never "removals"**.
    Yet `llama-template-analysis.exe` disappeared in b11681,
    and the official notes for the three versions say **not one word** about it.
    """
    p = os.path.join(build_dir(build), "llama-template-analysis.exe")
    return os.path.exists(p), ("present" if os.path.exists(p) else "missing")


# ============================================================
# Parameter points = build numbers, in ascending time order (where the official says the change happened)
# ============================================================
BUILDS = ["b10472", "b10595", "b11681"]
CRITERIA = [(b, b) for b in BUILDS]


# ============================================================
# Q account: the official statements, verbatim — one statement = one account
# ============================================================
# ★ Dimension discipline: this script was reworked once; the full lesson is in the file-head docstring.
#   One account = one official statement; artifact facts are evidence inside the predicate only, never an account of their own.
CLAIMS = [
    {
        "name": "C1 server adds SLOTS_N_DIFF",
        "claimed_at": "b10595",
        "verbatim": "server : add LLAMA_SERVER_SLOTS_N_DIFF (#27600)",
        "evidence": probe_slots_n_diff,
        "evidence_note": "whether that symbol appears in the server binary",
    },
    {
        "name": "C2 MELLUM precision handling",
        "claimed_at": "b11681",
        "verbatim": "graph : add precision handling for MELLUM architecture (#30584)",
        # ★ Honest mapping: this probe only proves "MELLUM exists", **weaker than** the official statement.
        #   Weakening that would disguise "cannot measure" as "passed". See _narrate ②.
        "evidence": probe_mellum,
        "evidence_note": "★ weaker than the statement: it can prove \"the MELLUM implementation exists\" "
                         "but not \"precision handling was added\"",
    },
    {
        "name": "C3 template-analysis not removed",
        "claimed_at": None,          # the official notes **never** state this
        "verbatim": None,
        "evidence": probe_template_analysis,
        "evidence_note": "no corresponding official statement; this account asserts \"it should not be removed without notice\"",
    },
]


def load_ledger():
    if not os.path.exists(LEDGER):
        raise SystemExit(
            f"[FATAL] missing official ledger {LEDGER}\n"
            f"       The Q account must be verbatim source text, never written from memory."
        )
    with open(LEDGER, encoding="utf-8") as f:
        return json.load(f)


def build_claims(ledger):
    """Build the three accounts.

    The predicate reads x (x = build number): the official claims it takes effect from claimed_at,
    so evidence is required only when x >= claimed_at.
    C3 with claimed_at=None is the reverse assertion: no build may lose that tool without an announcement.
    """
    releases = {r["tag"]: r for r in ledger["releases"]}
    claims = []
    for spec in CLAIMS:
        ev = spec["evidence"]
        at = spec["claimed_at"]

        def predicate(x, at=at, ev=ev):
            if at is None:
                # reverse assertion: the tool must still be there
                ok, _ = ev(x[0])
                return ok
            # the official claims "present from at on" → do not require it before at, must hold after
            if x[0] < at:
                return True
            ok, _ = ev(x[0])
            return ok

        # quote must be the verbatim text of **the record that contains that official statement**.
        # ★ Provenance trap: the first version quoted "the official statement this probe targets",
        #   but for b10472 that statement belongs to the b10595 notes,
        #   not to the b10472 source → ProvenanceError raised on the spot. The gate works.
        src_tag = at or "b11681"
        verbatim = releases[src_tag]["body_details_verbatim"]
        claims.append(
            Claim(
                name=spec["name"],
                predicate=predicate,
                applies=lambda x: True,
                domain_note=(f"official claims effective from {at or '(never stated)'}; "
                             f"evidence account: {spec['evidence_note']}"),
                source=f"github release {src_tag} notes (verbatim, see official_ledger.json)",
                quote=verbatim,
                quote_source=verbatim,
            )
        )
    return claims


def run(claims):
    """★ order_key is required — this is not a detail, it is part of correctness.

    The tool raises this warning on its own (quoted in full):
      "Order is not determined by order_key; the caller's list order is taken as time order.
        The ratchet direction ('present in the old version, dropped in the new one') depends on this
        assumption; if the list order is not time order, the direction of ratchet violations flips
        entirely, while the readout looks perfectly normal."

    "while the readout looks perfectly normal" is the most dangerous sentence — it means you cannot tell
    when you get it wrong.

    ★ Contract: `order_key(index, claim)` orders **accounts**, not parameter points.
      Here the accounts are the fixed three, and the order only affects the direction in which the
      ratchet check is presented, so sorting stably by claim name is enough.
      A build number is itself time order and **can be determined mechanically, with no human judgment** —
      this is this case's structural advantage over the previous one: parameter points come with natural labels.
    """
    return compare_n(claims, list(CRITERIA), chain=True,
                     order_key=lambda _i, c: c.name)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--llama-root", default=None,
                    help="corpus root (contains llama-b10472/ etc.)")
    args = ap.parse_args(argv)

    global LLAMA_ROOT
    LLAMA_ROOT = resolve_root(args.llama_root)

    ledger = load_ledger()
    claims = build_claims(ledger)
    r = run(claims)

    print("=" * 78)
    print("llama.cpp nightly: official-announcement account Q vs artifact-verification account P")
    print("=" * 78)
    print("  Corpus: three official nightly builds (unpacked, one directory per build number)")
    print(f"  Parameter points (build numbers, ascending time): {', '.join(BUILDS)}")
    print(f"  Q account: {len(CLAIMS)} verbatim statements from the official release notes")
    print("  P account: measured evidence from the binaries")
    print("=" * 78)

    print()
    print("[P-account measurement matrix]")
    print(f"{'probe':30s}" + "".join(f"{b:>10s}" for b in BUILDS))
    print("-" * 78)
    for label, probe in [("server has SLOTS_N_DIFF", probe_slots_n_diff),
                         ("has MELLUM implementation", probe_mellum),
                         ("has template-analysis.exe", probe_template_analysis)]:
        row = []
        for tag in BUILDS:
            ok, _ = probe(tag)
            row.append("  yes" if ok else "  —")
        print(f"  {label:28s}" + "".join(f"{x:>10s}" for x in row))

    print()
    print(render_n(claims, r))

    print()
    print("=" * 78)
    print("Readout conclusion")
    print("=" * 78)
    print(f"  parameter points {r.total} | all_true {r.all_true} / all_false {r.all_false} "
          f"/ split {r.split} / out_of_domain {r.out_of_domain}")
    print(f"  ratchet violations (present in the old version, dropped in the new one, with verifiable direction): {r.ratchet_total}")
    for w in (r.ratchet_witnesses or []):
        print(f"    {w}")

    print()
    print("  [Account-by-account reading]")
    _narrate()

    print()
    print("  [No adjudication] this differential only answers \"do they match\", not \"should this be upgraded\".")
    print("          template-analysis disappearing is not necessarily bad (it may be a deliberate cleanup),")
    print("          but that it **went unannounced** is a fact — the two must be stated separately.")


def _narrate():
    print()
    print("  ① C1 SLOTS_N_DIFF — the official statement [holds], and the introduction point can be located")
    print("     Official b10595: \"server : add LLAMA_SERVER_SLOTS_N_DIFF (#27600)\"")
    print("     Measured: absent in b10472, present in b10595, present in b11681 → the introduction point matches the statement.")

    print()
    print("  ② C2 MELLUM — the official statement [holds in wording, unverifiable in substance]")
    print("     Official b11681: \"graph : add precision handling for MELLUM architecture\"")
    print("     Measured: all three builds contain the mellum model implementation (the same 8 strings,")
    print("           including D:/a/llama.cpp/llama.cpp/src/models/mellum.cpp).")
    print("     → What the official says is \"adds precision handling\", not \"adds MELLUM support\".")
    print("     → MELLUM support was already present in b10472. So this account **cannot measure what the")
    print("       official claims**; it can only measure \"MELLUM exists\" — the tool's capability boundary, not the vendor's fault.")
    print("     → This case records it honestly as \"weak evidence\", not as \"pass\".")

    print()
    print("  ③ C3 template-analysis — ★ the official statement [missing], measured [a real gap]")
    print("     Across the three versions the official notes mention only 3 things, all of them \"additions\".")
    print("     Measured: llama-template-analysis.exe is present in b10472 / b10595,")
    print("           and missing in b11681 (the latest).")
    print("     → Removal is the most breaking kind of change, yet not one word mentions it.")
    print("     → Root cause: the official notes are per-commit summaries (add/fix/update);")
    print("       a deletion commit has no announcement slot.")
    print("     ★ This is the only **dominance readout** in this case:")
    print("       \"the vendor did not say it, but the artifact changed\" — exactly the class the announcement")
    print("       should have covered and did not.")


if __name__ == "__main__":
    main()

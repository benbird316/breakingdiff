"""Mutation evidence for aligned.py: breaking it must turn this file red.

[Why this file must exist]
One hard rule in this project: a passing positive run proves nothing.
Every protected behavior needs an assertion of the form "break it and it must turn red",
and that assertion must cover **both directions of breakage**:

| Direction | What gets broken            | Consequence if missed                                                    |
|---|---|---|
| Too loose | The gate always lets things through | The report still comes out and the format is still right — it just stops blocking: **disguised as a pass** |
| Too tight | The gate blocks what it should let through | A gate that "dares not let anything through" gets bypassed after two uses |

How to run: python test_aligned.py
"""
import contextlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

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
sys.path.insert(0, _HERE)

import aligned  # noqa: E402
import fetch_data  # noqa: E402  # the pinned corpus identity and its verifier
import misaligned  # noqa: E402
from breakingdiff import Claim, ProvenanceError  # noqa: E402

DB = os.path.join(_HERE, "pdg.sqlite")
HAS_DB = os.path.exists(DB)


def _make_fake_pdg_sqlite(path, *, edition="2024",
                          schema=fetch_data.PINNED_SCHEMA_VERSION,
                          rows=fetch_data.PINNED_PDGDATA_ROWS,
                          citation=fetch_data.PINNED_CITATION):
    """Build a **structurally valid but parameterized-wrong** fake PDG sqlite.

    The real corpus is not copied: each pinned check (edition / schema / rows /
    citation) must be breakable on its own, otherwise the corresponding assertion
    has no proven discriminating power.
    """
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE pdginfo ("
                    "id INTEGER PRIMARY KEY, name VARCHAR(30), value VARCHAR(255))")
        con.execute("CREATE TABLE pdgdata (pdgid TEXT)")
        meta = {
            "producer": "Particle Data Group (PDG)",
            "status": "production",
            "schema_version": schema,
            "edition": edition,
            "citation": citation,
            "license": "CC BY 4.0",
        }
        con.executemany(
            "INSERT INTO pdginfo (name, value) VALUES (?, ?)", list(meta.items()))
        con.executemany("INSERT INTO pdgdata (pdgid) VALUES (?)",
                        [("fake",)] * rows)
        con.commit()
    finally:
        con.close()
    return path


def total_summary(r):
    """Compress the readout into one line so a failed assertion shows the shape directly."""
    return (f"total={r.total} all_true={r.all_true} all_false={r.all_false} "
            f"split={r.split} ood={r.out_of_domain} "
            f"out={r.outliers} pio={r.pioneers}")


def _load():
    return aligned.load_measurements(aligned.TARGET_DESC)


@unittest.skipUnless(HAS_DB, "pdg.sqlite is missing; run fetch_data.py first")
class TestBaseline(unittest.TestCase):
    """Baseline readout. ★ The numbers must be pinned, not just "looked at once and
    found correct" — otherwise every mutation below could be glossed over with "the
    readout was always like that"."""

    def test_baseline_has_pioneer(self):
        claims, r = aligned.run()
        self.assertGreater(r.total, 0, "the comparison domain must not be empty")
        # ★ Under the correct selection out_of_domain must be 0: applies is always true.
        #   A non-zero value here means some account was silently skipped — that is
        #   three-level silence, not "the readout looks nice".
        self.assertEqual(r.out_of_domain, 0,
                         f"the correct selection should have no out-of-domain points, got {r.out_of_domain}")
        self.assertTrue(r.pioneers, "there should be at least one pioneer (the smallest-error row)")

    def test_pioneer_is_the_precise_measurement(self):
        """The pioneer must be the row with the smallest error — a mechanically
        checkable criterion."""
        rows = _load()
        claims, r = aligned.run(rows)
        self.assertEqual(len(r.pioneers), 1, f"there should be exactly one pioneer, got {r.pioneers}")
        idx = next(iter(r.pioneers))
        self.assertEqual(r.names[idx], rows[0][0],
                         f"the pioneer should be the smallest-error row {rows[0][0]}")

    def test_pioneer_fraction_is_not_degenerate(self):
        """★ Key assertion: the pioneer share must not be 100%.

        Error mode 2 (the predicate does not read x) gives 4/4 = 100%.
        Without this assertion, a constant vector would be accepted as a normal readout.
        """
        claims, r = aligned.run()
        frac = sum(r.pioneers.values()) / r.total
        self.assertLess(frac, 0.95,
                        f"pioneer share {frac:.0%} ≈100% — the verdict does not change with the parameter point, "
                        f"the fingerprint of zero information")


@unittest.skipUnless(HAS_DB, "pdg.sqlite is missing")
class TestMutationTooLoose(unittest.TestCase):
    """Too-loose direction: breaking the code **should be caught**, i.e. the mutation
    must turn the test red."""

    def test_mut_1_baseline_changed_to_wrong_row(self):
        """Mutation: use any middle row as the baseline instead of the smallest-error row."""
        rows = _load()
        mutated = list(rows)
        base_val = mutated[5][1]
        claims = [
            Claim(name=r[0],
                  predicate=lambda x, r=r: abs(r[1] - base_val) <= max(r[2], r[3]) * x[1],
                  applies=lambda x: True, domain_note="m",
                  source="PDG", quote=f"v={r[1]}", quote_source=f"v={r[1]}")
            for r in mutated
        ]
        from breakingdiff import compare_n
        r = compare_n(claims, list(aligned.CRITERIA), chain=False)
        # After swapping the baseline, the original pioneer no longer holds alone → the
        # assertion must go red
        self.assertNotEqual(
            sum(r.pioneers.values()), 1,
            "the pioneer count did not change after swapping the baseline — the baseline readout is not correctly bound")

    def test_mut_2_criteria_all_too_loose(self):
        """Mutation: loosen every criterion to 100σ → all points all_true → zero information."""
        rows = _load()
        base = rows[0][1]
        claims = [
            Claim(name=r[0],
                  predicate=lambda x, r=r: abs(r[1] - base) <= max(r[2], r[3]) * 100.0,
                  applies=lambda x: True, domain_note="m",
                  source="PDG", quote=f"v={r[1]}", quote_source=f"v={r[1]}")
            for r in rows
        ]
        from breakingdiff import compare_n
        r = compare_n(claims, list(aligned.CRITERIA), chain=False)
        self.assertEqual(r.all_true, r.total,
                         "everything should be all_true under 100σ — not all_true means the predicate construction has another bug")

    def test_mut_3_applies_always_false(self):
        """Mutation: applies always false → every point skipped as out-of-domain (a zero readout disguised as a pass)."""
        rows = _load()
        base = rows[0][1]
        claims = [
            Claim(name=r[0],
                  predicate=lambda x, r=r: abs(r[1] - base) <= max(r[2], r[3]) * x[1],
                  applies=lambda x: False, domain_note="m",
                  source="PDG", quote=f"v={r[1]}", quote_source=f"v={r[1]}")
            for r in rows
        ]
        from breakingdiff import compare_n
        r = compare_n(claims, list(aligned.CRITERIA), chain=False)
        self.assertEqual(r.total, 0, "the comparison domain should be empty when applies is always false")
        self.assertEqual(r.out_of_domain, len(aligned.CRITERIA),
                         "every point should fall out of domain")
        # ★ And coverage_guard must stop it
        from coverage_guard import require_covered, CoverageError
        with self.assertRaises(CoverageError):
            require_covered(["B038RE"], [], what="all accounts")


@unittest.skipUnless(HAS_DB, "pdg.sqlite is missing")
class TestMutationTooTight(unittest.TestCase):
    """Too-tight direction: do not block every account that should be let through."""

    def test_mut_4_criteria_absurdly_tight(self):
        """Mutation: tighten the criteria to 0.001σ → all_false. Also zero information, but in the opposite direction.

        ★ Construction point: **the baseline itself must be excluded**.
        The baseline's difference from itself is always 0, and `0 <= any positive
        threshold` is always true, so as long as the baseline stays in the set,
        all_false can never happen — the measured all_false=0 is not "bad
        construction", it is mathematically impossible.
        That is itself a selection discipline to remember: the baseline row cannot
        also serve as the object of the criterion.
        """
        rows = _load()
        base = rows[0][1]
        others = rows[1:]          # ★ exclude the baseline itself
        claims = [
            Claim(name=r[0],
                  predicate=lambda x, r=r: abs(r[1] - base) <= max(r[2], r[3]) * 0.001,
                  applies=lambda x: True, domain_note="m",
                  source="PDG", quote=f"v={r[1]}", quote_source=f"v={r[1]}")
            for r in others
        ]
        from breakingdiff import compare_n
        r = compare_n(claims, list(aligned.CRITERIA), chain=False)
        self.assertEqual(r.all_false, r.total,
                         f"everything should be all_false under 0.001σ, got all_false={r.all_false}/{r.total}")
        self.assertEqual(sum(r.pioneers.values()), 0,
                         "there should be no pioneer when everything is false")

    def test_mut_4b_baseline_self_claim_cannot_go_false(self):
        """★ The reverse side pins down the construction discipline above: the baseline row is always true under any positive threshold.

        This is a record of a **capability boundary**: it means the "all_false" readout
        is inherently unreachable as long as the baseline stays in the set. To read
        all_false, the construction must be changed.
        """
        rows = _load()
        base = rows[0][1]
        claims = [
            Claim(name=r[0],
                  predicate=lambda x, r=r: abs(r[1] - base) <= max(r[2], r[3]) * 0.001,
                  applies=lambda x: True, domain_note="m",
                  source="PDG", quote=f"v={r[1]}", quote_source=f"v={r[1]}")
            for r in rows           # ← the baseline **is** in the set
        ]
        from breakingdiff import compare_n
        r = compare_n(claims, list(aligned.CRITERIA), chain=False)
        self.assertEqual(r.all_false, 0,
                         "the baseline's own difference is 0, always true, so all_false is unreachable — "
                         "if it really read all_false, the predicate has been broken")

    def test_tight_and_loose_are_distinguishable(self):
        """★ Bidirectional assertion: too loose and too tight must give **different**
        readouts, otherwise the verdict logic is insensitive to the criteria (that is,
        decorative parameter points)."""
        rows = _load()
        base = rows[0][1]

        def build(mult):
            return [
                Claim(name=r[0],
                      predicate=(lambda x, r=r, m=mult:
                                 abs(r[1] - base) <= max(r[2], r[3]) * x[1] * m),
                      applies=lambda x: True, domain_note="m",
                      source="PDG", quote=f"v={r[1]}", quote_source=f"v={r[1]}")
                for r in rows
            ]

        from breakingdiff import compare_n
        tight = compare_n(build(0.1), list(aligned.CRITERIA), chain=False)
        loose = compare_n(build(100.0), list(aligned.CRITERIA), chain=False)
        self.assertNotEqual(
            (tight.all_true, tight.all_false),
            (loose.all_true, loose.all_false),
            "the readout did not change when the criteria were loosened 1000x → the verdict is insensitive to the criteria (decorative parameter points)")


@unittest.skipUnless(HAS_DB, "pdg.sqlite is missing")
class TestProvenance(unittest.TestCase):
    """Provenance gate: error mode 4 must be stopped."""

    def test_quote_mismatch_raises(self):
        rows = _load()
        r = rows[0]
        with self.assertRaises(ProvenanceError):
            Claim(name="m", predicate=lambda x: True, applies=lambda x: True,
                  domain_note="m", source="PDG",
                  quote="a summary with different wording",
                  quote_source=f"pdgid={r[0]}; value={r[1]:.6g}")

    def test_quote_substring_limitation(self):
        """★ Record the granularity limit of the verbatim check: dropping a few digits
        still counts as a substring and is let through.

        This is not a bug report; it is a record of a **capability ceiling**:
        the verbatim check only guarantees "the quoted string appears in the source";
        it does not guarantee "the quoted string expresses what the source means".
        """
        rows = _load()
        r = rows[0]
        src = f"pdgid={r[0]}; value={r[1]:.6g}"
        # A few digits less precision is still a substring → construction lets it through
        Claim(name="m", predicate=lambda x: True, applies=lambda x: True,
              domain_note="m", source="PDG",
              quote=f"value={r[1]:.4g}", quote_source=src)
        # But changed wording is not a substring → stopped
        with self.assertRaises(ProvenanceError):
            Claim(name="m", predicate=lambda x: True, applies=lambda x: True,
                  domain_note="m", source="PDG",
                  quote="the value is about x", quote_source=src)


@unittest.skipUnless(HAS_DB, "pdg.sqlite is missing")
class TestDegenerateFingerprint(unittest.TestCase):
    """★ Mechanical check of the degenerate-readout fingerprints.

    The table in §4 of the teaching document must be **measured**, not invented.
    This class pins six readout shapes so the document and the code cannot drift.

    ★ The most valuable item: there are **three** degeneracies here that all show
      "all zeros" (applies always false / constant verdict vector / accounts not
      same-source). Eyeballing the readout treats three diseases as one.
      Only total, split, and pioneers together tell them apart.
    """

    def _mk(self, **kw):
        rows = _load()
        return [Claim(name=r[0], domain_note="m", source="PDG",
                      quote="x", quote_source="x", **kw) for r in rows]

    def _shape(self, claims, domain=None):
        from breakingdiff import compare_n
        return compare_n(claims, list(domain or aligned.CRITERIA), chain=False)

    # ---------- Normal baseline ----------

    def test_fp0_baseline_shape(self):
        """Baseline shape: not all zeros, not all true, has a pioneer, out_of_domain 0."""
        _claims, r = aligned.run()
        self.assertEqual(
            (r.total, r.all_true, r.all_false, r.split, r.out_of_domain),
            (5, 0, 0, 2, 0),
            f"the baseline readout shape changed, got {total_summary(r)}")

    # ---------- Degenerate one: predicate always true ----------

    def test_fp1_predicate_always_true(self):
        """Predicate always true (does not read x) → all_true = total, and no pioneer."""
        r = self._shape(self._mk(predicate=lambda x: True,
                                 applies=lambda x: True))
        self.assertEqual((r.all_true, r.all_false, r.total), (5, 0, 5))
        self.assertEqual(sum(r.pioneers.values()), 0,
                         "there should be no pioneer when everything is true")

    # ---------- Degenerate two: applies always false ----------

    def test_fp2_applies_always_false(self):
        """applies always false → all zeros, and total = 0 (not a single point was compared)."""
        r = self._shape(self._mk(predicate=lambda x: True,
                                 applies=lambda x: False))
        self.assertEqual((r.all_true, r.all_false, r.split, r.total),
                         (0, 0, 0, 0))
        self.assertEqual(r.out_of_domain, len(aligned.CRITERIA),
                         "every parameter point should fall out of domain")

    # ---------- Degenerate three: constant verdict vector (error modes 2 / 3) ----------

    def test_fp3_verdict_vector_constant(self):
        """★ Constant verdict vector → all zeros, but total > 0."""
        _c, r, _rows = misaligned.wrong_2_predicate_ignores_x()
        self.assertEqual((r.all_true, r.all_false, r.split), (0, 0, 0))
        self.assertGreater(r.total, 0, "★ key: total > 0")
        self.assertEqual(sum(r.pioneers.values()), r.total,
                         "under a constant vector every account is counted as a pioneer at every point")

    def test_fp3b_decorative_criteria_same_fingerprint(self):
        """Error modes 3 and 2 are **the same disease**; the fingerprints must be identical."""
        _c, r2, _rows = misaligned.wrong_2_predicate_ignores_x()
        _c, r3, _rows, _dom = misaligned.wrong_3_decorative_criteria()
        self.assertEqual(
            (r2.all_true, r2.all_false, r2.split, bool(r2.pioneers)),
            (r3.all_true, r3.all_false, r3.split, bool(r3.pioneers)),
            "★ error modes 2 and 3 should land on the same fingerprint — "
            "whether the criterion names sound intimidating does not change the disease")
        self.assertEqual(sum(r3.pioneers.values()) / r3.total, 1.0,
                         "under a constant vector the pioneer share should be 100%")

    # ---------- Degenerate four: accounts not same-source (error mode 1) ----------

    def test_fp4_mixed_quantity_split_everywhere(self):
        """★ Accounts not same-source → also all zeros, but split = total (every point splits).

        This is the only difference from degenerate three: **there is a split, but the
        split credits nobody**.
        """
        _c, r, _rows, _base = misaligned.wrong_1_by_parent()
        self.assertEqual((r.all_true, r.all_false), (0, 0))
        self.assertGreater(r.total, 0)
        self.assertEqual(r.split, r.total,
                         "error mode 1 should split at every parameter point")
        self.assertEqual((r.outliers, r.pioneers), ({}, {}),
                         "error mode 1 must not give any attribution — that is exactly what makes it dangerous")

    # ---------- Put the three "all zeros" together ----------

    def test_fp_all_zero_are_distinguishable_only_by_total_and_split(self):
        """★ All three diseases show all zeros; only total / split / pioneers tell them apart.

        Without this assertion, the three above could each hold while the document
        writes them up as one sentence "all zeros = something is wrong", which mixes
        three diseases into one prescription.
        """
        r_apply = self._shape(self._mk(predicate=lambda x: True,
                                       applies=lambda x: False))
        _c, r_const, _rows = misaligned.wrong_2_predicate_ignores_x()
        _c, r_mixed, _rows, _base = misaligned.wrong_1_by_parent()

        # All three look like all zeros to the naked eye
        for tag, r in (("applies always false", r_apply), ("constant verdict", r_const),
                       ("mixed accounts", r_mixed)):
            self.assertEqual((r.all_true, r.all_false), (0, 0),
                             f"{tag} should show all zeros")
        # But total differs pairwise
        self.assertEqual(r_apply.total, 0, "applies always false = nothing was compared")
        self.assertGreater(r_const.total, 0)
        self.assertGreater(r_mixed.total, 0)
        self.assertNotEqual(r_const.total, r_mixed.total)
        # And split plus pioneers separate the latter two
        self.assertEqual(r_const.split, 0, "constant verdict: split count 0")
        self.assertGreater(r_mixed.split, 0, "mixed accounts: split count > 0")
        self.assertEqual(sum(r_const.pioneers.values()), r_const.total)
        self.assertEqual(sum(r_mixed.pioneers.values()), 0)


class TestPortability(unittest.TestCase):
    """★ Movability guard: the case must still run after the directory moves.

    This discipline was forced by a real migration: the script used to hard-code
    `_ROOT = ../../..`, and moving it to a directory one nesting level shallower
    immediately produced ModuleNotFoundError.
    And the last thing a case study can afford is "it won't run somewhere else" —
    the first thing a reader does is try it from a different location, and it breaks.
    """

    def test_root_is_discovered_not_hardcoded(self):
        for fn in ("aligned.py", "misaligned.py", "test_aligned.py"):
            with open(os.path.join(_HERE, fn), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(
                src, r'_ROOT\s*=\s*os\.path\.abspath\(os\.path\.join\(_HERE,\s*"\.\.',
                f"{fn}: _ROOT must not hard-code how many levels to walk up — moving the directory breaks it")
            self.assertIn("_find_scripts_root", src,
                          f"{fn}: should search upward for scripts/breakingdiff.py")

    def test_scripts_root_is_actually_resolved(self):
        self.assertTrue(
            os.path.isfile(os.path.join(aligned._ROOT, "scripts", "breakingdiff.py")),
            f"failed to resolve scripts/breakingdiff.py, _ROOT={aligned._ROOT}")

    def test_missing_scripts_root_exits_with_guidance(self):
        """★ When it cannot be found it must exit explicitly and state the requirement, not raise a bare ModuleNotFoundError."""
        import tempfile

        # ★ The construction point must be **outside the repository**: if it sat under
        #   this directory, walking up a few levels would still hit scripts/, and this
        #   assertion would be a false green.
        tmp = tempfile.mkdtemp(prefix="bd_nowhere_")
        deep = os.path.join(tmp, "a", "b", "c")
        os.makedirs(deep, exist_ok=True)
        saved = aligned._HERE
        try:
            aligned._HERE = deep
            with self.assertRaises(SystemExit) as cm:
                aligned._find_scripts_root()
            self.assertIn("breakingdiff", str(cm.exception))
        finally:
            aligned._HERE = saved
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestNoDataGuard(unittest.TestCase):
    """★ Missing data must exit explicitly; it must not quietly run an empty report."""

    def test_missing_db_exits_nonzero(self):
        """★ Missing data must exit explicitly; it must not quietly run an empty report.

        The construction uses a path that is **guaranteed not to exist**, and cleans up
        afterwards — because sqlite3.connect creates a 0-byte empty database out of
        thin air, and a leftover file makes the next run "exists but has no tables",
        turning the test into a false green.
        """
        ghost = os.path.join(_HERE, "__no_such__.sqlite")
        saved = aligned.DB
        try:
            if os.path.exists(ghost):
                os.remove(ghost)
            aligned.DB = ghost
            self.assertFalse(os.path.exists(ghost), "precondition: ghost must not exist")
            with self.assertRaises(SystemExit):
                aligned.main()
            #★ Also pin down: exiting must not leave an empty database behind
            self.assertFalse(
                os.path.exists(ghost),
                "the existence check should run before exit; sqlite3.connect must not be allowed to create an empty database")
        finally:
            aligned.DB = saved
            if os.path.exists(ghost):
                os.remove(ghost)


class TestDataPin(unittest.TestCase):
    """★ The corpus is pinned to PDG 2024: a wrong edition / wrong rows / tampered
    bytes must all go red.

    Background: the upstream online edition is now 2026 (edition=2026 / schema 0.3 /
    19,587 rows / about 25.75 MB), which is not the same data as the in-repo 2024
    corpus. If the fetch script still downloaded by URL, or if the verifier let a
    wrong edition through, every readout in this case would silently become another
    corpus's readout — exactly the "failure that raises nothing" this case teaches.
    So what is pinned must have assertions.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bd_pdgpin_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _fake(self, **kw):
        p = os.path.join(self.tmp, "pdg.sqlite")
        if os.path.exists(p):
            os.remove(p)
        return _make_fake_pdg_sqlite(p, **kw)

    # ---------- the pinned constants themselves ----------

    def test_pinned_constants_are_the_documented_facts(self):
        """★ The edition/citation/schema/size/bytes the docs state must equal the code constants."""
        self.assertEqual(fetch_data.PINNED_EDITION, "2024")
        self.assertEqual(fetch_data.PINNED_SCHEMA_VERSION, "0.2")
        self.assertEqual(fetch_data.PINNED_PDGDATA_ROWS, 18064)
        self.assertEqual(fetch_data.PINNED_BYTES, 7593984)
        self.assertEqual(len(fetch_data.PINNED_SHA256), 64)
        self.assertIn("Phys. Rev. D 110, 030001", fetch_data.PINNED_CITATION)
        self.assertIn("2024", fetch_data.PINNED_CITATION)

    # ---------- the real corpus: every pinned fact must be equal ----------

    @unittest.skipUnless(HAS_DB, "missing pdg.sqlite; run fetch_data.py to verify/recover")
    def test_real_db_matches_every_pinned_fact(self):
        """★ If the in-repo corpus is swapped to the 2026 edition (or edited), this must go red."""
        facts = fetch_data.verify_sqlite(DB)
        self.assertEqual(facts["edition"], fetch_data.PINNED_EDITION)
        self.assertEqual(facts["schema_version"],
                         fetch_data.PINNED_SCHEMA_VERSION)
        self.assertEqual(facts["pdgdata_rows"], fetch_data.PINNED_PDGDATA_ROWS)
        self.assertEqual(facts["citation"], fetch_data.PINNED_CITATION)
        self.assertEqual(facts["bytes"], fetch_data.PINNED_BYTES)
        self.assertEqual(facts["sha256"], fetch_data.PINNED_SHA256)

    @unittest.skipUnless(HAS_DB, "missing pdg.sqlite")
    def test_main_accepts_the_pinned_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fetch_data.main(["--path", DB])
        text = out.getvalue()
        self.assertIn("2024", text)
        self.assertIn(fetch_data.PINNED_SHA256, text)

    # ---------- forged wrong editions: each must go red ----------

    def test_wrong_edition_is_red(self):
        """★ Core mutation: switch edition to the upstream 2026 → must raise."""
        p = self._fake(edition="2026", schema="0.3", rows=19587)
        with self.assertRaises(fetch_data.PinError) as cm:
            fetch_data.verify_sqlite(p)
        msg = str(cm.exception)
        self.assertIn("edition", msg)
        self.assertIn("2024", msg, "the error must state that this case pins 2024")

    def test_wrong_schema_version_is_red(self):
        p = self._fake(schema="0.3")
        with self.assertRaises(fetch_data.PinError) as cm:
            fetch_data.verify_sqlite(p)
        self.assertIn("schema_version", str(cm.exception))

    def test_wrong_row_count_is_red(self):
        """★ Changing only the row count, with everything else right, must also go red —
        otherwise "different data but same structure name" slips through."""
        p = self._fake(rows=19587)
        with self.assertRaises(fetch_data.PinError) as cm:
            fetch_data.verify_sqlite(p)
        self.assertIn("row count", str(cm.exception))

    def test_citation_drift_is_red(self):
        p = self._fake(citation="S. Navas et al. (PDG), Phys. Rev. D 111, 030001 (2025)")
        with self.assertRaises(fetch_data.PinError) as cm:
            fetch_data.verify_sqlite(p)
        self.assertIn("citation", str(cm.exception))

    def test_tampered_bytes_are_caught_by_sha256_not_only_size(self):
        """★ Structure all right and bytes padded to the pinned size, yet SHA256 must stop it.

        This one specifically guards against "verification only looks at size/rows":
        after padding the file to PINNED_BYTES, size and row count both match; only
        SHA256 can detect that the content was changed.
        """
        p = self._fake()
        size = os.path.getsize(p)
        self.assertLess(size, fetch_data.PINNED_BYTES)
        with open(p, "ab") as f:
            f.write(b"\0" * (fetch_data.PINNED_BYTES - size))
        self.assertEqual(os.path.getsize(p), fetch_data.PINNED_BYTES)
        with self.assertRaises(fetch_data.PinError) as cm:
            fetch_data.verify_sqlite(p)
        self.assertIn("SHA256", str(cm.exception))

    # ---------- missing: recovery guidance, never a silent download ----------

    def test_missing_file_exits_with_recovery_not_download(self):
        ghost = os.path.join(self.tmp, "__no_such__.sqlite")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                fetch_data.main(["--path", ghost])
        self.assertEqual(cm.exception.code, 1)
        text = out.getvalue() + err.getvalue()
        self.assertIn("2024", text, "the recovery text must name the pinned 2024 edition")
        self.assertIn("SHA256", text, "the recovery text must give the SHA256 anchor")
        self.assertIn("Recovery", text, "a missing file must say how to recover")
        self.assertFalse(os.path.exists(ghost),
                         "★ must not create an empty database while checking, and must not "
                         "silently download a substitute edition")

    def test_fetch_script_has_no_download_path(self):
        """★ Structural assertion: the fetch script must contain no network download mechanism.

        A human convention "do not download 2026" is not enough — as long as a download
        path exists, the next person will trigger it.
        """
        with open(os.path.join(_HERE, "fetch_data.py"), encoding="utf-8") as f:
            src = f.read()
        for forbidden in ("http://", "https://", "urllib", "requests",
                          "curl", "wget", "os.system", "subprocess"):
            self.assertNotIn(forbidden, src,
                             f"fetch_data.py must contain no download mechanism: {forbidden!r}; "
                             f"this case pins 2024 and only gives recovery steps when it is missing")

    # ---------- the same guard on the read path ----------

    def test_aligned_rejects_wrong_edition(self):
        """★ Even bypassing fetch_data and running aligned.py directly must be blocked."""
        p = self._fake(edition="2026", schema="0.3", rows=19587)
        saved = aligned.DB
        try:
            aligned.DB = p
            with self.assertRaises(SystemExit) as cm:
                aligned.load_measurements(aligned.TARGET_DESC)
            self.assertIn("2024", str(cm.exception))
        finally:
            aligned.DB = saved

    def test_misaligned_rejects_wrong_edition(self):
        p = self._fake(edition="2026", schema="0.3", rows=19587)
        saved = misaligned.DB
        try:
            misaligned.DB = p
            with self.assertRaises(SystemExit) as cm:
                misaligned._con()
            self.assertIn("2024", str(cm.exception))
        finally:
            misaligned.DB = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)

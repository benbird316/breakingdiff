# -*- coding: utf-8 -*-
"""Permanent regression suite for iteration_chain: ratchet capture, outlier attribution,
degenerate equivalence with pairwise, gate reuse, and the console-encoding contract of
the casestudy CLI entries."""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "scripts"))

from breakingdiff import (Claim, ProvenanceError, SourceTestError,
                          compare, compare_n)
from iteration_chain import (CHANGELOG_V1, DOMAIN, SPECS, main,
                             make_version_claim)

# Discovery criterion for a casestudy CLI entry: a script on disk with an
# `if __name__ == "__main__":` guard. Discovery is reconciled against the explicit
# list below, so a newly added entry that nobody registered goes red on the spot.
ENTRY_MAIN_RE = re.compile(r"^if __name__ == [\"']__main__[\"']:", re.M)

# Every CLI entry under casestudy/ — all of them must switch stdout to UTF-8 before
# __main__. A Chinese Windows console defaults to GBK and the report contains ⚠️/★,
# which are outside that code page; an entry that does not switch crashes with
# UnicodeEncodeError at exactly the moment it is supposed to raise the alarm — the
# script dying while it should speak is worse than staying silent.
# The list may only grow/shrink explicitly: a missing registration is caught by
# test_gbk_smoke_skips_are_named (enumerate completely or declare the gap).
CASESTUDY_CLI_ENTRIES = (
    "casestudy/hubble/case_study.py",
    "casestudy/k8s/aligned.py",
    "casestudy/k8s/fetch_data.py",
    "casestudy/k8s/misaligned.py",
    "casestudy/llama/aligned.py",
    "casestudy/llama/fetch_corpus.py",
    "casestudy/llama/misaligned.py",
    "casestudy/malecns/aligned.py",
    "casestudy/malecns/fetch_corpus.py",
    "casestudy/malecns/misaligned.py",
    "casestudy/pdg/aligned.py",
    "casestudy/pdg/fetch_data.py",
    "casestudy/pdg/misaligned.py",
    "casestudy/port/reference.py",
)

# The behaviour smoke only runs entries that need no external corpus (pdg.sqlite and
# claims.json are tracked in the repo). Entries that need the ~2.1GB llama build or
# the ~56MB malecns feather tables are skipped with the reason named — never silently
# skipped: "did not run" and "ran and passed" must stay distinguishable in the report.
GBK_SMOKE_RUNNABLE = (
    ("casestudy/hubble/case_study.py", "pure script, no external corpus"),
    ("casestudy/pdg/aligned.py", "uses the pdg.sqlite tracked in the repo"),
    ("casestudy/pdg/misaligned.py", "uses the pdg.sqlite tracked in the repo"),
    ("casestudy/pdg/fetch_data.py", "verifies the tracked pdg.sqlite; does not download"),
    ("casestudy/port/reference.py", "uses the claims.json tracked in the repo"),
)
GBK_SMOKE_SKIPPED = (
    ("casestudy/k8s/aligned.py", "needs the ~6MB OpenAPI snapshots"),
    ("casestudy/k8s/misaligned.py", "needs the ~6MB OpenAPI snapshots"),
    ("casestudy/k8s/fetch_data.py", "fetches the ~6MB OpenAPI snapshots"),
    ("casestudy/llama/aligned.py", "needs llama-b*/ (~2.1GB extracted)"),
    ("casestudy/llama/misaligned.py", "needs llama-b*/ (~2.1GB extracted)"),
    ("casestudy/llama/fetch_corpus.py", "fetches ~450MB of llama.cpp assets"),
    ("casestudy/malecns/aligned.py", "needs two feather tables (~56MB)"),
    ("casestudy/malecns/misaligned.py", "needs two feather tables (~56MB)"),
    ("casestudy/malecns/fetch_corpus.py", "fetches the ~56MB feather tables"),
)


class TestIterationChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = [make_version_claim(*spec) for spec in SPECS]

    def test_ratchet_caught_with_attribution(self):
        """The chain check catches 3 ratchet violations, each with a directed
        (old, new, point) triple."""
        rn = compare_n(self.claims, DOMAIN, chain=True)
        self.assertEqual(rn.ratchet_total, 3)
        got = {(j, k, x) for j, k, x in rn.ratchet_witnesses}
        self.assertEqual(got, {(0, 2, "csv"), (1, 2, "csv"), (1, 2, "parquet")})

    def test_adjacent_pairwise_blind_to_direction(self):
        """A pairwise diff's divergence region cannot tell 'dropped capability' from
        'changed differently' — that is why the chain check exists.
        compare(v2, v3) has 2 divergence points (csv+parquet); the report gives no
        regression verdict at all."""
        v2, v3 = self.claims[1], self.claims[2]
        r = compare(v2, v3, DOMAIN)
        self.assertEqual(r.divergence, 2)
        self.assertEqual(r.dominance, 1)      # xlsx looks like a "normal addition"
        self.assertFalse(hasattr(r, "ratchet_total"))   # pairwise readouts have no direction field

    def test_outlier_and_pioneer_attribution(self):
        rn = compare_n(self.claims, DOMAIN)
        self.assertEqual(rn.outliers, {2: 1})          # csv: missing exactly in v3
        self.assertEqual(rn.pioneers, {1: 1, 2: 1})    # parquet exactly in v2; xlsx exactly in v3
        self.assertEqual(rn.all_true, 1)               # json consensus
        self.assertEqual(rn.split, 0)

    def test_chain_off_means_no_ratchet_readout(self):
        rn = compare_n(self.claims, DOMAIN)
        self.assertEqual(rn.ratchet_total, 0)
        self.assertEqual(rn.ratchet_witnesses, [])

    def test_pair_of_claims_matches_pairwise(self):
        """Degenerate equivalence: the shape counts of a two-account compare_n and the
        four quadrants of compare line up one to one."""
        p, q = self.claims[0], self.claims[2]
        r = compare(p, q, DOMAIN)
        rn = compare_n([p, q], DOMAIN)
        self.assertEqual(rn.all_true, r.common)
        self.assertEqual(rn.pioneers.get(0, 0), r.divergence)   # (T,F) = unique to P
        self.assertEqual(rn.pioneers.get(1, 0), r.dominance)    # (F,T) = unique to Q
        self.assertEqual(rn.all_false, r.neither)
        self.assertEqual(rn.out_of_domain, r.out_of_domain)

    def test_guards_still_apply(self):
        """The three gates still bite on the compare_n path. The two paths are verified
        separately: the construction-time provenance gate (ProvenanceError) and the
        comparison-time source-example gate (SourceTestError)."""
        v1, v2 = self.claims[0], self.claims[1]
        # Comparison time: the Claim is legal, but its predicate contradicts its own
        # source self-test; _guard bites during compare_n
        self_liar = Claim(
            name="self-liar", predicate=lambda cap: True, applies=lambda cap: True,
            domain_note="n/a", source="demo-repo@v9:CHANGELOG.md",
            quote="- export: --format json, --format csv", quote_source=CHANGELOG_V1,
            source_tests=(("csv", False),),   # csv is plainly in the corpus, yet the predicate denies it
        )
        with self.assertRaises(SourceTestError):
            compare_n([v1, self_liar], DOMAIN)
        # Construction time: a missing source is rejected on the spot
        with self.assertRaises(ProvenanceError):
            Claim(name="bogus", predicate=lambda x: True, applies=lambda x: True,
                  domain_note="n/a", source="", quote="x")

    def test_needs_at_least_two_claims(self):
        with self.assertRaises(ValueError):
            compare_n(self.claims[:1], DOMAIN)

    def test_anchor_out_of_range(self):
        with self.assertRaises(ValueError):
            compare_n(self.claims, DOMAIN, anchor=9)


class TestRatchetDirection(unittest.TestCase):
    """The ratchet direction must be fixed by order_key, never guessed from list position.

    Background: a ratchet violation means "the old version had it, the new version
    dropped it", so the direction depends entirely on which account is newer.
    compare_n used to treat j<k as "old → new", yet it has no field saying which
    account is newer — the caller owns the order. Pass [v3, v1, v2] by mistake and
    the tool computes a reversed regression "v3 → v2" while the readout looks
    perfectly normal and nothing warns.

    That is worse than a zero readout: a zero readout makes people suspicious,
    while a reversed conclusion looks credible.
    """

    @classmethod
    def setUpClass(cls):
        cls.claims = [make_version_claim(*spec) for spec in SPECS]
        # The corpus carries version numbers; sorting by them gives the real
        # chronological order. Wrap it in staticmethod: a plain lambda would become
        # a bound method, cls would be passed automatically, and the signature would
        # have 3 parameters.
        cls.order_key = staticmethod(lambda i, c: c.name)

    def test_order_key_fixes_direction_when_input_is_shuffled(self):
        """Shuffled input + order_key = same readout as canonical input (witness
        direction included)."""
        canonical = compare_n(self.claims, DOMAIN, chain=True,
                              order_key=self.order_key)
        shuffled = compare_n([self.claims[2], self.claims[0], self.claims[1]],
                             DOMAIN, chain=True, order_key=self.order_key)
        self.assertEqual(canonical.ratchet_total, shuffled.ratchet_total)
        self.assertEqual(
            {(self.claims[j].name, self.claims[k].name, x)
             for j, k, x in canonical.ratchet_witnesses},
            {(self.claims[j].name, self.claims[k].name, x)
             for j, k, x in shuffled.ratchet_witnesses})

    def test_order_key_makes_direction_trusted(self):
        """Giving order_key → ratchet_trusted=True (the report no longer warns about
        direction)."""
        rn = compare_n(self.claims, DOMAIN, chain=True, order_key=self.order_key)
        self.assertTrue(rn.ratchet_trusted)

    def test_without_order_key_direction_is_flagged_untrusted(self):
        """No order_key → the readout is still produced, but it must report "direction
        unverified".

        This is the core of the group: not raising is deliberate — the order simply
        cannot be derived from a Claim, and forcing an error would push callers into
        inventing a key. But the uncertainty must be surfaced in the readout, not
        silently assumed to follow list position.
        """
        rn = compare_n(self.claims, DOMAIN, chain=True)
        self.assertFalse(rn.ratchet_trusted)
        self.assertEqual(rn.ratchet_total, 3)   # the readout stays; it is merely marked uncertain

    def test_report_warns_about_untrusted_direction(self):
        """An untrusted direction must be visible in the report body, not only in a
        data field."""
        from breakingdiff import render_n
        rn = compare_n(self.claims, DOMAIN, chain=True)
        out = render_n(self.claims, rn)
        self.assertIn("order_key", out)
        self.assertIn("direction", out)
        # with a trusted direction this warning must be absent
        rn2 = compare_n(self.claims, DOMAIN, chain=True, order_key=self.order_key)
        out2 = render_n(self.claims, rn2)
        self.assertNotIn("Order is not fixed by order_key", out2)

    def test_anchor_name_follows_the_same_reordering(self):
        """After reordering, anchor still points at the same account, not at a
        shifted index."""
        shuffled = [self.claims[2], self.claims[0], self.claims[1]]
        rn = compare_n(shuffled, DOMAIN, anchor=0, order_key=self.order_key)
        self.assertEqual(rn.anchor_name, "v3.0.0")

    def test_main_assertions_hold(self):
        """The red-first-then-green assertions shipped with the instance run end to
        end."""
        rn = main()
        self.assertEqual(rn.ratchet_total, 3)


class TestConsoleEncoding(unittest.TestCase):
    """A Chinese Windows console defaults to GBK, and the report's ⚠️/★ are outside
    that code page. An entry that does not switch its standard streams to UTF-8
    crashes with UnicodeEncodeError at the first ratchet warning — the script dying
    exactly when it is supposed to speak is worse than staying silent.

    Three layers, because each one alone has a hole:
      · the behaviour smoke runs the corpus-free entries under
        PYTHONIOENCODING=gbk and checks exit code / stderr / stdout bytes;
      · the static guard pins the switch inside the corpus-dependent entries, which
        the behaviour smoke can never run on a corpus-free checkout;
      · the enumeration reconciliation keeps both lists equal to what is on disk.
    """

    def test_casestudy_cli_entries_switch_stdout_to_utf8(self):
        """Static guard (14/14): every casestudy CLI entry switches stdout first.

        The behaviour smoke only covers the corpus-free entries; this test makes
        "reconfigure deleted from a corpus entry" go red as well, so the static
        coverage has no gap. The criterion is the entry's fixed shape — this repo
        switches before __main__ everywhere; changing the shape means changing this
        test with it.
        """
        for rel in CASESTUDY_CLI_ENTRIES:
            with self.subTest(entry=rel):
                path = REPO / rel
                self.assertTrue(path.is_file(), f"entry does not exist: {rel}")
                src = path.read_text(encoding="utf-8")
                self.assertIn(
                    "sys.stdout.reconfigure(", src,
                    f"{rel} is missing the stdout UTF-8 switch: under a GBK console, "
                    f"writing ⚠️/★ raises UnicodeEncodeError")

    def test_gbk_console_casestudy_entries_do_not_crash(self):
        """Parameterized GBK smoke: run each corpus-free entry as a subprocess with
        PYTHONIOENCODING=gbk.

        Three assertions: exit 0; no UnicodeEncodeError in stderr; stdout decodes as
        valid UTF-8. The third one covers the failure mode where reconfigure was
        removed but the output happens to be GBK-encodable: that does not crash, it
        writes GBK bytes that the terminal then renders as mojibake. The skip reasons
        for the corpus-dependent entries are reconciled by the next test.
        """
        env = dict(os.environ, PYTHONIOENCODING="gbk")
        for rel, why in GBK_SMOKE_RUNNABLE:
            with self.subTest(entry=rel):
                path = REPO / rel
                self.assertTrue(path.is_file(), f"entry does not exist: {rel} ({why})")
                proc = subprocess.run(
                    [sys.executable, str(path)], cwd=str(path.parent),
                    env=env, capture_output=True)
                err = proc.stderr.decode("utf-8", "replace")
                self.assertEqual(
                    proc.returncode, 0,
                    f"{rel} crashed under a GBK console ({why}): {err}")
                self.assertNotIn(
                    "UnicodeEncodeError", err,
                    f"{rel} raised UnicodeEncodeError while writing stderr: {err}")
                try:
                    proc.stdout.decode("utf-8")
                except UnicodeDecodeError:
                    self.fail(
                        f"{rel}'s stdout is not valid UTF-8 — the entry did not switch "
                        f"its standard streams to UTF-8, so a GBK terminal shows "
                        f"mojibake or crashes: {proc.stdout[:200]!r}")
                self.assertTrue(proc.stdout, f"{rel} produced no output; the smoke proves nothing")

    def test_gbk_smoke_skips_are_named(self):
        """Enumeration completeness: the CLI entries on disk = the explicit list =
        runnable ∪ skipped-with-a-reason.

        Disk discovery (`if __name__ == "__main__":`) catches "a new entry was never
        registered"; the list reconciliation catches "the same entry is both run and
        skipped"; the non-empty reason catches "silently skipped". All three layers
        are required.
        """
        discovered = set()
        for path in (REPO / "casestudy").rglob("*.py"):
            if "__pycache__" in path.parts or path.name.startswith("test_"):
                continue
            if ENTRY_MAIN_RE.search(path.read_text(encoding="utf-8")):
                discovered.add(path.relative_to(REPO).as_posix())
        self.assertEqual(
            discovered, set(CASESTUDY_CLI_ENTRIES),
            "the entry list does not match the disk: extra on disk "
            f"{sorted(discovered - set(CASESTUDY_CLI_ENTRIES))}, extra in the list "
            f"{sorted(set(CASESTUDY_CLI_ENTRIES) - discovered)}")
        runnable = {rel for rel, _ in GBK_SMOKE_RUNNABLE}
        skipped = {rel for rel, _ in GBK_SMOKE_SKIPPED}
        self.assertEqual(runnable & skipped, set(), "the same entry cannot be both run and skipped")
        self.assertEqual(
            runnable | skipped, discovered,
            f"entry classification is incomplete (who is missing?): {discovered - runnable - skipped}")
        for rel, why in GBK_SMOKE_SKIPPED:
            self.assertTrue(why.strip(), f"{rel} has an empty skip reason")


if __name__ == "__main__":
    unittest.main()

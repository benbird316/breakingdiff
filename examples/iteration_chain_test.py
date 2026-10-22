# -*- coding: utf-8 -*-
"""Permanent regression suite for iteration_chain: ratchet capture, outlier attribution,
degenerate equivalence with pairwise, and gate reuse."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from breakingdiff import (Claim, ProvenanceError, SourceTestError,
                          compare, compare_n)
from iteration_chain import (CHANGELOG_V1, DOMAIN, SPECS, main,
                             make_version_claim)


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


if __name__ == "__main__":
    unittest.main()

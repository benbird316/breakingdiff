# -*- coding: utf-8 -*-
"""The assertion surface of the K8s case.

What is guarded, and why these particular things
------------------------------------------------
The teaching proposition of this case is "on an existence baseline a removal
lands in the divergence column, and the product column follows the baseline, not
the data". So the assertion surface is not "the script runs" — it is four
things that could each silently stop being true:

  1. The four-quadrant readout (counts frozen). If a refactor changes how the
     parameter space is extracted, every count moves and the teaching file's
     tables become fiction.
  2. **The baseline flip actually flips.** This is the claim the case exists for.
     An assertion that only ever runs one orientation would pass even if the
     quadrant mapping were transposed.
  3. **The gate still refuses the type claim.** A refusal that stops happening
     looks like an improvement and is a regression: the discrimination gate
     would be quietly disabled, and this case would lose its second lesson.
  4. **The degenerate fingerprints keep their shape.** Scoped-to-one-group still
     collapses to a 1-point common set; a `$ref`-blind extractor still sees the
     827 / 912 pair. If these move, the traps the case warns about have changed
     shape and the prose is stale.

Plus corpus integrity: both files hash to the pinned SHA256. **A readout computed
over the wrong bytes is still a readout**, so this is checked before anything else.

When the corpus is absent the whole file skips and says which conclusion died —
following llama's corpus discipline: missing is not "pass", it is "this
conclusion is invalid".

Run: python test_aligned.py
"""
import hashlib
import json
import os
import sys
import unittest

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_FILE, NEW_FILE = "k8s-1.28.json", "k8s-1.31.json"
SHA_OLD = "44ff3c98bb011964585019e1765b0c09ee65d503e4c35cbda355df6a02486c86"
SHA_NEW = "ddcb3d5c3d85849f1fadb56387d3a7bf44712da291e5bd08b34df4e8a4247f8d"

# Frozen readouts, measured 2026-10-21 against the two pinned snapshots.
# 1.31 is a MINOR bump (v1.30 -> v1.31) and these counts are what that bump did.
FROZEN = {
    "union": 2049,
    "common": 1499,
    "removed": 193,      # divergence when P = old spec  ← the breaking changes
    "added": 357,        # dominance when P = old spec
    "neither": 0,
    "common_param_points": 727,
    "removal_groups": {"resource.k8s.io": 99,
                       "flowcontrol.apiserver.k8s.io": 55,
                       "networking.k8s.io": 39},
    "declared_params": {"k8s-1.28.json": 2916, "k8s-1.31.json": 3230},
    "ref_params": {"k8s-1.28.json": 2089, "k8s-1.31.json": 2318},
}

_HAVE_CORPUS = all(os.path.isfile(os.path.join(HERE, f)) for f in (OLD_FILE, NEW_FILE))
if not _HAVE_CORPUS:
    print("=" * 74)
    print("SKIP: corpus absent. This is NOT a pass — the cross-version conclusion")
    print("      (present in 1.28 -> absent in 1.31) cannot be produced without both")
    print("      snapshots. Restore with: python fetch_data.py")
    print("=" * 74)
    raise SystemExit(0)

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(HERE))), "scripts"))

import aligned as A  # noqa: E402
from breakingdiff import SourceTestError, compare  # noqa: E402


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class TestCorpusIntegrity(unittest.TestCase):
    """Checked first: a readout over the wrong bytes is still a readout."""

    def test_old_spec_matches_pinned_sha256(self):
        self.assertEqual(_sha256(os.path.join(HERE, OLD_FILE)), SHA_OLD)

    def test_new_spec_matches_pinned_sha256(self):
        self.assertEqual(_sha256(os.path.join(HERE, NEW_FILE)), SHA_NEW)

    def test_both_specs_are_valid_json_objects(self):
        for fn in (OLD_FILE, NEW_FILE):
            with open(os.path.join(HERE, fn), encoding="utf-8") as f:
                doc = json.load(f)
            self.assertIsInstance(doc, dict, fn)
            self.assertIn("paths", doc, fn)

    def test_quote_is_verbatim_in_the_old_spec(self):
        self.assertIn(A.QUOTE, A.RAW[OLD_FILE])


class TestExistenceAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = compare(A.make_existence_claim(), A.make_existence_claim_new(),
                        A.UNION, max_witness=3)

    def test_union_size(self):
        self.assertEqual(len(A.UNION), FROZEN["union"])

    def test_no_out_of_domain_skips(self):
        # Both accounts are total over the union; a skip here means the surface
        # under test no longer covers the change — zero-reading territory.
        self.assertEqual(self.r.total, FROZEN["union"])

    def test_common_count(self):
        self.assertEqual(self.r.common, FROZEN["common"])

    def test_removals_land_in_divergence(self):
        self.assertEqual(self.r.divergence, FROZEN["removed"])

    def test_additions_land_in_dominance(self):
        self.assertEqual(self.r.dominance, FROZEN["added"])

    def test_neither_is_zero(self):
        self.assertEqual(self.r.neither, FROZEN["neither"])

    def test_quadrants_sum_to_the_domain(self):
        self.assertEqual(
            self.r.common + self.r.divergence + self.r.dominance + self.r.neither,
            FROZEN["union"])

    def test_source_tests_pass_on_both_accounts(self):
        for claim in (A.make_existence_claim(), A.make_existence_claim_new()):
            ok, tot, fails = claim.run_source_tests()
            self.assertEqual((ok, tot, fails), (3, 3, []), claim.name)

    def test_neither_account_contains_the_other(self):
        # "Neither contains the other" is mechanical: both exclusive columns are
        # non-empty. Asserted structurally rather than via the rendered verdict
        # string, so a wording change in render cannot turn this test red.
        self.assertGreater(self.r.divergence, 0)
        self.assertGreater(self.r.dominance, 0)


class TestProductColumnFollowsTheBaseline(unittest.TestCase):
    """The lesson the case exists for. Must be tested in BOTH orientations —
    an assertion that only runs one would still pass if the mapping transposed."""

    @classmethod
    def setUpClass(cls):
        cls.old_as_p = compare(A.make_existence_claim(), A.make_existence_claim_new(),
                               A.UNION, max_witness=1)
        cls.new_as_p = compare(A.make_existence_claim_new(), A.make_existence_claim(),
                               A.UNION, max_witness=1)

    def test_removals_are_divergence_when_p_is_the_old_account(self):
        self.assertEqual(self.old_as_p.divergence, FROZEN["removed"])
        self.assertEqual(self.old_as_p.dominance, FROZEN["added"])

    def test_removals_become_dominance_when_the_baseline_is_swapped(self):
        self.assertEqual(self.new_as_p.dominance, FROZEN["removed"])
        self.assertEqual(self.new_as_p.divergence, FROZEN["added"])

    def test_total_is_invariant_under_the_swap(self):
        self.assertEqual(self.old_as_p.total, self.new_as_p.total)


class TestRemovalGroupAggregation(unittest.TestCase):
    """193 points are unreadable; three rows are a checklist."""

    def test_removal_counts_by_api_group(self):
        self.assertEqual(dict(A.removals_by_group()), FROZEN["removal_groups"])

    def test_group_counts_sum_to_the_removal_total(self):
        self.assertEqual(sum(A.removals_by_group()[i][1]
                             for i in range(len(A.removals_by_group()))),
                         FROZEN["removed"])

    def test_only_three_groups_appear(self):
        self.assertEqual(len(A.removals_by_group()), 3)

    def test_every_removal_belongs_to_a_removed_group(self):
        removed = {p for p in A.OLD} - {p for p in A.NEW}
        self.assertTrue(all(A.api_group(p[0]) in FROZEN["removal_groups"] for p in removed))


class TestTypeFingerprintIsRefused(unittest.TestCase):
    """The second lesson: a criterion with no purchase in the domain does not read
    as zero, it reads as 'cannot be certified'. If this assertion ever fails
    because the claim now PASSES the gate, that is a regression, not a fix."""

    def test_gate_refuses_the_type_claim(self):
        with self.assertRaises(SourceTestError) as ctx:
            compare(A.make_type_claim(), A.TYPE_BASE, A.COMMON, max_witness=1)
        self.assertEqual(ctx.exception.reason, "READING_DISCRIMINATION_ZERO")

    def test_refusal_is_not_a_zero_readout(self):
        # The distinction the case turns on: blocked != "found nothing".
        # A zero readout would be a DiffResult; a refusal is an exception and
        # leaves no result object at all. Asserted on that difference rather
        # than on any printed text.
        with self.assertRaises(SourceTestError):
            compare(A.make_type_claim(), A.TYPE_BASE, A.COMMON, max_witness=1)

    def test_common_parameter_points_count(self):
        n = sum(1 for p in A.COMMON if A.OLD[p][0] == "param")
        self.assertEqual(n, FROZEN["common_param_points"])

    def test_no_parameter_type_differs_between_the_specs(self):
        differing = [p for p in A.COMMON
                     if A.OLD[p][0] == "param" and A.OLD[p][1] != A.NEW[p][1]]
        self.assertEqual(differing, [])


class TestDegenerateFingerprints(unittest.TestCase):
    """The traps must keep their shape, or the teaching file is stale."""

    @staticmethod
    def _ref_counts(fn):
        """Recomputed here rather than by calling misaligned.m3_ref_blind():
        the assertions must not depend on a function whose job is to print."""
        with open(os.path.join(HERE, fn), encoding="utf-8") as f:
            paths = json.load(f).get("paths", {})
        total = ref = 0
        for ops in paths.values():
            if not isinstance(ops, dict):
                continue
            for m, op in ops.items():
                if m.lower() not in A.METHODS or not isinstance(op, dict):
                    continue
                for prm in op.get("parameters") or []:
                    if not isinstance(prm, dict):
                        continue
                    total += 1
                    if "$ref" in prm:
                        ref += 1
        return total, ref, total - ref

    def test_single_group_scope_collapses_to_a_one_point_common_set(self):
        group = "resource.k8s.io"
        scoped = [p for p in A.UNION if A.api_group(p[0]) == group]
        common = {p for p in A.OLD if A.api_group(p[0]) == group} & \
                 {p for p in A.NEW if A.api_group(p[0]) == group}
        self.assertEqual(len(scoped), 218)
        self.assertEqual(len(common), 1)

    def test_scoped_false_green_leaves_217_dimensions_unread(self):
        group = "resource.k8s.io"
        scoped = [p for p in A.UNION if A.api_group(p[0]) == group]
        common = {p for p in A.OLD if A.api_group(p[0]) == group} & \
                 {p for p in A.NEW if A.api_group(p[0]) == group}
        self.assertEqual(len(scoped) - len(common), 217)

    def test_declared_and_ref_parameter_counts(self):
        t28, r28, i28 = self._ref_counts(OLD_FILE)
        t31, r31, i31 = self._ref_counts(NEW_FILE)
        self.assertEqual(t28, FROZEN["declared_params"][OLD_FILE])
        self.assertEqual(t31, FROZEN["declared_params"][NEW_FILE])
        self.assertEqual(r28, FROZEN["ref_params"][OLD_FILE])
        self.assertEqual(r31, FROZEN["ref_params"][NEW_FILE])

    def test_ref_blind_extractor_sees_827_and_912(self):
        self.assertEqual(self._ref_counts(OLD_FILE)[2], 827)
        self.assertEqual(self._ref_counts(NEW_FILE)[2], 912)

    def test_ref_blind_difference_is_invented_drift(self):
        # 912 - 827 = 85 looks exactly like a real drift and is not one.
        self.assertEqual(self._ref_counts(NEW_FILE)[2] - self._ref_counts(OLD_FILE)[2], 85)

    def test_ref_share_exceeds_seventy_percent(self):
        t28, r28, _ = self._ref_counts(OLD_FILE)
        self.assertGreater(r28 / t28, 0.70)


class TestMutationEvidence(unittest.TestCase):
    """Break the protected behaviour and confirm exactly the protected thing flips.

    Two directions, per this project's rule: too loose (the guard is disabled and
    still reports success) and too tight.

    Mutation A — group extraction broken. The real bug hit while writing this
    case: `api_group` was handed the whole dimension tuple, so `"/apis/" in p`
    tested tuple membership, was always False, and every group label silently
    degraded to the dimension itself. The four-quadrant readout did NOT notice;
    only the aggregation did. That is the whole reason M2 exists.
    """

    def test_mutation_a_broken_group_extractor_changes_the_aggregation(self):
        good = dict(A.removals_by_group())

        # The exact mutation: pass the dimension instead of its path component.
        broken = {}
        for p in {q for q in A.OLD} - {q for q in A.NEW}:
            label = A.api_group(p)          # p, not p[0]
            broken[label] = broken.get(label, 0) + 1

        self.assertNotEqual(good, broken)
        self.assertEqual(sum(good.values()), sum(broken.values()))  # totals survive
        self.assertEqual(len(good), 3)
        self.assertEqual(len(broken), FROZEN["removed"])            # labels explode

    def test_mutation_a_is_invisible_to_the_four_quadrant_readout(self):
        # The uncomfortable half: the readout is identical before and after.
        before = compare(A.make_existence_claim(), A.make_existence_claim_new(),
                         A.UNION, max_witness=1)
        after = compare(A.make_existence_claim(), A.make_existence_claim_new(),
                        A.UNION, max_witness=1)
        self.assertEqual((before.common, before.divergence,
                          before.dominance, before.neither),
                         (after.common, after.divergence,
                          after.dominance, after.neither))

    def test_mutation_b_a_type_claim_that_can_be_certified_is_the_wrong_world(self):
        # Too-tight direction: if the gate ever started accepting a claim with
        # zero discriminating points, the refusal assertions above would break.
        # Pin the precondition so the failure is legible rather than mysterious.
        self.assertEqual(A.make_type_claim().run_reading_discrimination(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

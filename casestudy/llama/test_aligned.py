"""Mutation evidence for aligned.py: break it and it must go red.

[Why this file has to exist]
A hard discipline of this project: a passing positive run proves nothing.
This case is especially dangerous because it **goes all green easily** —
the first version once read out "all_true 3/3 = 100%", a beautiful zero-information result,
with the tool raising no error at all. So "the readout shape itself" has to be pinned down.

It covers both directions of breakage:

| Direction | What is broken | Consequence if missed |
|---|---|---|
| too loose | verdict constantly true | readout all_true 100%, zero information, **disguised as a pass** |
| too tight | verdict constantly false | readout all_false, equally zero information |

How to run: python test_aligned.py
"""
import json
import os
import sys
import unittest

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

def _have_corpus():
    try:
        aligned.resolve_root(None)
        return True
    except SystemExit:
        return False


HAS_LLAMA = _have_corpus()
HAS_LEDGER = os.path.exists(aligned.LEDGER)

# ★ Without the corpus, run only the ledger and guard assertions, with an explicit reason —
#   silently skipping half the tests looks like "all green".
_SKIP_REASON = ("no llama.cpp corpus (three nightly builds) found.\n"
                "       Set BREAKINGDIFF_LLAMA_ROOT, "
                "or copy the llama-b* directories beside this script.")


# ============================================================
@unittest.skipUnless(HAS_LEDGER, "missing official_ledger.json")
class TestLedger(unittest.TestCase):
    """The ledger is the source of the Q account. If it breaks, everything after it breaks."""

    def test_ledger_has_all_three_builds(self):
        led = aligned.load_ledger()
        tags = {r["tag"] for r in led["releases"]}
        self.assertEqual(tags, set(aligned.BUILDS),
                         f"ledger build numbers do not match the parameter points: {tags}")

    def test_self_reported_sha_is_prefix_of_ledger_sha(self):
        """★ P6 external-anchor mechanical check: the artifact's self-reported commit
        must be a prefix of the official ledger sha. Not holding = mismatched attribution in the ledger."""
        for r in aligned.load_ledger()["releases"]:
            self.assertTrue(
                r["sha"].startswith(r["sha_self_reported"]),
                f'{r["tag"]}: self-reported {r["sha_self_reported"]} '
                f'is not a prefix of the ledger sha {r["sha"]}')

    def test_verbatim_is_actually_in_the_record(self):
        """Every entry in claims_verbatim must appear verbatim in body_details_verbatim.
        This stops the ledger from storing a summary as the original text."""
        for r in aligned.load_ledger()["releases"]:
            for c in r["claims_verbatim"]:
                self.assertIn(c, r["body_details_verbatim"],
                              f'{r["tag"]}: {c!r} is not in that record\'s source text')


# ============================================================
@unittest.skipUnless(HAS_LLAMA and HAS_LEDGER, _SKIP_REASON)
class TestBaseline(unittest.TestCase):
    """Baseline readout. ★ The numbers must be pinned, or the mutations below could be waved away with "the readout was always like that"."""

    def setUp(self):
        aligned.LLAMA_ROOT = aligned.resolve_root(None)
        self.claims = aligned.build_claims(aligned.load_ledger())
        self.r = aligned.run(self.claims)

    def test_there_is_an_outlier(self):
        """★ Core assertion: C3 must be read as an outlier.

        C3 = "template-analysis should not be removed without notice",
        and it is false on b11681. This is the only real finding of the case;
        not reading it out means the work was pointless."""
        self.assertTrue(self.r.outliers, f"expected at least one outlier, got {self.r.outliers}")
        idx = next(iter(self.r.outliers))
        self.assertEqual(self.r.names[idx],
                         "C3 template-analysis not removed")

    def test_ratchet_is_detected(self):
        """★ The ratchet must report a cross-version regression, and all of them must land on b11681.

        This matters more than the outlier: template-analysis is "present in the old version, dropped in the new one",
        and **adjacent pairwise diffs are blind to cross-version regressions** — only the chain check catches it.
        """
        self.assertGreater(self.r.ratchet_total, 0, "a ratchet violation should be reported")
        for _j, _k, at in self.r.ratchet_witnesses:
            self.assertEqual(at[0], "b11681",
                             f"ratchet violations should land on b11681, got {at}")

    def test_reading_is_not_degenerate(self):
        """★ Anti-degeneration assertion: the readout must not be all true.

        The first version was exactly the zero-information "all_true 3/3 = 100%", with the tool raising no error.
        This assertion keeps it from happening again."""
        self.assertLess(
            self.r.all_true, self.r.total,
            f"all_true {self.r.all_true}/{self.r.total} — the verdict degenerated into a tautology, "
            f"which is the fingerprint of a zero-information readout")

    def test_verdicts_actually_vary(self):
        """Print each account's verdict vector for a human check that it really varies.
        This is direct evidence that "the predicate reads x"."""
        varying = 0
        for c in self.claims:
            vs = [c.predicate(x) for x in aligned.CRITERIA]
            if len(set(vs)) > 1:
                varying += 1
        self.assertGreater(varying, 0,
                           "no account's verdict varies with the parameter point — "
                           "the predicate is not reading x and has degenerated into a constant")

    def test_c1_and_c2_are_not_outliers(self):
        """C1/C2 official statements hold, so they must not be read as outliers.
        If they became outliers too, the predicate construction has some other error."""
        outlier_names = {self.r.names[i] for i in self.r.outliers}
        self.assertNotIn("C1 server adds SLOTS_N_DIFF", outlier_names)
        self.assertNotIn("C2 MELLUM precision handling", outlier_names)


# ============================================================
@unittest.skipUnless(HAS_LLAMA and HAS_LEDGER, _SKIP_REASON)
class TestMutationTooLoose(unittest.TestCase):
    """The too-loose direction: verdict constantly true → readout all_true 100%, disguised as a pass."""

    def test_mut_1_predicate_ignores_x(self):
        """Mutation: the predicate closure does not mention x and always returns True.

        ★ Construction point: all three accounts must be **individually** constant true.
        I first wrote "all three equal the result of probe_template_analysis(b11681)",
        which happens to be False (exactly this case's real finding), so the readout came out all false —
        the test measured "all false" rather than "constantly true". A mutation must hit the direction it intends to test.
        """
        claims = [
            Claim(name=c.name, predicate=lambda x: True,
                  applies=lambda x: True, domain_note="m",
                  source="llama", quote="x", quote_source="x")
            for c in aligned.build_claims(aligned.load_ledger())
        ]
        r = aligned.run(claims)
        self.assertEqual(r.all_true, r.total,
                         "with a constantly-true predicate the readout should be all true — that is the degeneration to prevent")
        #★ and the ratchet must go to zero: if everything is constantly true there is no "present in the old, dropped in the new"
        self.assertEqual(r.ratchet_total, 0,
                         "an all-true readout should not report ratchet violations")

    def test_mut_2_evidence_always_true(self):
        """Mutation: replace the probes with a constant True (simulating a mis-written or broken probe)."""
        def broken(build):
            return True, "replaced with a constant true"
        claims = []
        for spec in aligned.CLAIMS:
            ev = broken
            at = spec["claimed_at"]

            def predicate(x, at=at, ev=ev):
                if at is None or x[0] >= at:
                    ok, _ = ev(x[0])
                    return ok
                return True
            claims.append(Claim(name=spec["name"], predicate=predicate,
                                applies=lambda x: True, domain_note="m",
                                source="llama", quote="x", quote_source="x"))
        r = aligned.run(claims)
        self.assertEqual(r.all_true, r.total,
                         "when the probes are constantly true the readout must be all true — otherwise a real gap would be hidden")

    def test_mut_3_reading_covers_nothing(self):
        """Mutation: applies constantly false → everything out of domain, a zero readout disguised as a pass."""
        claims = [
            Claim(name=c.name, predicate=lambda x: True,
                  applies=lambda x: False, domain_note="m",
                  source="llama", quote="x", quote_source="x")
            for c in aligned.build_claims(aligned.load_ledger())
        ]
        r = aligned.run(claims)
        self.assertEqual(r.total, 0, "with applies constantly false the comparison domain should be empty")
        # and coverage_guard must stop it
        from coverage_guard import require_covered, CoverageError
        with self.assertRaises(CoverageError):
            require_covered([c.name for c in claims], [], what="all accounts")


# ============================================================
@unittest.skipUnless(HAS_LLAMA and HAS_LEDGER, _SKIP_REASON)
class TestMutationTooTight(unittest.TestCase):
    """The too-tight direction: verdict constantly false → readout all_false, equally zero information."""

    def test_mut_4_predicate_always_false(self):
        """Mutation: predicate constantly false → all false, and the ratchet must expose the reverse direction."""
        claims = [
            Claim(name=c.name, predicate=lambda x: False,
                  applies=lambda x: True, domain_note="m",
                  source="llama", quote="x", quote_source="x")
            for c in aligned.build_claims(aligned.load_ledger())
        ]
        r = aligned.run(claims)
        self.assertEqual(r.all_false, r.total, "with a constantly-false predicate the readout should be all false")
        self.assertEqual(r.all_true, 0)

    def test_loose_and_tight_are_distinguishable(self):
        """★ Two-way assertion: too loose and too tight must give **different** readouts.

        Otherwise the verdict logic is insensitive to its input, and the "pretty readout" means nothing."""
        base = aligned.build_claims(aligned.load_ledger())
        loose = [Claim(name=c.name, predicate=lambda x, v=True: v,
                       applies=lambda x: True, domain_note="m",
                       source="llama", quote="x", quote_source="x")
                 for c in base]
        tight = [Claim(name=c.name, predicate=lambda x, v=False: v,
                       applies=lambda x: True, domain_note="m",
                       source="llama", quote="x", quote_source="x")
                 for c in base]
        rl = aligned.run(loose)
        rt = aligned.run(tight)
        self.assertNotEqual((rl.all_true, rl.all_false),
                            (rt.all_true, rt.all_false),
                            "loose and tight give the same readout → the verdict is insensitive to its input")


# ============================================================
@unittest.skipUnless(HAS_LLAMA, _SKIP_REASON)
class TestProvenance(unittest.TestCase):
    """The provenance gate: the Q account must come verbatim from the official notes."""

    def test_quote_mismatch_raises(self):
        led = aligned.load_ledger()
        verbatim = led["releases"][0]["body_details_verbatim"]
        with self.assertRaises(ProvenanceError):
            Claim(name="X", predicate=lambda x: True, applies=lambda x: True,
                  domain_note="m", source="github release",
                  quote="a sentence that is nowhere in the official notes",
                  quote_source=verbatim)

    def test_cross_tag_quote_raises(self):
        """★ A trap this case really hit: quoting another build's statement as this build's.

        C1 originally quoted the b10595 statement on b10472,
        and ProvenanceError was raised on the spot. This keeps it from coming back."""
        led = aligned.load_ledger()
        b10472 = next(r for r in led["releases"] if r["tag"] == "b10472")
        b10595 = next(r for r in led["releases"] if r["tag"] == "b10595")
        with self.assertRaises(ProvenanceError):
            Claim(name="X", predicate=lambda x: True, applies=lambda x: True,
                  domain_note="m", source="github release b10472",
                  quote=b10595["body_details_verbatim"],
                  quote_source=b10472["body_details_verbatim"])


# ============================================================
class TestNoDataGuard(unittest.TestCase):
    """★ When the ledger is missing the script must exit explicitly, never quietly produce an empty report."""

    def test_missing_ledger_exits_nonzero(self):
        saved = aligned.LEDGER
        try:
            aligned.LEDGER = os.path.join(_HERE, "__no_such__.json")
            with self.assertRaises(SystemExit):
                aligned.main()
        finally:
            aligned.LEDGER = saved

    def test_missing_probe_file_does_not_crash(self):
        """★ When a probe cannot find its file it must return False + an explanation, never raise.

        This is the second guard layer: the first is the ledger, the second is the evidence.
        A missing tool (the kind of trap `strings` was) must show up as "cannot measure",
        never as "the assertion is true"."""
        ghost = os.path.join(_HERE, "__no_such_dir__")
        saved = aligned.LLAMA_ROOT
        try:
            aligned.LLAMA_ROOT = ghost
            for probe in (aligned.probe_slots_n_diff,
                          aligned.probe_template_analysis):
                ok, detail = probe("b10472")
                self.assertFalse(ok, "when the file does not exist the probe must return False")
                self.assertTrue(detail, "it must give an explanation; it must not be silent")
        finally:
            aligned.LLAMA_ROOT = saved


@unittest.skipUnless(HAS_LLAMA and HAS_LEDGER, _SKIP_REASON)
class TestDegenerateFingerprint(unittest.TestCase):
    """★ Mechanical check of the degenerate-readout fingerprints.

    The quick-reference table in the teaching doc must be **measured**, never written from memory.
    This class pins the readout shapes of the four degenerations
    so the table in the docs cannot drift away from the code's actual behavior.

    ★ The most valuable item: the last two degenerations both show "all zero",
      and only total separates them. Reading the numbers with the naked eye treats two diseases as one.
    """

    def _shape(self, claims):
        return compare_n(claims, list(aligned.CRITERIA), chain=False)

    def _mk(self, **kw):
        base = aligned.build_claims(aligned.load_ledger())
        return [Claim(name=c.name, domain_note="m", source="llama",
                      quote="x", quote_source="x", **kw)
                for c in base]

    def test_fp1_predicate_always_true(self):
        """Predicate constantly true → all_true = total."""
        r = self._shape(self._mk(predicate=lambda x: True,
                                 applies=lambda x: True))
        self.assertEqual((r.all_true, r.total), (3, 3))

    def test_fp2_applies_always_false(self):
        """applies constantly false → all zero, with total = 0 (not a single point was compared)."""
        r = self._shape(self._mk(predicate=lambda x: True,
                                 applies=lambda x: False))
        self.assertEqual((r.all_true, r.all_false, r.total), (0, 0, 0))
        self.assertEqual(r.out_of_domain, len(aligned.CRITERIA))

    def test_fp3_mixed_quantity_splits_claims(self):
        """★ Mixed dimensions → all zero, but total > 0. That is the only difference from fp2."""
        import misaligned
        _rows, claims, r, vectors = misaligned.wrong_3_mixed_quantity()
        self.assertEqual((r.all_true, r.all_false), (0, 0),
                         "mixed dimensions should read out all zero")
        self.assertGreater(r.total, 0,
                           "★ Key: total > 0 — this is the only difference from applies constantly false "
                           "(total = 0)")
        # and every account's verdict vector is a constant
        for name, vec in vectors.items():
            self.assertEqual(len(set(vec)), 1,
                             f"{name}'s verdict vector {vec} is not constant, "
                             f"which means the mixed-dimension construction has changed")

    def test_fp2_and_fp3_are_distinguishable_only_by_total(self):
        """★ Combine the two above and pin them down: the shapes are nearly identical, only total separates them."""
        import misaligned
        r2 = self._shape(self._mk(predicate=lambda x: True,
                                  applies=lambda x: False))
        _r, claims3, r3, _v = misaligned.wrong_3_mixed_quantity()
        self.assertEqual(
            (r2.all_true, r2.all_false), (r3.all_true, r3.all_false),
            "both should show all zero")
        self.assertNotEqual(
            r2.total, r3.total,
            "★ total must separate them: 0 = nothing compared; 3 = compared but no region of agreement")


class TestNoPathLeak(unittest.TestCase):
    """★ Redaction guard: no local absolute path may appear in code or docs.

    This is not fussiness. The case study has to run after someone copies it elsewhere,
    and code carrying local paths can neither be copied nor avoid exposing the user's environment.
    So the discipline itself needs an assertion behind it, or it gets written back in while editing.
    """

    _ALLOWED = (
        # The upstream CI build path: it appears inside the official binaries and is public information.
        # Keeping it is **citing evidence**, not leaking.
        "D:/a/llama.cpp",
        "llama.cpp",
    )

    def test_no_local_absolute_paths(self):
        import re
        # drive-letter paths: C:\ ... / F:\ ... (both backslash and forward slash forms)
        pat = re.compile(r"[A-Za-z]:[\\/]{1,2}(?:Users|llama-setup|breakingdiff)")
        for fn in ("aligned.py", "misaligned.py", "test_aligned.py",
                   "official_ledger.json", "../TEACHING-llama.md"):
            p = os.path.join(_HERE, fn)
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    m = pat.search(line)
                    self.assertIsNone(
                        m, f"{fn}:{lineno} local absolute path found: {line.strip()[:80]}")

    def test_no_hardcoded_corpus_root(self):
        """The corpus root must come from the environment variable / command line / sibling directory; never hard-coded."""
        import re
        p = os.path.join(_HERE, "aligned.py")
        with open(p, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("BREAKINGDIFF_LLAMA_ROOT", src,
                      "the environment variable for the corpus root must be supported")
        self.assertNotRegex(src, r'LLAMA_ROOT\s*=\s*r?["\'][A-Za-z]:',
                            "LLAMA_ROOT must not hard-code an absolute path")

    def test_missing_root_exits_nonzero_with_guidance(self):
        """★ When the corpus cannot be found the script must exit explicitly and **tell the reader what to do**,
        never quietly produce an empty readout."""
        saved = aligned.LLAMA_ROOT
        here = aligned._HERE
        try:
            aligned.LLAMA_ROOT = ""
            aligned._HERE = os.path.join(here, "__no_such_dir__")
            with self.assertRaises(SystemExit) as cm:
                aligned.resolve_root(None)
            msg = str(cm.exception)
            for kw in ("BREAKINGDIFF_LLAMA_ROOT", "--llama-root"):
                self.assertIn(kw, msg,
                              f"the exit message must explain how to use {kw}")
            # ★ Added: it must also point at the automatic fetch path
            self.assertIn("fetch_corpus.py", msg,
                          "the exit message should point at fetch_corpus.py — "
                          "saying only \"not found\" without a way out is irresponsible")
        finally:
            aligned.LLAMA_ROOT = saved
            aligned._HERE = here

    def test_partial_corpus_explains_consequence_not_just_missing(self):
        """★ When the corpus is **incomplete**, the message must state which conclusion goes invalid.

        This comes from a real trap: after b10472/b10595 were deleted,
        the old message said only "corpus not found", while the actual situation was that b11681 had been found.
        Worse still — **the tool raises no error when builds are missing**: the readout goes from "1 missing out of 3 versions"
        to "1 missing out of 1 version", the outlier share goes 33% → 100%,
        and it still looks "normal". So the message must state the consequence.
        """
        import tempfile
        import shutil
        tmp = tempfile.mkdtemp(prefix="bd_partial_")
        try:
            # build only one build: simulate "only the latest is left"
            os.makedirs(os.path.join(tmp, f"llama-{aligned.BUILDS[-1]}"))
            saved_root, saved_here = aligned.LLAMA_ROOT, aligned._HERE
            try:
                aligned.LLAMA_ROOT = ""
                aligned._HERE = tmp
                with self.assertRaises(SystemExit) as cm:
                    aligned.resolve_root(None)
            finally:
                aligned.LLAMA_ROOT, aligned._HERE = saved_root, saved_here

            msg = str(cm.exception)
            self.assertIn("incomplete", msg,
                          "must distinguish \"no corpus at all\" from \"an incomplete corpus\"")
            for b in aligned.BUILDS[:-1]:
                self.assertIn(b, msg, f"must name the missing builds: {b}")
            self.assertIn("cross-version", msg,
                          "must state that missing builds invalidate the cross-version conclusion")
            self.assertIn("does not raise an error", msg,
                          "★ must point out that the tool will not error because of it — "
                          "that is exactly what makes it dangerous")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestPortability(unittest.TestCase):
    """★ Relocatability guard: the directory must still run after being moved.

    This discipline was forced by a real migration:
    the script used to hard-code `_ROOT = ../../..`, and moving it to a directory
    one level shallower immediately raised ModuleNotFoundError.
    And the last thing a case study can afford is "it will not run from another location" —
    the first thing a reader does is try it in a different place, and it dies on the first try.
    """

    _FILES = ("aligned.py", "misaligned.py", "test_aligned.py")

    def test_root_is_discovered_not_hardcoded(self):
        for fn in self._FILES:
            with open(os.path.join(_HERE, fn), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(
                src, r'_ROOT\s*=\s*os\.path\.abspath\(os\.path\.join\(_HERE,\s*"\.\.',
                f"{fn}: _ROOT must not hard-code a number of parent levels — moving the directory kills it")
            self.assertIn("_find_scripts_root", src,
                          f"{fn}: it should search upward for scripts/breakingdiff.py")

    def test_scripts_root_is_actually_resolved(self):
        self.assertTrue(
            os.path.isfile(os.path.join(aligned._ROOT, "scripts", "breakingdiff.py")),
            f"could not resolve scripts/breakingdiff.py, _ROOT={aligned._ROOT}")

    def test_missing_scripts_root_exits_with_guidance(self):
        """★ When it cannot be found the script must exit explicitly with the requirement, not raise a bare ModuleNotFoundError."""
        import shutil
        import tempfile

        # ★ The construction point must be **outside the repository**: under this directory,
        #   walking up a few levels would still hit scripts/, and the assertion would become a false green.
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
            shutil.rmtree(tmp, ignore_errors=True)


class TestCorpusManifest(unittest.TestCase):
    """★ Discipline for the artifact-side ledger.

    The Q account (official statements) is pinned in official_ledger.json;
    but the **artifact-side** facts — what each build has, how big it is, what the probes read —
    used to live only in my chat log. That is not good enough: the reader cannot check it.

    Hence corpus_manifest.json. Two disciplines:
      1) the ledger must not become "a record that never changes and may be out of date"
         → fetch_corpus.py --manifest can rescan and overwrite it
      2) the ledger **must not replace re-running the probes**
         → a missing corpus must say "cannot re-run", never take the ledger's place
    """

    MANIFEST = os.path.join(_HERE, "corpus_manifest.json")

    def _man(self):
        with open(self.MANIFEST, encoding="utf-8") as f:
            return json.load(f)

    def test_manifest_exists_and_covers_all_builds(self):
        man = self._man()
        for tag in aligned.BUILDS:
            self.assertIn(tag, man["builds"],
                          f"the ledger must cover {tag} — without it readout consistency cannot be checked")

    def test_manifest_asset_names_match_ledger_tags(self):
        """★ Asset names in the ledger must match the tags in official_ledger.

        A mismatch = downloading from a URL that does not exist.
        """
        man = self._man()
        for tag in aligned.BUILDS:
            self.assertIn(tag, man["asset_pins"],
                          f"asset_pins is missing {tag}")
            self.assertIn(tag, man["builds"])

    def test_manifest_records_actual_cuda_minor_not_vague(self):
        """★ Asset names must carry the real minor version (cuda-13.3 / 13.4), never a vague "CUDA 13".

        This came out of measurement: b10472/b10595 are 13.3, b11681 is 13.4.
        A vague record makes later readers assume all three builds use the same asset,
        so they fetch the wrong file — and a failed download usually looks like a "network problem", hard to trace back here.
        """
        man = self._man()
        minors = set()
        for tag, entry in man["asset_pins"].items():
            if tag.startswith("_"):
                continue
            name = entry["used_asset"]
            self.assertRegex(name, r"win-cuda-\d+\.\d+-x64\.zip$",
                             f"{tag}'s asset name should contain the cuda minor version, actual: {name}")
            minors.add(name.split("cuda-")[1].split("-")[0])
        self.assertGreater(
            len(minors), 1,
            "★ The three builds' CUDA minor versions should differ. If they are the same, "
            "the ledger has flattened the version and later readers will fetch the wrong asset.")

    def test_manifest_states_honesty_boundary(self):
        """★ The ledger must state of itself that it "cannot replace re-running the probes"."""
        man = self._man()
        blob = json.dumps(man, ensure_ascii=False)
        self.assertIn("cannot replace re-running the probes", blob,
                      "the ledger must say it is only a measured record, not the evidence itself")

    def test_manifest_records_corpus_state_truthfully(self):
        """★ The corpus state must be recorded truthfully, not worked around.

        This maps directly onto what recently happened in this case: b10472/b10595 were deleted.
        state/missing/impact must be self-consistent —
        especially impact, which must say **the cross-version conclusion cannot be re-run**,
        because with only one build left the readout merely shrinks and raises no error.
        """
        man = self._man()
        cs = man["corpus_status"]
        state = cs["state"]
        self.assertIn(state, ("COMPLETE", "PARTIAL"),
                      f"state may only be COMPLETE/PARTIAL, got {state}")
        if state == "COMPLETE":
            self.assertEqual(cs["missing"], [])
        else:
            self.assertTrue(cs["missing"], "when PARTIAL, missing must not be empty")
            self.assertIn("cross-version", cs["impact"],
                          "when PARTIAL, impact must state the effect on the cross-version conclusion")
        # the on_disk marker must not contradict state
        on_disk = [t for t in man["builds"] if man["builds"][t].get("on_disk")]
        self.assertEqual(
            sorted(on_disk), sorted(cs["present"]),
            "each build's on_disk marker must agree with corpus_status.present")

    def test_manifest_verdict_vectors_match_probe_semantics(self):
        """★ The C3 readout in the ledger must match the direction of the "disappeared" finding.

        This does not re-run the probe (the corpus may be absent); it pins **internal consistency of the ledger**:
        the core finding says b11681 lacks template-analysis,
        so in the ledger b11681's C3 must be false and the other two must be true.
        """
        man = self._man()
        b = man["builds"]
        latest = aligned.BUILDS[-1]
        oldest = aligned.BUILDS[0]
        self.assertFalse(
            b[latest]["verdict_vector"]["C3"],
            f"{latest}'s C3 should be False (template-analysis has disappeared)")
        for tag in aligned.BUILDS[:-1]:
            self.assertTrue(
                b[tag]["verdict_vector"]["C3"],
                f"{tag}'s C3 should be True (that build still contains template-analysis)")

    def test_fetch_script_is_importable_and_guards_missing_tag(self):
        """★ The fetch script must refuse explicitly when the build number changes, instead of assembling an asset name itself."""
        import fetch_corpus
        with self.assertRaises(SystemExit) as cm:
            fetch_corpus.asset_name("b99999", "cuda")
        msg = str(cm.exception)
        self.assertIn("asset_pins", msg,
                      "when the build number changes it must point at the ledger entry to add")

    def test_verify_all_reports_missing_loudly(self):
        """★ When the corpus is incomplete it must exit explicitly and state the consequence."""
        import tempfile
        import fetch_corpus
        tmp = tempfile.mkdtemp(prefix="bd_corpus_")
        try:
            self.assertFalse(
                fetch_corpus.verify_all(tmp),
                "an empty directory should count as an incomplete corpus")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Red-end tests for the malecns strength-layer case: assert aligned.py / misaligned.py /
fetch_corpus.py / corpus_manifest.json (source of the criteria: strength-layer plan 2026-10-20).

[Red-state convention (following B6 dist_layout_test)]
When the implementation-side deliverable is absent, this file must still run and exit 2 (runtime error: implementation
not delivered), never silently go green. The lazy _impl() puts "module does not exist" in the runtime-error layer
(ERROR → exit 2), separate from an assertion red for "it ran but the behavior is wrong" (FAIL → exit 1). When the
corpus has not been downloaded, all corpus-related classes skip with a trace (the llama convention); manifest/fetch
assertions are unaffected by the missing corpus — they are in-repo static deliverables, and absence is the red state itself.

[Data facts (measured independently on 2026-10-20; static release, unchanged once hash-anchored)]
Both feathers are ARROW1 (Feather V2). pyarrow can read the annotation table directly; for the transmitter table
pyarrow/pandas report "Lz4 compressed input contains more than one frame" and polars reports flatbuffer InvalidOffset —
its lz4 frames are block-dependent (FLG bit5=0) and one buffer holds several frames, a known read-path trap of this
case, so the implementation must decode it itself (frame-by-frame splitting + block-dependent decoding works, proven).
Therefore the transmitter-side readout can only be reconciled through the implementation, while the annotation-side
readout is backed by an independent pyarrow recomputation in this file.

[Frozen accounts]
Domain = (type, side) points where the annotation-table type is non-empty, somaSide ∈ {L, R}, and count > 0, sorted.
somaSide takes L/R/M/missing; M (392 bodies) and the missing side stay out of the domain —
P2 symmetry is defined only for L/R. Q = existence baseline (an always-true anchor on the domain). The three band
accounts (P1 count band / P2 hemisphere symmetry band / P3 transmitter composition band) are constructed by the
implementation from "the data's self-reported distribution + literature feel"; this file only pins the shape:
not constantly true (the band must narrow down to a readout), not constantly false, and failure points landing on
real data points.
P3's two accounts: neuron-level majority vote (predicted_nt votes per body, unclear counts, a tie takes the
lexicographically largest — 136 measured tied types make that rule discriminating: min rule 111 types disagree /
max rule 138) vs the data's self-reported celltype_predicted_nt (unique within a type, measured 0 types with
multiple values). Share denominator = the number of members of that type that have a transmitter row.

How to run: python test_aligned.py   (exit code 0 pass / 1 assertion red / 2 runtime error)
"""
import hashlib
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


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

FEATHER_ANNOT = "body-annotations-male-cns-v0.9-minconf-0.5.feather"
FEATHER_NT = "body-neurotransmitters-male-cns-v0.9.feather"
MANIFEST = os.path.join(_HERE, "corpus_manifest.json")
HAS_CORPUS = (os.path.isfile(os.path.join(_HERE, FEATHER_ANNOT))
              and os.path.isfile(os.path.join(_HERE, FEATHER_NT)))

# ---- corpus anchors (measured on this machine with a 4 MB chunked SHA256 stream, 2026-10-20;
#      the single downloader's on-disk file was checked against full-parse statistics afterwards.
#      Hashing mid-download captures an incomplete state) ----
ANNOT_SHA256 = "03cca8d1e667353f75f7674fb7d6b3a9e22e5b04b089865127407a5c38816cda"
NT_SHA256 = "93f436ed5ac29787c485907ba1aa2ca85213929a485466c46da034cd676fbbeb"
ANNOT_BYTES = 12900778
NT_BYTES = 43403618
ANNOT_ROWS = 211743
NT_ROWS = 1836293

# ---- annotation-table statistics (measured independently with pyarrow; recomputable inside the test) ----
SIDE_COUNTS = {"L": 75370, "R": 75233, "M": 392, None: 60748}
N_TYPES = 11732            # unique types with non-empty type
N_TYPES_LR = 11235         # types with ≥1 L/R body
DOMAIN_SIZE = 22176        # existing (type, {L,R}) points
ONE_SIDED_TYPES = 294      # types occupying one side only
ASYM_TWO_SIDED = 2030      # types with both sides and L≠R
W2_FAIL_POINTS = 4354      # false-red points of left-right strict equality on the domain (two-sided types×2 + one-sided types×1)
MAX_ASYM_TYPE = "KCab-s"   # L=234 R=423, |L-R|=189
MAX_ASYM_LEFT = 234
MAX_ASYM_RIGHT = 423
MAX_ASYM = 189
W1_FAIL = 2720             # false-red points of the point-value claim (n0 = type total body count // 2, including M/side-less)
W1_PASS = 19456
W3_FAIL_POINTS = 241       # false-red points of neuron-level top-1 written as type-level
VOTE_VS_CELLTYPE_TYPES = 138   # types where the majority vote ≠ celltype_predicted_nt (tie=max rule)
VOTE_SHARE_SUBHALF_TYPES = 16  # types whose main transmitter share < 0.5 (tie-independent)

# ---- cell-by-cell readout anchors (representative types; share denominator = the type's members with a transmitter row) ----
REP_KCAB = ("KCab-s", 234, 423, "dopamine", 656, 657, "dopamine")
REP_R1R6 = ("R1-R6", 4, 9, "unclear", 2627, 3377, "histamine")

# ---- the frozen face of corpus_manifest.json readings ----
READINGS = {
    "domain_size": DOMAIN_SIZE,
    "types": N_TYPES_LR,
    "one_sided_types": ONE_SIDED_TYPES,
    "asym_two_sided_types": ASYM_TWO_SIDED,
    "wrong1_fail": W1_FAIL,
    "wrong2_fail": W2_FAIL_POINTS,
    "wrong3_fail": W3_FAIL_POINTS,
    "vote_vs_celltype_types": VOTE_VS_CELLTYPE_TYPES,
    "vote_share_subhalf_types": VOTE_SHARE_SUBHALF_TYPES,
    "max_asym_type": MAX_ASYM_TYPE,
    "max_asym_left": MAX_ASYM_LEFT,
    "max_asym_right": MAX_ASYM_RIGHT,
    "max_asym": MAX_ASYM,
}


class ImplMissing(RuntimeError):
    """The implementation-side deliverable is absent — runtime-error layer (exit code 2), not an assertion red."""


_IMPL_CACHE = {}


def _impl(name):
    """Lazily load the implementation module. When absent, raise ImplMissing: the red-end file must run and triage,
    never blow up into a bare traceback at the import line (that would read as an exit-code-1 assertion red)."""
    if name not in _IMPL_CACHE:
        path = os.path.join(_HERE, name + ".py")
        if not os.path.isfile(path):
            raise ImplMissing(
                f"[malecns_test] runtime error: casestudy/malecns/{name}.py does not exist "
                "(implementation not delivered?), so this case cannot run")
        _IMPL_CACHE[name] = __import__(name)
    return _IMPL_CACHE[name]


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_annot_columns():
    """Read the annotation table directly with pyarrow; return three lists (bodyId, type, somaSide)."""
    try:
        import pyarrow.feather as feather
    except ImportError as e:
        raise RuntimeError(
            "[malecns_test] runtime error: corpus present but pyarrow unavailable — cannot read the annotation table "
            f"({e!r})") from e
    t = feather.read_table(os.path.join(_HERE, FEATHER_ANNOT))
    return (t.column("bodyId").to_pylist(), t.column("type").to_pylist(),
            t.column("somaSide").to_pylist())


def _recompute_domain_facts():
    """Test-side independent recomputation of the domain facts (through no implementation code); returns
    (counts, per_type_total, domain, one_sided, asym_two_sided)."""
    body_ids, types, sides = _load_annot_columns()
    cs = {}
    for t, s in zip(types, sides):
        if t is None or not str(t).strip():
            continue
        key = (str(t), str(s))
        cs[key] = cs.get(key, 0) + 1
    per_type_total = {}
    for (t, s), n in cs.items():
        per_type_total[t] = per_type_total.get(t, 0) + n
    counts = {(t, s): n for (t, s), n in cs.items()
              if s in ("L", "R") and n > 0}
    one_sided = [t for t in per_type_total
                 if (cs.get((t, "L"), 0) == 0) != (cs.get((t, "R"), 0) == 0)]
    asym = {t for (t, _s) in counts
            if cs.get((t, "L"), 0) and cs.get((t, "R"), 0)
            and cs[(t, "L")] != cs[(t, "R")]}
    return counts, per_type_total, sorted(counts), set(one_sided), asym


_SKIP_CORPUS = ("missing MaleCNS v0.9 corpus (both feathers).\n"
                "       Run python fetch_corpus.py first to download it into this directory; "
                "for the transmitter table's read-path trap see the file head.")


def _man():
    if not os.path.isfile(MANIFEST):
        raise ImplMissing(
            "[malecns_test] runtime error: corpus_manifest.json does not exist "
            "(implementation not delivered?) — it is written by fetch_corpus.py and is the in-repo anchor "
            "for the readout table; without it no readout reconciliation is possible")
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
class TestFetchAndManifest(unittest.TestCase):
    """fetch_corpus.py and corpus_manifest.json: in-repo static deliverables whose absence
    is the runtime-error red state itself (independent of whether the corpus was downloaded)."""

    def test_fetch_corpus_exists(self):
        _impl("fetch_corpus")

    def test_default_targets_are_exactly_two_feathers(self):
        """The default download set must be exactly the two feathers — the 2.7 GB tbar table
        (tbar-neurotransmitters-male-cns-v0.9.feather) is barred from the default."""
        fc = _impl("fetch_corpus")
        targets = sorted(fc.DEFAULT_TARGETS)
        self.assertEqual(targets, sorted((FEATHER_ANNOT, FEATHER_NT)),
                         f"[malecns_test] the default download set should be exactly the two feathers, got {targets}")
        blob = json.dumps(targets)
        self.assertNotIn("tbar", blob,
                         "[malecns_test] the default download set must not include a tbar-level 2.7 GB table")

    def test_manifest_four_keys(self):
        cs = _man()["corpus_status"]
        for k in ("state", "missing", "impact", "how"):
            self.assertIn(k, cs, f"[malecns_test] corpus_status is missing {k} — the four-field discipline is incomplete")
        state = cs["state"]
        self.assertIn(state, ("COMPLETE", "PARTIAL"),
                      f"[malecns_test] state may only be COMPLETE/PARTIAL, got {state!r}")
        if state == "COMPLETE":
            self.assertEqual(cs["missing"], [],
                             "[malecns_test] when COMPLETE, missing must be empty")
        else:
            self.assertTrue(cs["missing"],
                            "[malecns_test] when PARTIAL, missing must not be empty")
            self.assertTrue(cs["impact"],
                            "[malecns_test] when PARTIAL, impact must state which conclusions are invalid")
        self.assertTrue(cs["how"],
                        "[malecns_test] how must state the way to restore the corpus")

    def test_manifest_sha256_anchors_match_measured(self):
        """Corpus anchors: a static release's hash does not change, so the measured values are written into the assertion."""
        files = _man()["files"]
        for fn, sha, nbytes, rows in (
                (FEATHER_ANNOT, ANNOT_SHA256, ANNOT_BYTES, ANNOT_ROWS),
                (FEATHER_NT, NT_SHA256, NT_BYTES, NT_ROWS)):
            self.assertIn(fn, files, f"[malecns_test] manifest.files is missing {fn}")
            ent = files[fn]
            self.assertEqual(ent["sha256"], sha,
                             f"[malecns_test] {fn}'s sha256 anchor does not match: manifest "
                             f"{ent['sha256']!r} vs measured {sha!r}")
            self.assertEqual(ent["bytes"], nbytes,
                             f"[malecns_test] {fn} byte count does not match: got {ent['bytes']}")
            self.assertEqual(ent["rows"], rows,
                             f"[malecns_test] {fn} row count does not match: got {ent['rows']}")

    def test_manifest_readings_match_measured(self):
        """The readout table goes into the repository: the small aggregate table is reconciled cell by cell against the measured constants."""
        readings = _man()["readings"]
        for k, want in READINGS.items():
            self.assertIn(k, readings, f"[malecns_test] readings is missing {k}")
            self.assertEqual(readings[k], want,
                             f"[malecns_test] readings.{k} got {readings[k]!r}, "
                             f"measured {want!r}")

    @unittest.skipUnless(HAS_CORPUS, _SKIP_CORPUS)
    def test_sha256_file_helper_agrees_with_hashlib(self):
        fc = _impl("fetch_corpus")
        for fn, sha in ((FEATHER_ANNOT, ANNOT_SHA256), (FEATHER_NT, NT_SHA256)):
            got = fc.sha256_file(os.path.join(_HERE, fn))
            self.assertEqual(got, sha,
                             f"[malecns_test] fetch_corpus.sha256_file({fn}) "
                             f"got {got!r}, chunked hashlib measured {sha!r}")


# ============================================================
@unittest.skipUnless(HAS_CORPUS, _SKIP_CORPUS)
class TestCorpusAnchors(unittest.TestCase):
    """Corpus anchors: the test recomputes with pyarrow/hashlib directly, through no implementation code."""

    def test_annotation_rows_and_required_columns(self):
        import pyarrow.feather as feather
        t = feather.read_table(os.path.join(_HERE, FEATHER_ANNOT))
        self.assertEqual(t.num_rows, ANNOT_ROWS,
                         f"[malecns_test] annotation table row count got {t.num_rows}")
        for col in ("bodyId", "type", "somaSide", "class", "status"):
            self.assertIn(col, t.column_names,
                          f"[malecns_test] annotation table is missing column {col}")

    def test_both_files_sha256_chunked(self):
        for fn, sha in ((FEATHER_ANNOT, ANNOT_SHA256), (FEATHER_NT, NT_SHA256)):
            got = _sha256_file(os.path.join(_HERE, fn))
            self.assertEqual(got, sha,
                             f"[malecns_test] {fn} chunked SHA256 got {got!r}")

    def test_annotation_side_value_distribution(self):
        _, _, sides = _load_annot_columns()
        got = {}
        for s in sides:
            got[s] = got.get(s, 0) + 1
        self.assertEqual(got, SIDE_COUNTS,
                         f"[malecns_test] somaSide distribution got {got}, measured {SIDE_COUNTS}")

    def test_domain_facts_recomputed(self):
        counts, per_type_total, domain, one_sided, asym = _recompute_domain_facts()
        self.assertEqual(len(per_type_total), N_TYPES,
                         f"[malecns_test] unique type count got {len(per_type_total)}")
        self.assertEqual(len(domain), DOMAIN_SIZE,
                         f"[malecns_test] domain point count got {len(domain)}")
        self.assertEqual(len(one_sided), ONE_SIDED_TYPES,
                         f"[malecns_test] one-sided type count got {len(one_sided)}")
        self.assertEqual(len(asym), ASYM_TWO_SIDED,
                         f"[malecns_test] two-sided asymmetric type count got {len(asym)}")
        hard_equal_fail = 0
        for (t, s) in domain:
            other = counts.get((t, "R" if s == "L" else "L"), 0)
            if counts[(t, s)] != other:
                hard_equal_fail += 1
        self.assertEqual(hard_equal_fail, W2_FAIL_POINTS,
                         f"[malecns_test] left-right strict-equality false-red points got {hard_equal_fail}")
        mx = max(asym, key=lambda t: (abs(counts[(t, "L")] - counts[(t, "R")]), t))
        d = abs(counts[(mx, "L")] - counts[(mx, "R")])
        self.assertEqual((mx, counts[(mx, "L")], counts[(mx, "R")], d),
                         (MAX_ASYM_TYPE, MAX_ASYM_LEFT, MAX_ASYM_RIGHT, MAX_ASYM),
                         f"[malecns_test] maximum asymmetry got {mx} "
                         f"L={counts[(mx, 'L')]} R={counts[(mx, 'R')]} |Δ|={d}")

    def test_nt_file_size_and_annot_w1_fails(self):
        """The transmitter table can only be read for its byte count directly (read-path trap, see the file head);
        the row-count anchor is in the manifest. The point-value claim's false-red surface is on the annotation side
        and can be recomputed independently."""
        self.assertEqual(os.path.getsize(os.path.join(_HERE, FEATHER_NT)), NT_BYTES,
                         "[malecns_test] transmitter table byte count does not match the measurement")
        counts, per_type_total, domain, _one, _a = _recompute_domain_facts()
        w1_fail = sum(1 for (t, s) in domain
                      if counts[(t, s)] != per_type_total[t] // 2)
        self.assertEqual(w1_fail, W1_FAIL,
                         f"[malecns_test] point-value claim false-red points got {w1_fail}")


# ============================================================
@unittest.skipUnless(HAS_CORPUS, _SKIP_CORPUS)
class TestAlignedInvariants(unittest.TestCase):
    """The readout shape of aligned.run(): on real data the bounded accounts must narrow down to a readout,
    and must not read the whole dataset red. Implementation absent → _impl raises ImplMissing (exit 2)."""

    def _run(self):
        aligned = _impl("aligned")
        claims, r = aligned.run()
        return aligned, claims, r

    def test_run_shape(self):
        aligned, claims, r = self._run()
        self.assertEqual(len(claims), 4,
                         f"[malecns_test] should be exactly 4 accounts (P1/P2/P3/Q), got {len(claims)}")
        prefixes = {c.name.split()[0] for c in claims}
        self.assertEqual(prefixes, {"P1", "P2", "P3", "Q"},
                         f"[malecns_test] account-name prefixes should include P1/P2/P3/Q, got {prefixes}")
        self.assertEqual(r.total, DOMAIN_SIZE,
                         f"[malecns_test] comparison domain point count got {r.total}")
        self.assertEqual(r.out_of_domain, 0,
                         f"[malecns_test] out-of-domain skips should be all 0 (domain = existence points), got {r.out_of_domain}")
        self.assertEqual(r.all_false, 0,
                         f"[malecns_test] all_false should be 0 — reading the whole true dataset red "
                         f"is the false-red disease, got {r.all_false}")
        self.assertLess(r.all_true, r.total,
                        f"[malecns_test] all_true {r.all_true}/{r.total} — the bounded accounts let everything through, "
                        "a zero-information decorative band")

    def test_q_existence_baseline_holds(self):
        aligned, claims, _r = self._run()
        qi = next(i for i, c in enumerate(claims) if c.name.split()[0] == "Q")
        q = claims[qi]
        bad = [x for x in aligned.CRITERIA if not q.predicate(x)]
        self.assertEqual(bad, [],
                         f"[malecns_test] the existence baseline Q must be always true on its own domain, "
                         f"failing witnesses {bad[:3]}")

    def test_p2_symmetry_band_binds(self):
        """P2 must narrow down to a readout: measured 2,030 two-sided types with L≠R, maximum |L-R|=189
        (KCab-s L=234/R=423), so any band between strict equality and infinite tolerance should flag points here.
        Failure points must land on genuinely asymmetric data points — that is the material for "per-type strict equality is real drift"."""
        aligned, claims, _r = self._run()
        counts, _pt, _dom, _one, _asym = _recompute_domain_facts()
        asym_points = set()
        for (t, s) in counts:
            other = counts.get((t, "R" if s == "L" else "L"), 0)
            if counts[(t, s)] != other:
                asym_points.add((t, s))
        p2i = next(i for i, c in enumerate(claims) if c.name.split()[0] == "P2")
        p2 = claims[p2i]
        fails = [x for x in aligned.CRITERIA if not p2.predicate(x)]
        self.assertTrue(fails,
                        "[malecns_test] the P2 hemisphere symmetry band lets everything through on real data — "
                        "measured 2,030 two-sided types with unequal sides, maximum |L-R|=189, "
                        "the band should narrow down to at least 1 point, got 0")
        outside = [x for x in fails if x not in asym_points]
        self.assertEqual(outside, [],
                         f"[malecns_test] P2's failure points must land on types whose left and right differ, "
                         f"out-of-band witnesses {outside[:3]}")

    def test_bands_do_not_reject_everything(self):
        aligned, claims, _r = self._run()
        for tag in ("P1", "P2", "P3"):
            ci = next(i for i, c in enumerate(claims) if c.name.split()[0] == tag)
            c = claims[ci]
            n_true = sum(1 for x in aligned.CRITERIA if c.predicate(x))
            self.assertGreater(n_true, 0,
                               f"[malecns_test] {tag} rejects the whole dataset "
                               f"(0/{DOMAIN_SIZE} pass) — the band is not built right")


# ============================================================
@unittest.skipUnless(HAS_CORPUS, _SKIP_CORPUS)
class TestMisalignedFingerprints(unittest.TestCase):
    """The degeneration fingerprints of the three error modes, named one by one. misaligned.wrong_*() returns
    (claims, r): exactly two accounts, claims[1] being the existence baseline Q (name starts with Q),
    compare_n(claims, aligned.CRITERIA, chain=False). Under N=2 the points where everything else is true and
    it alone is false land in pioneers[the Q index] — exactly the size of the false-red surface."""

    def _finger(self, fn, want_total, want_pass, want_fail):
        mis = _impl("misaligned")
        claims, r = fn()
        self.assertEqual(len(claims), 2,
                         f"[malecns_test] {fn.__name__} should have exactly two accounts (error mode + Q), "
                         f"got {len(claims)}")
        self.assertTrue(r.names[1].startswith("Q"),
                        f"[malecns_test] {fn.__name__} claims[1] should be the existence baseline Q, "
                        f"got {r.names[1]!r}")
        self.assertEqual((r.total, r.all_true, r.all_false, r.split),
                         (want_total, want_pass, 0, 0),
                         f"[malecns_test] {fn.__name__} readout shape got "
                         f"(total={r.total}, all_true={r.all_true}, "
                         f"all_false={r.all_false}, split={r.split})")
        self.assertEqual(r.out_of_domain, 0,
                         f"[malecns_test] {fn.__name__} out_of_domain should be all 0")
        self.assertEqual(r.outliers, {},
                         f"[malecns_test] {fn.__name__} under N=2 there should be no outlier attribution, "
                         f"got {r.outliers}")
        self.assertEqual(r.pioneers, {1: want_fail},
                         f"[malecns_test] {fn.__name__} false-red surface got {r.pioneers}, "
                         f"should be {{Q index: {want_fail}}}")
        return r

    def test_wrong1_point_value_false_red(self):
        """Error mode ① point-value claim: at each point assert n = type total body count // 2. Individual variation +
        a missing side make 2,720/22,176 true data points go red — true data looks like bad data."""
        self._finger(_impl("misaligned").wrong_1_point_value,
                     DOMAIN_SIZE, W1_PASS, W1_FAIL)

    def test_wrong2_hard_symmetry_false_red(self):
        """Error mode ② left-right strict equality: 4,354/22,176 points go red — real hemisphere asymmetry
        (maximum |L-R|=189) treated as bad data. Much larger than the P2 band's narrowing surface;
        that is the control group for "bounded is the right strength"."""
        self._finger(_impl("misaligned").wrong_2_hard_symmetry,
                     DOMAIN_SIZE, DOMAIN_SIZE - W2_FAIL_POINTS, W2_FAIL_POINTS)

    def test_wrong3_nt_top1_as_type_level_false_red(self):
        """Error mode ③ neuron-level top-1 written as type-level: the majority vote (unclear counts, a tie takes the
        lexicographically largest) disagrees with the data's self-reported celltype_predicted_nt on 138 types,
        and 241 domain points go red — account confusion, outlier."""
        self._finger(_impl("misaligned").wrong_3_nt_top1_as_type_level,
                     DOMAIN_SIZE, DOMAIN_SIZE - W3_FAIL_POINTS, W3_FAIL_POINTS)

    def test_three_false_reds_are_distinct_and_anchored(self):
        """The three false-red surfaces are pairwise unequal and reconcile with the manifest's readout table —
        the "point value < strict equality < bounded" strength staircase must be mechanically recomputable."""
        mis = _impl("misaligned")
        readings = _man()["readings"]
        got = {}
        for tag, fn in (("wrong1_fail", mis.wrong_1_point_value),
                        ("wrong2_fail", mis.wrong_2_hard_symmetry),
                        ("wrong3_fail", mis.wrong_3_nt_top1_as_type_level)):
            _claims, r = fn()
            got[tag] = sum(r.pioneers.values())
        self.assertEqual(got["wrong1_fail"], readings["wrong1_fail"],
                         "[malecns_test] error mode ①'s false-red surface does not match the manifest readout table")
        self.assertEqual(got["wrong2_fail"], readings["wrong2_fail"],
                         "[malecns_test] error mode ②'s false-red surface does not match the manifest readout table")
        self.assertEqual(got["wrong3_fail"], readings["wrong3_fail"],
                         "[malecns_test] error mode ③'s false-red surface does not match the manifest readout table")
        self.assertLess(got["wrong3_fail"], got["wrong1_fail"],
                        "[malecns_test] account confusion's false-red surface should be smaller than the point-value claim, "
                        f"got {got}")
        self.assertLess(got["wrong1_fail"], got["wrong2_fail"],
                        "[malecns_test] the point-value claim's false-red surface should be smaller than left-right strict equality, "
                        f"got {got}")


# ============================================================
@unittest.skipUnless(HAS_CORPUS, _SKIP_CORPUS)
class TestReadingTable(unittest.TestCase):
    """Cell-by-cell reconciliation of the readout table: the annotation side is fully recomputed by the test;
    the transmitter side has a read-path trap (see the file head), so it is reconciled through the implementation
    with manifest readings as the in-repo anchor."""

    def test_load_counts_matches_corpus_exactly(self):
        aligned = _impl("aligned")
        counts, _pt, _dom, _one, _a = _recompute_domain_facts()
        got = aligned.load_counts()
        self.assertEqual(got, counts,
                         "[malecns_test] aligned.load_counts() does not match the test-side full recomputation "
                         f"({len(got)} vs {len(counts)} entries) — cell-by-cell reconciliation failed")

    def test_representative_cells(self):
        aligned = _impl("aligned")
        counts = aligned.load_counts()
        tag, l, r_, _vm, _vn, _dn, _ct = REP_KCAB
        self.assertEqual((counts[(tag, "L")], counts[(tag, "R")]), (l, r_),
                         f"[malecns_test] {tag} left/right counts got "
                         f"{counts[(tag, 'L')]}/{counts[(tag, 'R')]}")
        tag, l, r_, _vm, _vn, _dn, _ct = REP_R1R6
        self.assertEqual((counts[(tag, "L")], counts[(tag, "R")]), (l, r_),
                         f"[malecns_test] {tag} left/right counts got "
                         f"{counts[(tag, 'L')]}/{counts[(tag, 'R')]}")

    def test_load_nt_fractions_matches_anchors(self):
        """Share denominator = the type's members with a transmitter row; a tie takes the lexicographically largest;
        unclear counts. R1-R6 is the best witness of account confusion: the neuron-level majority vote is unclear,
        while the data self-reports histamine (photoreceptors are histaminergic to begin with)."""
        aligned = _impl("aligned")
        fr = aligned.load_nt_fractions()
        for tag, _l, _r, vm, vn, dn, ct in (REP_KCAB, REP_R1R6):
            self.assertIn(tag, fr, f"[malecns_test] load_nt_fractions is missing {tag}")
            got = fr[tag]
            self.assertEqual(got[0], vm,
                             f"[malecns_test] {tag} voted main transmitter got {got[0]!r}")
            self.assertAlmostEqual(got[1], vn / dn, places=9,
                                   msg=f"[malecns_test] {tag} main transmitter share got "
                                       f"{got[1]!r}, should be {vn}/{dn}")
            self.assertEqual(got[2], ct,
                             f"[malecns_test] {tag} data self-reported type-level transmitter got {got[2]!r}")

    def test_nt_reading_counts_match_manifest(self):
        aligned = _impl("aligned")
        fr = aligned.load_nt_fractions()
        disagree = sum(1 for v in fr.values() if v[0] != v[2])
        subhalf = sum(1 for v in fr.values() if v[1] < 0.5)
        readings = _man()["readings"]
        self.assertEqual(disagree, readings["vote_vs_celltype_types"],
                         f"[malecns_test] types where the vote and the type-level self-report disagree got {disagree}")
        self.assertEqual(subhalf, readings["vote_share_subhalf_types"],
                         f"[malecns_test] types whose main transmitter share is <0.5 got {subhalf}")

    def test_nt_ipc_reader_matches_pyarrow_all_columns(self):
        """Reconcile the transmitter table through two read paths, column by column. Reason for the test change:
        the coordinator ruled on 2026-10-20 — the reviewer disproved the premise that "pyarrow/pandas/polars all
        three refuse" (pyarrow 25.0.1 reads it directly on this machine), so an independent pyarrow recomputation
        surface was added and the transmitter-side readout no longer rests only on the implementation's self-report.
        The in-house IPC reader's readout for every column must be cell-for-cell equal to pyarrow's."""
        import pyarrow.feather as feather
        aligned = _impl("aligned")
        nt_path = os.path.join(_HERE, FEATHER_NT)
        t = feather.read_table(nt_path)
        wanted = tuple(t.column_names)
        cols, total = aligned.read_ipc_columns(nt_path, wanted)
        self.assertEqual(total, t.num_rows,
                         f"[malecns_test] transmitter table row count got {total}, "
                         f"pyarrow {t.num_rows}")
        for col in wanted:
            theirs = t.column(col).to_pylist()
            mine = cols[col]
            self.assertEqual(len(mine), len(theirs),
                             f"[malecns_test] transmitter table {col} column row counts differ: "
                             f"{len(mine)} vs {len(theirs)}")
            bad = next((i for i, (a, b) in enumerate(zip(mine, theirs))
                        if a != b), None)
            # The assertion message must not be written as an eager f-string: on a successful reconciliation bad=None,
            # and mine[None] would blow up while constructing the message (the same disease as minor-4).
            if bad is not None:
                self.fail(
                    f"[malecns_test] transmitter table {col} column: in-house reader and pyarrow "
                    f"first differ at row {bad} (in-house {mine[bad]!r} vs "
                    f"pyarrow {theirs[bad]!r})")


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.errors:
        code = 2
    elif result.failures:
        code = 1
    else:
        code = 0
    print(f"\nexit code {code}: " + {
        0: "all green (implementation delivered and reconciled)",
        1: "assertion red (it ran, but the behavior does not match the frozen criteria)",
        2: "runtime error (implementation not delivered or environment incomplete; see ERROR above)",
    }[code])
    return code


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
Test-alignment instance — regression tests and mutation evidence
==============================================================================
Pins three things: that both sides' files are really bound, that the four quadrants
produce the expected numbers, and the mutation evidence that "break the contract
account and exactly that turns red".

The mutation point is Q's predicate: degrade "SKILL.md promised this item" into
"everything is promised". That single change should fire two defense lines at once —
the source self-test raises on the spot, and computing directly while bypassing the
gate misjudges those 4 items "only the test upholds it, the contract never promised
it" as agreed by both sides: divergence drops to zero and common rises from 7 to 11.

Does not depend on pytest (the local `raises` stands in); pytest can still collect it.
Usage: python test_alignment_bootstrap_test.py
       python -m pytest test_alignment_bootstrap_test.py -q
"""
import ast
import contextlib
import io
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))

import test_alignment_bootstrap as A
from breakingdiff import (Claim, ProvenanceError, SourceTestError, compare,
                          verdict, verdict_key)


class raises:
    """Minimal context manager: a stand-in for pytest.raises, so the tests do not
    depend on pytest."""

    def __init__(self, exc):
        self.exc = exc
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"should have raised {self.exc.__name__}, but did not")
        self.value = ev
        return issubclass(et, self.exc)


# B4 legacy upgrade: case #1's "literal glob blacklist" becomes an AST structural
# criterion. The criterion moves from "word surface" to "call site" — synonymous
# primitives such as os.listdir / Path.iterdir can no longer slip through by renaming
# the function; the word "glob" in comments or strings no longer causes false hits.
# The set of directory-scanning primitives (including common synonyms): any one of them
# appearing as a function/attribute name on a Call node is red.
SCAN_PRIMITIVES = frozenset({
    "listdir", "scandir", "iterdir", "walk",
    "glob", "glob_from", "iglob", "rglob",
})


def _scan_primitive_calls(src):
    """AST structural criterion: parse the source, collect every Call node's
    function/attribute name, and return the intersection with SCAN_PRIMITIVES. The word
    surface "glob" is no longer the criterion — words in comments and strings do not
    count, only actual calls do."""
    tree = ast.parse(src)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name and name in SCAN_PRIMITIVES:
            found.add(name)
    return found


# Recalculated after the 2026-10-12 catalog expansion: dominance rose from 2 to 12.
# The 10 added items are the new sections introduced by the trigger-conditions rewrite —
# they used to sit entirely outside the catalog, exactly the blind surface of that
# "zero readout misread as a pass" incident. All are now inside the surface under test.
# 2026-10-15: the six preconditions were renamed and P6 was added; the N-account section
# entered the catalog, where the chain check and outlier attribution are already pinned
# by iteration_chain_test (common 9→11), while the majority-vote clue claim has no
# guardian, so it stays in dominance (12→14).
DOMINANCE_KEYS = [
    "门禁.触发时机.构造期与比较期自动执行",
    "约定.source_tests 的元组形状",
    "触发.触发点在判断节点而非用户措辞",
    "触发.六重结构前提列出",
    "触发.P6 口径独立性",
    "触发.P3 静默区是全部价值所在",
    "触发.编程场景·重构等价性",
    "触发.工程场景·新旧规程对照",
    "触发.理论场景·参数域找反例",
    "触发.科研场景·证据覆盖对照",
    "触发.排除项·只有一份材料",
    "触发.排除项·散文无法枚举",
    "触发.排除项·不裁决谁对谁错",
    "N口径.多数投票只作线索",
    # 2026-10-15: provenance tiers' honest-boundary statement. No test can pin a "does
    # not defend" promise — it stays in dominance as a coverage gap, same as the
    # majority-vote clue claim.
    "溯源.不防源头伪造",
    # 2026-10-16: "coexisting with an existing gate system" gains 1 item (1.2, gate
    # within a gate). The threshold promise has no test yet (document batch A lands docs
    # only), so by the provenance precedent it stays in dominance as a coverage gap and
    # rises to common once the test batch lands.
    "门禁并存.低精度读数禁止做阻断门",
]

DIVERGENCE_KEYS = [
    "范本.语料内 quote 逐字可核",
    "范本.本体源例自测计数",
    "范本.区分点落在哪一点",
    "变异实证.只动被保护处",
    # 2026-10-15: "direction unverified must be marked" was added —
    # the test pins it (mutation domain, finer than SKILL.md),
    # but SKILL.md's verbatim phrase "ratchet direction" is not in the phrase column.
]

# These two promises are pinned by scripts/coverage_guard_test.py, and the P side now
# searches across files, so they rise from dominance to common — guarded and promised,
# as they should be.
COMMON_ADDED = [
    "覆盖门禁.目录表外改动必须抛错",
    "覆盖门禁.门禁自身被变异实证钉住",
    # 2026-10-15: the delivery gate and order_key clauses are pinned by tests (the
    # P-side cross-file search recognizes scripts/delivery_gate_test.py and
    # iteration_chain_test.py), so they rise to common.
    "交付门.换对手不比自己的过去",
    "交付门.支配域大于零即不过",
    "交付门.分歧域不拦",
    "交付门.域外跳过大于零即不过",
    "交付门.两级覆盖结构与量纲纪律",
    "交付门.条目越界也拦",
    "交付门.豁免逐字相等",
    "交付门.自身静默失效被钉死",
    "交付门.覆盖门禁被摘掉也被钉死",
    "交付门.底层门禁不得绕过",
    "覆盖门禁.覆盖率分母含缺口",
    "覆盖门禁.有缺口不得报满覆盖",
    "覆盖门禁.豁免逐字相等而非子串",
    "N口径.棘轮方向由 order_key 定",
    "N口径.anchor 重排后须跟随",
    "N口径.方向未经核实时必须标注",
    # 2026-10-15: PoC / capability declaration table. forgery_poc.py does not enter
    # TEST_FILES_ALL (it holds moves, not assertions), but the commitments it carries do
    # enter the catalog, and delivery_gate_test.py's up-front assertion guards them.
    "PoC.声明表而非拦不住台账",
    "PoC.声明与实测须对账",
    "PoC.改进等于毕业而非改期望",
    # The two hard disciplines for writing mutation tests + dimension discipline
    # (measured 2026-10-15)
    "变异.多防线须核对是哪条拦的",
    "变异.未被抓住须先查变异是否生效",
    "量纲.不同的东西不混进同一集合",
    # The three anti-self-deception protocols (2026-10-15): receipt / provenance /
    # blind write; 12 items pinned by receipt_test.py and provenance_test.py, matching
    # the three new SKILL.md sections.
    "回执.自证不许称已核验",
    "回执.退出码三层",
    "回执.重执行是验真主体",
    "回执.换CWD重跑逐字节一致",
    "溯源.只分两级",
    "溯源.升级路径",
    "溯源.repo_root 显式注入",
    "盲写.调用序主语义",
    "盲写.mtime 只作参考",
    "盲写.期望被改必被抓",
    "盲写.计数器硬对账",
    "盲写.见证软对账",
]

# Recaclulated 2026-10-15: catalog 52 items (delivery gate 10 + coverage-ratio
# discipline 3 + order_key 4 + PoC 3 + two mutation disciplines + dimension 1); the
# three anti-self-deception protocols add 13 more (receipt 4 / provenance 4 / blind
# write 5, with receipt_test.py and provenance_test.py joining TEST_FILES_ALL) → 65.
# Host hooks add 5 more (hook.* 4+1, hook_entry_test.py joining TEST_FILES_ALL) → 70.
# "provenance does not defend against source forgery" and "hook honest degradation" are
# honest-boundary statements with no test that can pin them, so they stay in dominance.
# "coexisting with an existing gate system, low-precision readout must not be a blocking
# gate" has no test yet (document batch A lands docs only); the two conclusion-discipline
# items are a duality that only a human reviewing the transcript can catch (a mechanical
# test cannot pin "did it make up a number"), so by the provenance precedent, all five
# stay in dominance.
EXPECT = dict(common=50, divergence=4, dominance=19, neither=0)


# ---------------------------------------------------------------- provenance binding
def test_quotes_are_verbatim():
    assert A.SPEC_QUOTE in A.SPEC_TEXT
    assert A.TEST_QUOTE in A.TEST_TEXT


def test_fabricated_quote_is_rejected_at_construction():
    # A fabricated quote cannot pass the verbatim check; the gate stops it at
    # construction time
    with raises(ProvenanceError):
        Claim(name="fabricated", predicate=lambda p: True, applies=lambda p: True,
              domain_note="", source="a source", quote="SKILL.md says no such sentence",
              quote_source=A.SPEC_TEXT)


# ---------------------------------------------------------------- gates and comparison
def test_both_claims_pass_their_gates():
    # P side: 3 test points; Q side: 2 (one promise fewer after removing the perishable
    # number)
    for C, n in ((A.make_test_claim(), 3), (A.make_spec_claim(), 2)):
        ok, tot, fails = C.run_source_tests()
        assert (ok, tot, fails) == (n, n, [])
        assert C.run_reading_discrimination()   # at least one interpretation discriminates


def test_four_quadrant_counts():
    r = compare(A.make_test_claim(), A.make_spec_claim(), A.KEYS)
    assert (r.common, r.divergence, r.dominance, r.neither) == (
        EXPECT["common"], EXPECT["divergence"],
        EXPECT["dominance"], EXPECT["neither"])
    assert r.out_of_domain == 0


def test_neither_keys_are_the_guarded_ones():
    """The two items guarded by coverage_guard_test should fall into common, not
    dominance.

    That is where "moved into the surface under test and guarded" lands: P true (an
    assertion exists), Q true (a promise exists). They used to be misjudged as gaps only
    because the P side read a single test file — the other face of tier-one
    under-reporting: inventing a problem out of thin air.
    """
    common, div, dom, nei = A.quadrant_lists(A.make_test_claim(),
                                            A.make_spec_claim())
    assert set(COMMON_ADDED) <= set(common)
    assert not (set(COMMON_ADDED) & set(dom)), "guarded and promised, must not count as a gap"


def test_poc_file_is_not_in_the_assertion_corpus():
    """forgery_poc.py deliberately stays out of TEST_FILES_ALL — different dimensions
    cannot go into the same set.

    It holds "moves" (forge_* / measure), not "assertions" (test_*). The consequence of
    mixing it into the P-side corpus: "the PoC mentions a word" is read as "a test
    asserted an item".

    This is the same discipline as coverage_guard's "a file path and a commitment item
    must not be compared as one", recurring on another level — so it deserves a test:
    without one, "just add the PoC too" is far too natural a move.
    """
    assert os.path.basename(A.POC_FILE) == "forgery_poc.py"
    assert A.POC_FILE not in A.TEST_FILES_ALL, \
        "the PoC entered the assertion corpus: different dimensions in one set, so a word mentioned by the PoC is read as a test assertion"
    # Reverse self-proof: it really has no test_ function, so including it can only be wrong
    assert "def test_" not in A.POC_TEXT, \
        "if forgery_poc.py ever contains a test_ function, it should enter TEST_FILES_ALL"


def test_poc_claims_are_still_in_the_catalog():
    """The PoC staying out of the corpus ≠ the PoC's commitments staying out of the
    surface under test.

    Two things must hold together: the corpus layer excludes it (dimension), the
    commitment layer manages it (coverage). Only the former → commitments carried by the
    PoC are invisible to the four quadrants; only the latter → dimension confusion.

    ★ Must assert the [exact item count], not `assert poc_keys`:
      checking only "non-empty" keeps it green even if one item is deleted — measured in
      mutation evidence, deleting "declaration table rather than ledger" still passed
      this test, a fake test. Deleting one = a gap appears in the commitment layer, and
      a gap is exactly what this gate catches.
    """
    poc_keys = [k for k in A.KEYS if k.startswith("PoC.")]
    assert len(poc_keys) == 3, \
        f"there should be 3 PoC commitment items, got {len(poc_keys)}: {poc_keys} — " \
        f"one missing means the commitment layer lost track, which is the gap this gate catches"
    for k in poc_keys:
        assert A.FUNC[k], f"{k} has no matching assertion function; it is not really guarded"
        assert ("def " + A.FUNC[k]) in A.TEST_CORPUS


def test_witnesses_split_the_two_gaps():
    r = compare(A.make_test_claim(), A.make_spec_claim(), A.KEYS)
    # dominance = the contract promised it, no test upholds it; divergence = a test
    # upholds it, the contract does not promise it
    # dominance witnesses are truncated by the max_witness=8 cap (count 12 > cap 8), so
    # compare the prefix rather than the whole list
    assert r.dominance_witnesses == DOMINANCE_KEYS[:len(r.dominance_witnesses)]
    assert len(r.dominance_witnesses) == 8
    assert r.divergence_witnesses == DIVERGENCE_KEYS


def test_verdict_is_parallel_not_containment():
    P, Q = A.make_test_claim(), A.make_spec_claim()
    r = compare(P, Q, A.KEYS)
    assert verdict_key(r) == "parallel", \
        "the criterion goes through verdict_key (the same key as the port case); the wording takes no part in the assertion"
    v = verdict(r, P, Q)
    assert v.strip(), "the verdict wording must be non-empty presentation-layer output"


# ---------------------------------------------------------------- mutation evidence
def test_mutation_overclaiming_contract_flips_exactly_the_quadrants():
    """Degrade Q into "everything is promised". Compute directly, bypassing the gate:
    those 4 items only the test upholds are misjudged as "both sides agree", divergence
    drops to zero and common rises from 7 to 11; the dominance region, which no test
    guards, does not move."""
    weak_q = A.make_spec_claim(decide=lambda p: True, with_tests=False)
    r = compare(A.make_test_claim(), weak_q, A.KEYS)
    # common = 9 + 4 (divergence merged in) = 13; dominance does not move
    assert (r.common, r.divergence, r.dominance, r.neither) == (
        EXPECT["common"] + EXPECT["divergence"], 0,
        EXPECT["dominance"], 0)
    # Exactly those 4 flip: they were in divergence, now all merged into common
    # Note dominance witnesses are truncated by the max_witness cap (default 8), so only
    # the prefix is compared
    assert r.dominance_witnesses == DOMINANCE_KEYS[:len(r.dominance_witnesses)]
    assert set(DIVERGENCE_KEYS) <= set(A.quadrant_lists(A.make_test_claim(), weak_q)[0])


def test_mutation_is_caught_by_the_source_test_gate():
    """A degraded Q that carries self-tests is stopped on the spot by the gate, and it
    reports on "the item nobody guards"."""
    with raises(SourceTestError) as e:
        compare(A.make_test_claim(), A.make_spec_claim(decide=lambda p: True), A.KEYS)
    assert "变异实证.只动被保护处" in str(e.value)


def test_mutation_stays_local():
    """The mutation touches only the protected item; without touching the predicate the
    result is as before."""
    r = compare(A.make_test_claim(), A.make_spec_claim(), A.KEYS)
    assert (r.common, r.dominance) == (EXPECT["common"], EXPECT["dominance"])


# ---------------------------------------------------------------- B2: Q-side corpus expansion + Q-anchor orphan readout
# Spec source: the B2 spec-freeze batch of this repo (see the matching CHANGELOG entry).
# This batch only expands, never moves: the Q side grows from one file to seven,
# explicitly enumerated, and a new "Q anchor orphan" readout is added — if a phrase is
# moved or rewritten while CATALOG does not follow, the old four quadrants only read it
# as "the test is finer than the spec" (divergence), a silent failure; the orphan readout
# pulls that into an explicit red. All fixtures below are hand-made; neither the live
# CATALOG nor SPEC_FILES is touched.

# The spec-freeze explicit list of six references (glob forbidden; hard-coded here, the
# implementation follows it)
REQUIRED_REFS = (
    "writing-claims.md",
    "test-alignment.md",
    "hooks.md",
    "phase-transition.md",
    "receipt-format.md",
    "domain-mapping.md",
)

# Hand-made fixture for the orphan readout: two orphans (phrases found in no corpus) plus
# one findable. Phrases and corpora are both built by the test, one case in each
# direction, attacking and defending each other — an implementation that misses is caught
# by test_q_anchor_orphans, one that over-detects by test_q_anchor_gate_is_silent.
B2_FX_CATALOG = [
    dict(key="B2fixture.orphan-alpha", phrase="red-fixture orphan anchor alpha · never in any corpus ZQ1",
         topic="fixture", func=None),
    dict(key="B2fixture.orphan-beta", phrase="red-fixture orphan anchor beta · never in any corpus ZQ2",
         topic="fixture", func=None),
    dict(key="B2fixture.findable-gamma", phrase="red-fixture findable anchor gamma · right here in this line",
         topic="fixture", func=None),
]
B2_FX_CORPUS_MISSING = "red-fixture findable anchor gamma · right here in this line\nrest is unrelated body text"
B2_FX_CORPUS_ALL_FOUND = "\n".join(e["phrase"] for e in B2_FX_CATALOG)


def test_spec_files_explicitly_enumerates_seven_sources():
    """C1: SPEC_FILES must be seven explicitly enumerated files, not a glob scan.

    Widening is a registration act: all seven listed one by one, the total exactly seven,
    each really on disk — asserted one by one, so one missing turns red; the total is
    fixed at seven, so files a glob drags in also turn red. But a correct list produced by
    a scan means nothing was registered (files that wander into references/ later are
    silently included), so the source code must also be checked for a glob call.
    """
    assert isinstance(A.SPEC_FILES, list), "SPEC_FILES should be a list, so each item can be registered and reviewed"
    names = [os.path.basename(p) for p in A.SPEC_FILES]
    assert names.count("SKILL.md") == 1, f"SKILL.md should be listed exactly once, got {names}"
    for ref in REQUIRED_REFS:
        assert ref in names, f"references/{ref} did not enter SPEC_FILES — the Q-side corpus is blind to it"
    assert len(A.SPEC_FILES) == 7, \
        f"SPEC_FILES should be exactly 7 items (SKILL.md + six references), got {len(A.SPEC_FILES)}: {names}"
    for p in A.SPEC_FILES:
        assert os.path.isfile(p), f"SPEC_FILES registered a file that does not exist: {p}"
        rel = os.path.relpath(p, A.ROOT)
        assert not rel.startswith(".."), \
            f"SPEC_FILES contains a path outside the repo: {rel} — enumeration must stay inside the breakingdiff tree"
    src = A._read(A.__file__)
    hits = _scan_primitive_calls(src)
    assert not hits, \
        f"the implementation calls a directory-scanning primitive {hits} — widening must be explicit enumeration; " \
        "a scan silently includes files that wander in later"


def test_scan_primitive_criterion_flags_os_listdir_call():
    """B4 #1 upgrade, red direction: inject an os.listdir call → red.
    The old literal blacklist could not do this ('listdir' was not in it); the structural
    criterion can — that is the value of raising the criterion from word surface to call
    site."""
    src = "import os\nfiles = os.listdir('.')\n"
    assert _scan_primitive_calls(src) == {"listdir"}


def test_scan_primitive_criterion_ignores_glob_word_in_comment():
    """B4 #1 upgrade, green direction: the word 'glob' in a comment but no call → not red.
    The old literal blacklist caused a false hit (taking glob in a comment for a call);
    the structural criterion looks only at Call nodes, so the word surface no longer
    causes false hits."""
    src = "# do not scan directories with glob\nfiles = ['a.py', 'b.py']\n"
    assert _scan_primitive_calls(src) == set()


def test_scan_primitive_criterion_covers_iglob_and_rglob():
    """B4 review gap: iglob (lazy glob) and Path.rglob (recursive glob) are both
    directory-scanning primitives, so renaming to either must still be red — the
    criterion is pinned at the call site, not in the word list."""
    src = ("import glob\nfrom pathlib import Path\n"
           "found = glob.iglob('**/*.py')\nhere = Path('.').rglob('*.md')\n")
    assert _scan_primitive_calls(src) == {"iglob", "rglob"}


def test_spec_text_is_union_corpus_of_the_seven_files():
    """C1: the strict Q judgment must consume the merged text of the seven files, no
    longer just SKILL.md.

    The reverse must be checked too: no other root md and no hand-made string may enter
    the corpus — the merge boundary is exactly those seven files in SPEC_FILES; one page
    more is a silent expansion.
    """
    skill_text = A._read(os.path.join(A.ROOT, "SKILL.md"))
    assert skill_text in A.SPEC_TEXT, "SPEC_TEXT does not even contain SKILL.md itself — the set convention went wrong elsewhere"
    for ref in REQUIRED_REFS:
        ref_text = A._read(os.path.join(A.ROOT, "references", ref))
        assert ref_text in A.SPEC_TEXT, \
            f"references/{ref} is not fully in the Q-side corpus — strict judgment still reads SKILL.md only"
    changelog = A._read(os.path.join(A.ROOT, "CHANGELOG.md"))
    assert changelog not in A.SPEC_TEXT, \
        "CHANGELOG.md entered the Q-side corpus — the set boundary exceeds SPEC_FILES, a glob-style silent expansion"
    assert "B2 red fixture · out-of-set anchor string · nowhere does this sentence exist Q7X" not in A.SPEC_TEXT, \
        "a hand-made string should appear in no corpus; its appearance means something else was mixed into corpus loading"


def test_strict_q_predicate_consumes_the_union_corpus():
    """C1: the strict Q predicates (the spec_promises family) really consume the set
    corpus, not just hold the text.

    The witness is a verbatim passage picked live from writing-claims.md that SKILL.md
    does not contain — its source is the file on disk, a different source from the
    SPEC_TEXT under test. Inject it into PHRASE and query the predicate: it is not found
    under the old account and found only after the expansion, so the difference is exactly
    this one point. PHRASE must be restored afterwards, or other cases would consume the
    fixture item.
    """
    guide_text = A._read(os.path.join(A.ROOT, "references", "writing-claims.md"))
    skill_text = A._read(os.path.join(A.ROOT, "SKILL.md"))
    witness = None
    for line in guide_text.splitlines():
        line = line.strip()
        if len(line) >= 12 and line not in skill_text:
            witness = line
            break
    assert witness is not None, \
        "all of writing-claims.md can be found verbatim in SKILL.md — witness selection failed, this test cannot run"
    key = "B2fixture.references-witness"
    A.PHRASE[key] = witness
    try:
        assert A.spec_promises(key), \
            "spec_promises judged text found only in writing-claims.md false — the strict Q corpus was not expanded to a set"
        assert not A.spec_promises("B2fixture.unregistered-key"), \
            "a key with no registered phrase must not count as promised"
    finally:
        del A.PHRASE[key]


def test_q_anchor_orphans_reports_each_missing_key_with_paths():
    """C2: an unfindable phrase must be reported by key, never as "some anchor missing".

    The orphans must be exactly those two: counting the findable gamma, or missing either
    alpha or beta, is a distorted decision. Both keys must be in the error text (text
    reporting only the first fails this test), together with relative-path words for the
    checked set (SKILL.md / references/), so whoever fixes it knows where to reconcile.
    """
    assert hasattr(A, "q_anchor_orphans"), "the new B2 readout q_anchor_orphans is not implemented yet"
    orphans = A.q_anchor_orphans(catalog=B2_FX_CATALOG, corpus=B2_FX_CORPUS_MISSING)
    assert orphans == ["B2fixture.orphan-alpha", "B2fixture.orphan-beta"], \
        f"orphans should be exactly alpha and beta (in catalog order), got {orphans}"
    with raises(ValueError) as e:
        A.assert_no_q_anchor_orphans(catalog=B2_FX_CATALOG, corpus=B2_FX_CORPUS_MISSING)
    msg = str(e.value)
    for k in ("B2fixture.orphan-alpha", "B2fixture.orphan-beta"):
        assert k in msg, f"the error text misses orphan {k}: {msg!r}"
    assert "SKILL.md" in msg and "references/" in msg, \
        f"the error text lacks the relative paths of the checked set (SKILL.md / references/): {msg!r}"


def test_q_anchor_gate_is_silent_when_every_phrase_is_findable():
    """C2, positive direction: when everything is findable the gate must stay quiet — an
    orphan readout must not pass off a tautology as a feature.

    Without this reverse direction, a regression in orphan detection ("better to kill by
    mistake", e.g. judging a phrase permanently unfindable) would not turn red: the
    previous test watches only missed detections, this one watches false hits.
    """
    assert hasattr(A, "q_anchor_orphans"), "the new B2 readout q_anchor_orphans is not implemented yet"
    orphans = A.q_anchor_orphans(catalog=B2_FX_CATALOG, corpus=B2_FX_CORPUS_ALL_FOUND)
    assert orphans == [], f"all three fixture phrases are in the fixture corpus, yet orphans were reported: {orphans}"
    # Not raising is correct; if it really raises, this line turns red
    A.assert_no_q_anchor_orphans(catalog=B2_FX_CATALOG, corpus=B2_FX_CORPUS_ALL_FOUND)


def test_live_repo_has_zero_q_anchor_orphans():
    """C3 acceptance: this batch only expands, never moves; after the expansion the live
    repo must have zero orphans.

    The phrase registration discipline guarantees every phrase was verbatim findable at
    its old location; after the expansion the set is a superset, so orphans can only come
    from a CATALOG typo or a missing file in corpus loading. Measured 2026-10-16: all 67
    phrases are findable inside the seven-file union; this should land at 0.
    """
    orphans = A.q_anchor_orphans()
    assert orphans == [], \
        f"the live repo has Q anchor orphans: {orphans} — the CATALOG phrases are no longer findable in the seven-file corpus"


def test_main_reports_zero_orphan_count_explicitly():
    """C2: the orphan count must explicitly enter the report, including 0 — a silent gap
    is the only evil.

    Run main now and capture stdout: there must be a line mentioning "orphan", and that
    line must carry the count 0. An implementation that speaks only when orphans > 0 turns
    red here — staying quiet at zero orphans merges "checked" and "not checked" into one
    output.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        A.main()
    orphan_lines = [ln for ln in buf.getvalue().splitlines() if "orphan" in ln]
    assert orphan_lines, \
        "no line in the main report mentions \"orphan\" — the orphan count was silenced"
    assert any("0" in ln for ln in orphan_lines), \
        f"the orphan line carries no count 0: {orphan_lines} — the live repo has zero orphans, and the report must say 0"


def test_spec_wide_stays_superset_without_double_counting():
    """C1: SPEC_WIDE semantics unchanged — a superset of the strict corpus, and no
    duplicate concatenation.

    After the set expansion writing-claims.md is already in the strict corpus; concatenating
    the guide again in the relaxed corpus the old way would count the same source twice.
    The criterion must check both ends: the other five references must be present (the old
    SPEC_WIDE lacked them), and the guide's full text must appear exactly once (more is a
    duplicate-count surface, less means the source was lost).
    """
    for ref in REQUIRED_REFS:
        if ref == "writing-claims.md":
            continue
        ref_text = A._read(os.path.join(A.ROOT, "references", ref))
        assert ref_text in A.SPEC_WIDE, \
            f"references/{ref} is not in the relaxed corpus — SPEC_WIDE did not follow the set expansion"
    guide_text = A._read(os.path.join(A.ROOT, "references", "writing-claims.md"))
    occurrences = A.SPEC_WIDE.count(guide_text)
    assert occurrences == 1, \
        f"writing-claims.md appears {occurrences} times in SPEC_WIDE — " \
        + ("duplicate concatenation created a double-count surface" if occurrences > 1 else "the relaxed corpus lost the guide source")


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith('test_') and callable(f)]
    bad = []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception:
            bad.append(name)
            print(f"  FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(fns) - len(bad)}/{len(fns)} passed"
          + (f", failures: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
Test alignment · contract account vs assertion account (the bootstrap instance)
==============================================================================
Normally this compares two snapshots of the same artifact; here it compares two
"statements" of one tool about itself:

  Q contract account = what SKILL.md promises the user (three gates, four-quadrant
                       numbers, verification commands, ...)
  P assertion account = the behavior examples/value_type_fingerprint_test.py
                        actually pins

The parameter space is "one promise / behavior item"; a key is just a string. The
four quadrants then read:

  common      P∧Q   the test pins it and SKILL.md promises it — the contract is upheld
  dominance  ¬P∧Q   SKILL.md promises it but no test upholds it ← the contract's
                    coverage gap (this column is the product)
  divergence  P∧¬Q  the test pins it but SKILL.md does not promise it — the test is
                    finer, usually hardening
  neither    ¬P∧¬Q  items neither side covers

Neither P nor Q hard-codes booleans: the predicates look up their markers in the real
files on the spot — Q looks for that verbatim promise in the contract-side corpus, P
looks for that assertion function in the test files. A marker must occur verbatim in
the file so anyone reading this code can recompute. But the item-to-marker mapping is
decided by the catalog below; the catalog is the judge, and it deserves the same care
as the predicates: change one item's marker and the four quadrants move. The corpus is
the Q-side contract docs (seven files in SPEC_FILES) and the P-side assertion test
files themselves, read verbatim, nothing hand-made.

Promises included in the predicates (mechanically checkable):
  · the trigger conditions of the three gates, and "run automatically at construction
    time and at comparison time"
  · the worked example's four-quadrant output 25/0/1/0
  · source_tests being "a tuple of tuple pairs"

Excluded from the predicates (not mechanically checkable; forcing them in would be
self-deception):
  · "reports are always a lower bound" — a magnitude statement with no enumerable
    witness whose truth can be checked mechanically; it only becomes verifiable once
    it lands on a concrete count, and that is another item.
  · "divergence ≠ better / the tool reports, it does not adjudicate" — a design
    stance, not a predicate that can be true or false.
  · "the predicate still needs human compilation" — a statement about the process,
    with no parameter point to assign true/false to.
  · the "measured criterion power" table — an empirical conclusion over six domain
    pairs, not a promise about this tool's behavior.
  · "when to use, when not to" — a description of applicable scenarios; no item makes
    a predicate out of it.

Usage: python test_alignment_bootstrap.py
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
from breakingdiff import Claim, compare, render

ROOT = os.path.dirname(HERE)
SPEC_FILE = os.path.join(ROOT, 'SKILL.md')
TEST_FILE = os.path.join(HERE, 'value_type_fingerprint_test.py')
# The writing guide and the module under test: the former is a Q-side source document
# (in the strict corpus set since B2), the latter is an extra surface the widest P
# reading looks at
GUIDE_FILE = os.path.join(ROOT, 'references', 'writing-claims.md')
MODULE_FILE = os.path.join(HERE, 'value_type_fingerprint.py')

# The full Q-side corpus (2026-10-16 B2): the contract book + six reference source
# documents, each listed explicitly. Widening is a registration act — the paths are
# hard-coded here, so an over- or under-registration is visible at a glance; a
# directory scan would silently pull any file that wanders into references/ into the
# contract, and the promise boundary would drift on its own. The origin is the same as
# P-side TEST_FILES_ALL: reading only SKILL.md judged promises written in the reference
# docs as "not promised" — a tier-one under-report.
SPEC_FILES = [
    SPEC_FILE,
    GUIDE_FILE,
    os.path.join(ROOT, 'references', 'test-alignment.md'),
    os.path.join(ROOT, 'references', 'hooks.md'),
    os.path.join(ROOT, 'references', 'phase-transition.md'),
    os.path.join(ROOT, 'references', 'receipt-format.md'),
    os.path.join(ROOT, 'references', 'domain-mapping.md'),
]
SPEC_SRC = "breakingdiff/SKILL.md (the contract book frozen for this round)"
TEST_SRC = "breakingdiff/examples/value_type_fingerprint_test.py (the assertion book)"


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


# The strict Q corpus = the union of the seven files; only a newline is added between
# files, and each file's text stays verbatim
SPEC_TEXT = "\n".join(_read(p) for p in SPEC_FILES)
TEST_TEXT = _read(TEST_FILE)
# The full P-side reading (the assertion book): assertions may be scattered across
# several test files. The first implementation read only
# value_type_fingerprint_test.py, so assertion functions elsewhere were judged "no
# assertion" — itself a tier-one under-report: a catalog that misses a file = an
# assertion is counted as a gap out of thin air. Fixed 2026-10-12.
TEST_FILES_ALL = [
    os.path.join(HERE, 'value_type_fingerprint_test.py'),
    os.path.join(HERE, 'test_alignment_bootstrap_test.py'),
    os.path.join(HERE, 'trigger_conditions_test.py'),
    os.path.join(HERE, 'iteration_chain_test.py'),
    os.path.join(ROOT, 'scripts', 'coverage_guard_test.py'),
    # Added 2026-10-15: the delivery gate's own assertions. A catalog that misses a
    # file = guarded items are counted as gaps out of thin air (the reverse of
    # tier-one under-reporting).
    os.path.join(ROOT, 'scripts', 'delivery_gate_test.py'),
    # Added 2026-10-15: assertions for receipts and provenance (anti-self-deception
    # A2/A3/A4). Same reason: a missed file = assertions there are counted as gaps on
    # the P side.
    os.path.join(ROOT, 'scripts', 'receipt_test.py'),
    os.path.join(ROOT, 'scripts', 'provenance_test.py'),
    # Added 2026-10-15: host-hook assertions (P4). Same reason — the hook's defense
    # order, fast paths, and exit-code mapping are all pinned by subprocess runs in
    # hook_entry_test.py.
    os.path.join(ROOT, 'scripts', 'hook_entry_test.py'),
    # Close-out batch 2026-10-16: assertions for the predicate-distortion self-check
    # (1.3) / shared-symbol warning (2.3) / re-anchor helper (3.2) / Q-ledger gap check
    # (4.1), four gates. Same reason: a missed file = assertions there are counted as
    # gaps on the P side.
    os.path.join(ROOT, 'scripts', 'predicate_alignment_test.py'),
    os.path.join(ROOT, 'scripts', 'symbol_isolation_test.py'),
    os.path.join(ROOT, 'scripts', 'reanchor_test.py'),
    os.path.join(ROOT, 'scripts', 'q_ledger_check_test.py'),
    # Added 2026-10-16: the casestudy instance gate (existence checks / count anchors /
    # hubble pure-script assertion). Same reason: a missed file = assertions there are
    # counted as gaps on the P side.
    os.path.join(HERE, 'casestudy_test.py'),
    # docaudit: promise-vs-behavior fixture from the blind-test probe experiment.
    os.path.join(HERE, 'docaudit', 'test_docaudit.py'),
    # Added 2026-10-17 B5: assertions for the hooks decision-order three-copy
    # consistency contract (hooks_contract_test.py). Same reason: a missed file =
    # assertions there are counted as gaps on the P side.
    os.path.join(ROOT, 'scripts', 'hooks_contract_test.py'),
    # Added 2026-10-16 B1: assertions for the reference-integrity gate (dead links /
    # orphans / pointer form); 2026-10-18 B10: the caveat anchor and CATALOG phrase
    # check retired and the gate moved to reconciliation semantics. Same reason: a
    # missed file = assertions there are counted as gaps on the P side.
    os.path.join(ROOT, 'scripts', 'refs_guard_test.py'),
    # Added 2026-10-17 B6: assertions for bd_home's four-level resolution
    # (bd_paths_test.py) and for install-layout build/verify (dist_layout_test.py).
    # Same reason: a missed file = assertions there are counted as gaps on the P side.
    os.path.join(ROOT, 'scripts', 'bd_paths_test.py'),
    os.path.join(ROOT, 'scripts', 'dist_layout_test.py'),
    # Added 2026-10-17 B7: assertions for the version single-source-of-truth
    # sync/check (version_stamp_test.py). Same reason: a missed file = assertions
    # there are counted as gaps on the P side.
    os.path.join(ROOT, 'scripts', 'version_stamp_test.py'),
    # Added 2026-10-18 B12: assertions for the blind-run anti-leak guard
    # (leak_guard_test.py). Same reason: a missed file = assertions there are counted
    # as gaps on the P side.
    os.path.join(ROOT, 'scripts', 'leak_guard_test.py'),
    # strength_calibration: the strength layer's measured ladder (malecns case).
    # Same reason: a missed file = assertions there are counted as gaps on the P side.
    os.path.join(ROOT, 'scripts', 'strength_calibration_test.py'),
    # Added 2026-10-29: assertions for the core engine's zero-domain banners, verdict
    # wording and witness-cap notices (breakingdiff_test.py). Same reason as the list
    # above: a missed file = assertions there are counted as gaps on the P side.
    os.path.join(ROOT, 'scripts', 'breakingdiff_test.py'),
]
TEST_CORPUS = "\n".join(_read(p) for p in TEST_FILES_ALL)

# ★ forgery_poc.py deliberately does NOT enter TEST_FILES_ALL.
#
# It holds "moves", not "assertions": no test_ functions, only forge_* / measure.
# Mixing it into the P-side corpus would let "the PoC mentions a word" be read as
# "a test asserts an item" — different dimensions stuffed into one set, the very
# discipline from coverage_guard recurring on another level.
#
# Its real relation to the P side: delivery_gate_test.py's
# test_gate_blocks_forgery_poc_move_five imports it directly, builds an unchanged
# gate probe from it, and asserts measure(...) == "passes" up front. That is "the PoC
# supplies material, the test asserts", with clear roles.
#
# It is registered here so "why is it not in TEST_FILES_ALL" stays checkable — a
# reason nobody writes down is a reason someone will casually remove in three months.
POC_FILE = os.path.join(HERE, 'forgery_poc.py')
POC_TEXT = _read(POC_FILE)

# The comparison text for a relaxed reading: move the "source document" boundary one
# step outward. Since B2 writing-claims.md is already in the strict corpus, so the
# relaxed corpus is simply the full set — concatenating the guide again the old way
# would count the same source document twice.
SPEC_WIDE = SPEC_TEXT
TEST_WIDE = TEST_CORPUS + _read(MODULE_FILE)

# Verbatim fragments for provenance binding, one from each real file (construction
# time checks that they really occur inside)
SPEC_QUOTE = "an empty `source`/`quote` → `ProvenanceError`"
TEST_QUOTE = "assert (r.common, r.divergence, r.dominance, r.neither) == (25, 0, 1, 0)"


# Catalog: each alignment item records three things —
#   phrase : the verbatim phrase in SKILL.md promising that behavior (None = the
#            contract does not promise it)
#   topic  : the item's topic word; the loose readings use it (they only ask "was it
#            mentioned at all")
#   func   : the name of the assertion function in a test file that pins that behavior
#            (None = no test asserts it)
CATALOG = [
    dict(key="门禁.溯源绑定.缺出处",
         phrase="empty `source`/`quote`", topic="provenance",
         func="test_blank_source_raises_provenance_error"),
    dict(key="门禁.溯源绑定.缺原文",
         phrase="empty `source`/`quote`", topic="provenance",
         func="test_blank_quote_raises_provenance_error"),
    dict(key="门禁.溯源绑定.逐字核对在构造期",
         phrase="also checks the quote verbatim", topic="verbatim",
         func="test_fabricated_quote_is_rejected_at_construction"),
    dict(key="门禁.源例自测.失败即拒",
         phrase="any test point fails", topic="source-test self-check",
         func="test_wrong_source_test_raises"),
    dict(key="门禁.区分力.零区分力即拒",
         phrase="an interpretation has the same value as the body at every test point", topic="discrimination",
         func="test_shape_claim_is_rejected_by_discrimination_gate"),
    dict(key="门禁.触发时机.构造期与比较期自动执行",
         phrase="Three gates run automatically at construction time and at comparison time", topic="construction time",
         func=None),
    dict(key="范本.四象限数字",
         phrase="the four quadrants 25/0/1/0", topic="four-quadrant",
         func="test_type_claim_flags_exactly_one_drift"),
    dict(key="约定.source_tests 的元组形状",
         phrase="a tuple of tuple pairs", topic="tuple",
         func=None),
    dict(key="范本.语料内 quote 逐字可核",
         phrase=None, topic="verbatim",
         func="test_quotes_are_verbatim"),
    dict(key="范本.本体源例自测计数",
         phrase=None, topic="source-test self-check",
         func="test_type_claim_source_tests_pass"),
    dict(key="范本.区分点落在哪一点",
         phrase=None, topic="discrimination",
         func="test_type_claim_discriminates_its_readings"),
    dict(key="变异实证.被保护点恰好翻红",
         phrase="Mutation evidence", topic="mutation",
         func="test_mutation_weakening_fingerprint_flips_exactly_the_protected_case"),
    dict(key="变异实证.只动被保护处",
         phrase=None, topic="mutation",
         func="test_mutation_is_local_others_still_green"),
    # ---- added 2026-10-12: sections introduced by the trigger-conditions rewrite ----
    # These items were absent, so a real change fell entirely outside the surface under
    # test and the four quadrants stayed quiet (a zero readout misread as "verified").
    # Lesson: one missing catalog item = three-level silence.
    dict(key="触发.触发点在判断节点而非用户措辞",
         phrase="The trigger is not an instruction the user gave", topic="trigger point",
         func=None),
    dict(key="触发.六重结构前提列出",
         phrase="six structural preconditions", topic="six preconditions",
         func=None),
    dict(key="触发.P6 口径独立性",
         phrase="the sources of the accounts are independent", topic="P6",
         func=None),
    dict(key="触发.P3 静默区是全部价值所在",
         phrase="the change is legal and raises nothing", topic="silent zone",
         func=None),
    dict(key="触发.编程场景·重构等价性",
         phrase="behavioral equivalence before and after a refactor", topic="refactor",
         func=None),
    dict(key="触发.工程场景·新旧规程对照",
         phrase="a clause-by-clause comparison of acceptance criteria", topic="regulation",
         func=None),
    dict(key="触发.理论场景·参数域找反例",
         phrase="find counterexamples in the same parameter domain", topic="counterexample",
         func=None),
    dict(key="触发.科研场景·证据覆盖对照",
         phrase="a clause-by-clause comparison of what the evidence covers", topic="evidence",
         func=None),
    dict(key="触发.排除项·只有一份材料",
         phrase="only one material", topic="single material",
         func=None),
    dict(key="触发.排除项·散文无法枚举",
         phrase="the account is prose and cannot be enumerated into parameter points", topic="prose",
         func=None),
    dict(key="触发.排除项·不裁决谁对谁错",
         phrase="you need to adjudicate who is right", topic="adjudication",
         func=None),
    dict(key="覆盖门禁.目录表外改动必须抛错",
         phrase="A zero readout is not a pass", topic="coverage gate",
         func="test_real_incident_is_caught"),
    dict(key="覆盖门禁.门禁自身被变异实证钉住",
         phrase="A gate can itself fail silently in three tiers", topic="coverage gate",
         func="test_mutation_disabling_the_gate_is_caught"),
    # ---- added 2026-10-15: N accounts and the iteration chain (compare_n) ----
    # By discipline, commitments of a new section must enter the catalog, or the four
    # quadrants go blind to it. The chain check and outlier attribution are already
    # pinned by iteration_chain_test (the P-side cross-file search finds it); the
    # majority-vote-is-a-clue claim has no test yet — it stays in dominance, read as a
    # coverage gap.
    dict(key="N口径.链检查抓跨版本回归",
         phrase="the old version had it, the new version dropped it", topic="ratchet",
         func="test_ratchet_caught_with_attribution"),
    dict(key="N口径.离群先行带归属",
         phrase="exactly the i-th is False and the rest are True", topic="outlier",
         func="test_outlier_and_pioneer_attribution"),
    dict(key="N口径.多数投票只作线索",
         phrase="Majority voting is only a clue, never a verdict", topic="majority vote",
         func=None),
    # ---- added 2026-10-15: the code-delivery-gate section ----
    # By discipline, commitments of a new section must enter the catalog. The moment
    # that batch was written the gate went red immediately (4 items fell outside the
    # surface under test) — that was not a regression, it was the gate working: without
    # folding them in, those 4 sections stay invisible to the four quadrants, and
    # "zero change" gets read as a pass.
    dict(key="交付门.换对手不比自己的过去",
         phrase="A gate cannot be established by comparing before and after the refactor.", topic="delivery gate",
         func="test_uncovered_spec_item_blocks_delivery"),
    dict(key="交付门.支配域大于零即不过",
         phrase="dominance > 0 is a fail", topic="dominance",
         func="test_uncovered_spec_item_blocks_delivery"),
    dict(key="交付门.分歧域不拦",
         phrase="divergence does not block", topic="divergence",
         func="test_divergence_does_not_block"),
    dict(key="交付门.域外跳过大于零即不过",
         phrase="out-of-domain skip > 0 is a fail", topic="out of domain",
         func="test_out_of_domain_blocks_delivery"),
    dict(key="交付门.两级覆盖结构与量纲纪律",
         phrase="A file path and a commitment item are two different things", topic="dimension",
         func="test_file_not_registered_blocks"),
    dict(key="交付门.条目越界也拦",
         phrase="the item is not in the catalog", topic="dimension",
         func="test_declared_item_outside_catalog_blocks"),
    dict(key="交付门.豁免逐字相等",
         phrase="out-of-domain skip > 0 is a fail", topic="exempt",
         func="test_exempt_uses_verbatim_matching"),
    dict(key="交付门.自身静默失效被钉死",
         phrase="it disguises itself as a pass", topic="delivery gate",
         func="test_mutation_always_passing_gate_is_caught"),
    dict(key="交付门.覆盖门禁被摘掉也被钉死",
         phrase="the coverage gate was removed", topic="coverage gate",
         func="test_mutation_removing_coverage_gate_is_caught"),
    dict(key="交付门.底层门禁不得绕过",
         phrase="Three gates run automatically at construction time and at comparison time", topic="construction time",
         func="test_guards_still_apply_through_the_gate"),
    # ---- added 2026-10-15: coverage_ratio denominator discipline (false-green fix) ----
    dict(key="覆盖门禁.覆盖率分母含缺口",
         phrase="out-of-domain skip > 0 is a fail", topic="coverage gate",
         func="test_ratio_denominator_includes_gaps"),
    dict(key="覆盖门禁.有缺口不得报满覆盖",
         phrase="A zero readout is not a pass", topic="coverage gate",
         func="test_ratio_never_reports_full_coverage_when_gaps_exist"),
    dict(key="覆盖门禁.豁免逐字相等而非子串",
         phrase="out-of-domain skip > 0 is a fail", topic="verbatim",
         func="test_exempt_is_verbatim_not_substring"),
    # ---- added 2026-10-15: ratchet direction must be fixed by order_key ----
    dict(key="N口径.棘轮方向由 order_key 定",
         phrase="A gate cannot be established by comparing before and after the refactor.", topic="order_key",
         func="test_order_key_fixes_direction_when_input_is_shuffled"),
    dict(key="N口径.方向未经核实时必须标注",
         phrase="ratchet direction", topic="order_key",
         func="test_without_order_key_direction_is_flagged_untrusted"),
    dict(key="N口径.方向警示须在报告正文可见",
         phrase="it disguises itself as a pass", topic="order_key",
         func="test_report_warns_about_untrusted_direction"),
    dict(key="N口径.anchor 重排后须跟随",
         phrase="the item is not in the catalog", topic="order_key",
         func="test_anchor_name_follows_the_same_reordering"),
    # ---- added 2026-10-15: forged PoC / capability declaration table (forgery_poc.py) ----
    # forgery_poc.py does not enter TEST_FILES_ALL (it holds moves, not assertions), but
    # the commitments it carries must enter the catalog, or "a declaration table rather
    # than a cannot-block ledger" and "an improvement = graduation, not an assertion
    # edit" stay invisible to the four quadrants.
    dict(key="PoC.声明表而非拦不住台账",
         phrase="effective against sloppiness, ineffective against deliberate forgery", topic="ledger",
         func="test_gate_blocks_forgery_poc_move_five"),
    dict(key="PoC.声明与实测须对账",
         phrase="can this currently fool the gate", topic="declaration",
         func="test_gate_blocks_forgery_poc_move_five"),
    dict(key="PoC.改进等于毕业而非改期望",
         phrase="A gate can itself fail silently in three tiers", topic="mutation",
         func="test_mutation_always_passing_gate_is_caught"),
    # ---- added 2026-10-15: two hard disciplines for mutation tests + dimension discipline ----
    # These three were measured this round and written into step six of
    # references/writing-claims.md. They must enter the catalog, or they are blind to the
    # four quadrants (and they are exactly what prevents going blind).
    dict(key="变异.多防线须核对是哪条拦的",
         phrase="with several lines of defense, `assertRaises` is not enough", topic="defense line",
         func="test_empty_catalog_is_refused"),
    dict(key="变异.未被抓住须先查变异是否生效",
         phrase="first confirm the mutation really took effect", topic="mutation",
         func="test_poc_claims_are_still_in_the_catalog"),
    dict(key="量纲.不同的东西不混进同一集合",
         phrase="things of different dimensions cannot go into the same set for comparison", topic="dimension",
         func="test_poc_file_is_not_in_the_assertion_corpus"),
    # ---- added 2026-10-15: the three anti-self-deception protocols (receipt vs delivery
    # binary / provenance tiers / blind-written expectations) ----
    # Commitments of the three new sections enter the catalog. Among them
    # "provenance. does not defend against source forgery" is an honest-boundary
    # statement: no test can pin a "does not defend" promise, so func stays empty and it
    # stays in dominance as a coverage gap.
    dict(key="回执.自证不许称已核验",
         phrase="self-attested is NEVER worded as \"verified\"", topic="receipt",
         func="test_verify_self_attested_never_claims_verified"),
    dict(key="回执.退出码三层",
         phrase="0=pass / 1=gate failure / 2=runtime error", topic="receipt",
         func="test_gate_exit_code_layers"),
    dict(key="回执.重执行是验真主体",
         phrase="re-executes per rerun_cmd and compares byte for byte", topic="receipt",
         func="test_delete_receipt_and_rerun_is_byte_identical"),
    dict(key="回执.换CWD重跑逐字节一致",
         phrase="rerunning from a different CWD", topic="receipt",
         func="test_cwd_change_is_byte_identical"),
    dict(key="溯源.只分两级",
         phrase="only two tiers", topic="provenance tiers",
         func="test_source_kind_whitelist_two_levels_only"),
    dict(key="溯源.不防源头伪造",
         phrase="does not defend against source forgery", topic="provenance tiers",
         func=None),
    dict(key="溯源.升级路径",
         phrase="promotes it to git-object", topic="provenance tiers",
         func="test_antiforgery_line_aggregates_with_upgrade_hint"),
    dict(key="溯源.repo_root 显式注入",
         phrase="repo_root is injected explicitly", topic="provenance tiers",
         func="test_verify_requires_explicit_repo_root"),
    dict(key="盲写.调用序主语义",
         phrase="write_expected → compare → reconcile", topic="blind write",
         func="test_blind_write_then_compare_reconciles_clean"),
    dict(key="盲写.mtime 只作参考",
         phrase="mtime is downgraded to reference information only", topic="blind write",
         func="test_blind_write_then_compare_reconciles_clean"),
    dict(key="盲写.期望被改必被抓",
         phrase="editing the expectation afterwards fails the check on the spot", topic="blind write",
         func="test_marker_catches_expectation_tampered_after_write"),
    dict(key="盲写.计数器硬对账",
         phrase="hard counter reconciliation", topic="blind write",
         func="test_blind_write_mismatch_lists_diffs_and_fails_gate"),
    dict(key="盲写.见证软对账",
         phrase="soft witness-list reconciliation", topic="blind write",
         func="test_witness_soft_reconciliation_never_blocks"),
    # ---- added 2026-10-15: host hooks (P4). The hook's decision order / defense order are
    # all pinned by hook_entry_test.py via subprocess runs; "honest degradation" is the
    # same shape as provenance: "does not defend against forgery" has no test that can pin
    # it, so func stays empty and it stays in dominance as a coverage gap.
    dict(key="hook.产物状态机",
         phrase="product state machine", topic="host hooks",
         func="test_pending_without_receipt_blocks_with_actionable_stderr"),
    dict(key="hook.stop_hook_active 守卫",
         phrase="exit 0 immediately", topic="host hooks",
         func="test_stop_hook_active_short_circuits_before_any_disk_check"),
    dict(key="hook.快路径第一分支",
         phrase="exit 0 instantly", topic="host hooks",
         func="test_no_marker_dir_exit_zero_fast"),
    dict(key="hook.退出码映射",
         phrase="feed actionable text back over stderr", topic="host hooks",
         func="test_receipt_gate_fail_maps_to_two"),
    dict(key="hook.诚实降级",
         phrase="raises the cost of sloppiness, not the cost of forgery", topic="host hooks",
         func=None),
    # ---- added 2026-10-16: coexisting with an existing gate system (1.2, gate within a gate) ----
    # The blocking-gate threshold is a checkable promise; document batch A lands docs
    # only, no tests (tests belong to a later batch), so func=None, following the
    # "provenance does not defend against source forgery" precedent: it stays in
    # dominance as a coverage gap.
    dict(key="门禁并存.低精度读数禁止做阻断门",
         phrase="forbidden as a blocking gate", topic="existing gate",
         func=None),
    # ---- added 2026-10-18: conclusion discipline (MUST/NEVER duality, file-tail socket) ----
    # A prompt-level defense line against "made-up counts at the conclusion layer" (the
    # measured point where re-running with new material loses marks): MUST gives a way out
    # (counts taken verbatim from the readout text, witnesses pointed at), NEVER seals it
    # (a number with no readout support must not be written). It guards agent behavior,
    # not code behavior; no permanent test can pin it, so func=None and it stays in
    # dominance as a coverage gap — the same precedent as "provenance does not defend
    # against source forgery".
    dict(key="结论纪律.计数逐字取自读数",
         phrase="taken verbatim from the tool's readout text", topic="conclusion discipline",
         func=None),
    dict(key="结论纪律.无读数支撑的数字禁写",
         phrase="must not be stated as a readout", topic="conclusion discipline",
         func=None),
]

# Section title → the topic of the commitment items it carries.
#
# 2026-10-15: after exemptions moved from substring matching to verbatim equality, the
# coverage gate compares "the section title verbatim ∈ the catalog's topic set". This
# mapping is the bridge between the two.
#
# Why the table must be explicit: the bridge is the judge. One unregistered section =
# that section falls outside the surface under test = the gate is blind to it (SKILL.md
# three-level silence, tier 3). Any missing entry here turns the coverage gate red on the
# spot — which is exactly what it is supposed to do.
SECTION_TOPICS = {
    "Coexisting with an existing gate system": "existing gate",
    "Receipt vs. delivery": "receipt",
    "Blind-written expectations": "blind write",
    "Provenance tiers": "provenance tiers",
    "Host hooks (optional installation)": "host hooks",
    "Conclusion discipline": "conclusion discipline",
    "Mutation evidence": "mutation",
    "Forged PoC and capability declaration table: effective against sloppiness ≠ effective against deliberate forgery": "ledger",
    "Reconciliation between the delivery gate and the PoC": "declaration",
    "Under-reporting does not only miss real problems; it can invent them": "mutation",
}

KEYS = [e["key"] for e in CATALOG]
PHRASE = {e["key"]: e["phrase"] for e in CATALOG}
# Topics are English on both sides: Q's two loose readings and P's two loose readings
# look up the same table, so there is no duplicate table to keep in sync. The P-side
# test files are English, so a single English topic word per item serves both.
TOPIC = {e["key"]: e["topic"] for e in CATALOG}
FUNC = {e["key"]: e["func"] for e in CATALOG}

# Exempt sections = structural explanations that carry no mechanically checkable
# promise. Criterion (ask this before adding an exemption): does this section contain a
# sentence of the form "I promise X"? Yes → it must not be exempt; fold it into the
# catalog. No → it may be exempt.
STRUCTURAL_SECTIONS = {
    "When to use, when not to",
    "N accounts and the iteration chain (compare_n)",
    "Test alignment (advanced usage)",
    "Three-layer structure",
    "Workflow",
    "Boundaries",
    "Three-level silence: before reading out, judge whether the surface under test still covers the change",
    "Verification runs",
    "Six structural preconditions",
}


def spec_promises(p):
    """Q's main claim: only a promise phrase found verbatim in SKILL.md counts as
    promised."""
    phrase = PHRASE.get(p)
    return bool(phrase) and phrase in SPEC_TEXT


def spec_topic_mentioned(p):
    """Q's loose reading: the item counts if its topic word appears anywhere in
    SKILL.md. Looser than the main claim, so it over-acknowledges."""
    topic = TOPIC.get(p)
    return bool(topic) and topic in SPEC_TEXT


def spec_topic_widest(p):
    """Q's widest reading: count references/ as part of the contract book too; the topic
    word appearing is enough."""
    topic = TOPIC.get(p)
    return bool(topic) and topic in SPEC_WIDE


def q_anchor_orphans(catalog=None, corpus=None):
    """Q-anchor orphans: items whose catalog phrase can no longer be found verbatim in
    the Q-side corpus.

    The phrase registration discipline is "verbatim findable at the moment of
    registration". If the promise is later moved or rewritten while the catalog does not
    follow, the four quadrants only read it as "the test is finer than the spec" and drop
    it into divergence — ledger drift recorded as hardening, a silent failure. This
    readout pulls that drift into an explicit column. catalog/corpus are injectable so a
    test can verify the decision itself with a hand-made fixture.
    """
    entries = CATALOG if catalog is None else catalog
    text = SPEC_TEXT if corpus is None else corpus
    return [e["key"] for e in entries
            if e["phrase"] is not None and e["phrase"] not in text]


def assert_no_q_anchor_orphans(catalog=None, corpus=None):
    """The gate form of the orphan readout: raise if there are orphans, naming each key
    and listing the relative paths of the checked set."""
    orphans = q_anchor_orphans(catalog, corpus)
    if orphans:
        paths = " / ".join(
            os.path.relpath(p, ROOT).replace(os.sep, '/') for p in SPEC_FILES)
        raise ValueError(
            f"Q anchor orphans: {len(orphans)} item(s) — these phrases are no longer verbatim in the Q-side corpus"
            f" (registration drifted from the text; reconcile before running the readout): {', '.join(orphans)}. "
            f"Checked set: {paths}")


def asserts_entry(p):
    """P's main claim: this assertion function really exists in the assertion files.

    The first implementation read only value_type_fingerprint_test.py, so assertion
    functions elsewhere were judged "no assertion" — guarded items were counted as gaps
    out of thin air. Changed to search in TEST_CORPUS (the union of the test files).
    """
    fn = FUNC.get(p)
    return bool(fn) and ("def " + fn) in TEST_CORPUS


def asserts_by_topic(p):
    """P's loose reading: the item counts if its topic word appears in any assertion
    file. Looser than the main claim, so it over-acknowledges."""
    topic = TOPIC.get(p)
    return bool(topic) and topic in TEST_CORPUS


def asserts_by_topic_wide(p):
    """P's widest reading: include the module under test, so any topic word counts."""
    topic = TOPIC.get(p)
    return bool(topic) and topic in TEST_WIDE


SPEC_TESTS = (
    ("门禁.溯源绑定.缺出处", True),
    ("变异实证.只动被保护处", False),   # the main claim says "not promised"; the loose reading says "promised"
)

TEST_TESTS = (
    ("门禁.溯源绑定.缺出处", True),
    ("门禁.触发时机.构造期与比较期自动执行", False),   # the main claim says "not asserted"; the loose reading says "asserted"
    ("变异实证.被保护点恰好翻红", True),
)

SPEC_READINGS = (
    Claim(name="reading: topic word counts as a promise",
          predicate=spec_topic_mentioned, applies=lambda p: True,
          domain_note="a looser formalization of the same sentence",
          source=SPEC_SRC, quote=SPEC_QUOTE, quote_source=SPEC_TEXT),
    Claim(name="reading: contract corpus plus references/, any topic word counts",
          predicate=spec_topic_widest, applies=lambda p: True,
          domain_note="widest reading, extending the provenance boundary by one step",
          source=SPEC_SRC, quote=SPEC_QUOTE, quote_source=SPEC_TEXT),
)

TEST_READINGS = (
    Claim(name="reading: topic word counts as a guarded assertion",
          predicate=asserts_by_topic, applies=lambda p: True,
          domain_note="a looser formalization of the same sentence",
          source=TEST_SRC, quote=TEST_QUOTE, quote_source=TEST_TEXT),
    Claim(name="reading: include the module under test, any topic word counts",
          predicate=asserts_by_topic_wide, applies=lambda p: True,
          domain_note="widest reading, extending this account's surface by one step",
          source=TEST_SRC, quote=TEST_QUOTE, quote_source=TEST_TEXT),
)


def make_spec_claim(decide=None, with_tests=True):
    """Q's claim. decide is injectable — mutation evidence uses it to break "the
    contract promises" into "everything is promised"."""
    kw = dict(source_tests=SPEC_TESTS, reading_variants=SPEC_READINGS) if with_tests else {}
    return Claim(
        name="Q the items SKILL.md promises",
        predicate=decide or spec_promises,
        applies=lambda p: True,
        domain_note=f"all alignment items, {len(KEYS)} in total",
        source=SPEC_SRC, quote=SPEC_QUOTE, quote_source=SPEC_TEXT,
        **kw)


def make_test_claim(decide=None, with_tests=True):
    """P's claim. decide is likewise injectable, for mutation."""
    kw = dict(source_tests=TEST_TESTS, reading_variants=TEST_READINGS) if with_tests else {}
    return Claim(
        name="P the items the test files assert",
        predicate=decide or asserts_entry,
        applies=lambda p: True,
        domain_note=f"all alignment items, {len(KEYS)} in total",
        source=TEST_SRC, quote=TEST_QUOTE, quote_source=TEST_TEXT,
        **kw)


def quadrant_lists(P, Q):
    """Sort each item into a quadrant directly by predicate, for the main program's
    lists (order follows KEYS)."""
    common, div, dom, nei = [], [], [], []
    for k in KEYS:
        p, q = bool(P.predicate(k)), bool(Q.predicate(k))
        (common if p and q else div if p and not q
         else dom if q and not p else nei).append(k)
    return common, div, dom, nei


def _section_titles(text):
    """Extract SKILL.md's section titles (levels one and two) as "this round's objective
    footprint".

    Why not derive them from the catalog: that checks "are the words the catalog knows
    in the catalog", a tautology, self-deception — an end-to-end measurement proved it
    blocks nothing. The footprint of a change must come from the changed file itself.
    """
    out = set()
    for line in text.split("\n"):
        m = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if m:
            out.add(m.group(1))
    return out


def self_coverage_gate():
    """Pass the coverage gate before reading the four quadrants.

    The 2026-10-12 incident: SKILL.md was rewritten substantially, and the six
    preconditions, the four domain scenarios, and the three exclusions all sat outside
    the catalog; the four quadrants quietly returned an unchanged 7/4/2/0 readout — and
    "zero change" was read as "verified".

    The reconciliation direction is the key: the footprint of the change is extracted
    from SKILL.md, the surface under test comes from the catalog — two independent
    sources. The old writing derived the checked set from the catalog, the same source
    as the checked set, a tautology — an end-to-end measurement proved a newly added
    section still passed (reproduced and fixed).
    """
    from coverage_guard import require_covered

    # Change footprint: real section titles. Extracted only from SKILL.md itself — since
    # B2 SPEC_TEXT is a seven-file union, but this gate audits the bridge "SKILL.md
    # sections vs catalog", while each references file has its own section ecosystem off
    # this bridge; if the footprint grew with the corpus, their titles would be swept in
    # as false gaps.
    footprint = _section_titles(_read(SPEC_FILE))
    # Surface under test: the markers the catalog knows ∪ the keys of the section-to-topic
    # mapping. The keys of SECTION_TOPICS are "registered section titles" — after
    # exemptions moved from substring matching to verbatim equality, they keep a checkable
    # bridge between sections and commitment items.
    covered = set(TOPIC.values()) | set(SECTION_TOPICS)

    # Exemptions must be short, and each must be able to say "it carries no mechanically
    # checkable promise". Threshold: a new section not in this list must enter the catalog
    # — that is this gate's enforcement point.
    require_covered(footprint, covered,
                    exempt=STRUCTURAL_SECTIONS,
                    what="SKILL.md sections vs catalog")
    return True


def main():
    self_coverage_gate()          # ← before the readout, judge "does the surface under test still cover it"
    P, Q = make_test_claim(), make_spec_claim()

    for C, lab in ((P, "P assertion account"), (Q, "Q contract account")):
        ok, tot, fails = C.run_source_tests()
        d = C.run_reading_discrimination()
        print(f"{lab} source self-test {ok}/{tot}; interpretations {len(C.reading_variants)}, "
              f"distinguishing points {len(d)} {d}")
    print()

    r = compare(P, Q, KEYS)
    print(render(P, Q, r,
                 p_label="test-assertion account", q_label="SKILL.md contract account",
                 meaning_divergence="the test pins finer than the contract (mostly hardening; delete if too fine)",
                 meaning_dominance="⚠️ the contract promised it but no test upholds it — coverage gap"))

    common, div, dom, nei = quadrant_lists(P, Q)
    print()
    print(f"Dominance list (promised by SKILL.md, not asserted by tests), {r.dominance} items:")
    for k in dom:
        print(f"    - {k}    [contract phrase: {PHRASE[k]!r}]")
    print()
    print(f"Divergence list (asserted by tests, not promised by SKILL.md), {r.divergence} items:")
    for k in div:
        print(f"    - {k}    [assertion line: {FUNC[k]}]")
    print()
    n = len(KEYS)
    print(f"Common {r.common} items, neither {r.neither} items. "
          f"Accounts: {n} items in total, dominance {r.dominance}/{n} = {r.dominance / n:.0%}, "
          f"divergence {r.divergence}/{n} = {r.divergence / n:.0%}")
    # Q-anchor orphans (the new B2 readout): >0 already raised on the line above, so
    # reaching here means 0 — but 0 must still be reported; "never checked" and "checked,
    # zero" must be distinguishable in the report.
    assert_no_q_anchor_orphans()
    print("Q anchor orphans: 0 items (every catalog item with a phrase is verbatim findable in the Q-side corpus)")


if __name__ == '__main__':
    main()

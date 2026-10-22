# -*- coding: utf-8 -*-
"""
refs_guard red-first baseline — assertions on disk before the implementation
================================================================================
Batch B1 adds a static reference-integrity gate to breakingdiff (scripts/refs_guard.py).
This file is the red end of TDD: the green/red behavior of the 13 assertions is
pinned first, per the B1 spec (15 after batch B4 adds M-N3/N4; 13 after B10
retires two invariant checks; 14 after B11 adds pointer-promise reconciliation;
the CATALOG loader retired in the same batch was a function deletion and does
not join the assertion count).
At this moment refs_guard.py does not exist yet; the import failure is itself
the red baseline — not bypassed, not stubbed around.

Tests are mostly fixture-driven: each assertion builds synthetic SKILL.md /
references copies in a temp directory and measures red/green. The live repo
changes batch by batch, so hard-coding its line counts or file counts into tests
would pin the regression net to one historical slice; live-repo forward checks
live in a separate test_live_* section and do not write the live repo's concrete
content into assertions.
main(root=None)'s live-repo path is not untested: since B4 there are 8
live-repo acceptance cases (the test_live_* section), and once the known live
reds were fixed they turned into the normal all-green account
(2026-10-18 B11 scheduler revision; the old "deliberately untested" wording is
obsolete).

The contract the implementer must honor (disagreements go to the scheduler for a
ruling; do not rewrite a test just to make it green):
  1. Each assertion is an independent function; root = a directory containing
     SKILL.md and references/. skill_text / agents_text can be injected; when
     injected the injected value wins, and the corresponding file may be absent
     from disk.
  2. Every red is a RefsError; the text starts with [refs_guard], is multi-line
     and actionable, and must name the specific file; where a line can be
     located it must carry "relative/path:line" (forward slashes, e.g.
     SKILL.md:10, references/a.md:3). File-level problems (orphans, missing
     CHANGELOG and the like) only need to name the file, not a line.
  3. SKIP allows exactly one condition, "the target file does not exist yet",
     appended to the module-level SKIP_LOG (a list of strings, carrying the
     target name and the reason); warnings go into WARN_LOG and never raise.
     run_checks clears both logs when it enters, so a report contains only this
     run's records.
  4. run_checks returns a fixed six-key summary dict, and exit codes follow the
     repository's three tiers: 0=all green / 1=something red / 2=runtime error
     (see the receipt.py convention).
  5. M-P3 (assert_pointer_form) is measured red/green by the function itself and
     has been active by default since B8: run_checks runs it even without
     pointer_form_active, the live repo's three-part pointers should pass, and
     there is no suspended SKIP any more.

No pytest dependency (raises is a local implementation); pytest can collect the
file as well.
Usage: python refs_guard_test.py
"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import refs_guard
from refs_guard import (RefsError, assert_changelog_on_skill_change,
                        assert_hooks_contract_pair, assert_nav_links_exist,
                        assert_no_dead_links, assert_no_dead_relative_links,
                        assert_no_host_vars_in_references,
                        assert_no_orphans, assert_no_prose_in_nav,
                        assert_no_reference_cross_links, assert_pointer_form,
                        assert_pointer_promises, assert_toc_required,
                        main, run_checks, warn_nav_line_count,
                        _MD_LINK_RE)


class raises:
    """Minimal context manager: a stand-in for pytest.raises."""

    def __init__(self, exc):
        self.exc, self.value = exc, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"expected {self.exc.__name__} to be raised, but nothing was")
        self.value = ev
        return issubclass(et, self.exc)


# The run_checks summary structure and the default check surface (after B10
# retires two invariant checks and B11 adds pointer-promise reconciliation,
# --check-commit is a separate entry point among the 14 and does not join the
# default 13). The key set is pinned with an equality assertion; an extra or
# missing key is contract drift.
# B4 surface expansion (scheduler ruling): M-N3/N4 join the default check
# surface — if they were mounted only through main()'s checks injection, a
# programmatic consumer calling run_checks(root) would silently never run these
# two assertions. The expansion is an explicit list; the freeze intent against
# quiet additions and removals is unchanged.
RUN_CHECK_KEYS = {"root", "checks", "reds", "skips", "warnings", "exit_code"}
DEFAULT_CHECKS = {
    "assert_no_dead_links", "assert_no_orphans",
    "assert_no_reference_cross_links", "assert_toc_required",
    "assert_no_host_vars_in_references", "assert_pointer_form",
    "assert_pointer_promises",
    "assert_no_prose_in_nav", "assert_nav_links_exist", "assert_no_dead_relative_links",
    "warn_nav_line_count", "assert_hooks_contract_pair",
    "assert_agent_visible_manifest",
    "assert_no_overlap_between_agents_and_skill",
}


# ------------------------------------------------------------ fixtures
def _tmpdir():
    return tempfile.mkdtemp(prefix="bd_refs_guard_test_")


def _write(root, rel, text):
    path = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def _clear_logs():
    """Each test clears the logs before acting: SKIP_LOG/WARN_LOG are the
    subject's global records, cleared at the start of every test so runs do not
    contaminate each other."""
    refs_guard.SKIP_LOG.clear()
    refs_guard.WARN_LOG.clear()


def green_skill():
    """An all-green SKILL.md. The line numbers are laid out on purpose: a red
    fixture changes exactly one spot, and the attribution assertions pin the
    known line numbers (SKILL.md:8 and the like). The pointer form follows the
    three-part source text of plan §3.2.3: trigger condition → which section to
    read → what it solves."""
    return "\n".join([
        "# breakingdiff",                                                    # 1
        "",                                                                  # 2
        "N-account claim differential engine: compress each material into a claim and compute the four quadrants.",  # 3
        "This is by design, not a hole: every count reported is a lower bound.",  # 4
        "",                                                                  # 5
        "## Pointers",                                                       # 6
        "",                                                                  # 7
        "Change something in the claim differential → read the four-quadrant section of references/a.md → stops a zero readout being read as a pass",  # 8
        "Hand over a receipt → read the reconciliation section of references/b.md → stops receipt fields from drifting",  # 9
        "",                                                                  # 10
        "Level three gives the look of \"everything is normal\"; the gate itself can also go silent in three tiers.",  # 11
        "If this change were wrong, would the existing readout move? Effective against sloppiness, ineffective against deliberate forgery.",  # 12
        "Otherwise the capability declaration table is self-referential. When fixing under-reporting, also ask \"will it invent false problems\".",  # 13
    ])


def green_refs():
    """The promise words live in the body, not in the H1 title — after the B11
    hardening the head titles do not count as hit text
    (refs_guard._body_minus_head_titles), so the fixture must use the same
    account as reality: titles are self-introduction, delivery is judged on the
    body."""
    return {
        "references/a.md": "\n".join([
            "# Four-quadrant readout",
            "",
            "How the four quadrants are read: common, divergence, dominance, neither.",
        ]),
        "references/b.md": "\n".join([
            "# Receipt reconciliation",
            "",
            "How expected blind writes and the surprise gate are read; the reconciliation block compares field by field.",
        ]),
    }


def make_repo(files=None):
    """Build a temporary synthetic repo: files is {relative path: text}; the
    default is the all-green trio."""
    d = _tmpdir()
    if files is None:
        files = {"SKILL.md": green_skill(), **green_refs()}
    for rel, text in files.items():
        _write(d, rel, text)
    return d


def long_ref(n_lines, with_toc=False):
    """Build a references article with exactly n lines; with_toc puts
    "## Contents" on line 2."""
    lines = ["# A long article"]
    if with_toc:
        lines.append("## Contents")
    i = 0
    while len(lines) < n_lines:
        lines.append("line %d of body, covering how the readout is reconciled." % i)
        i += 1
    return "\n".join(lines)


def nav_table(rows, col2="Location"):
    """Minimal AGENTS.md shape: 4 header lines plus data rows."""
    lines = ["# Navigation", "", "| Item | %s |" % col2, "| :- | :- |"]
    lines += rows
    return "\n".join(lines)


def nav_with_lines(n):
    """A navigation table with exactly n lines — the line count itself is the
    criterion of warn_nav_line_count."""
    lines = ["# Navigation", ""]
    i = 0
    while len(lines) < n:
        lines.append("| placeholder%d | scripts/breakingdiff.py |" % i)
        i += 1
    return "\n".join(lines)


NAV_CLEAN = nav_table(["| Differential core | scripts/breakingdiff.py |",
                       "| Skill body | SKILL.md |"])


# ── 1. dead links: every references file SKILL.md points at must exist ───────
def test_dead_link_green_when_every_pointer_resolves():
    d = make_repo()
    try:
        assert_no_dead_links(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_dead_link_red_names_skill_line_and_missing_file():
    """The red fixture adds exactly one pointer to a file that does not exist;
    everything else stays green. The error text must name both SKILL.md:10 and
    ghost.md — without the line number there is nothing to fix, and without the
    file name the pointer could have been stopped by another check instead
    (false green); both are unactionable."""
    files = {"SKILL.md": green_skill().replace(
        "Hand over a receipt → read the reconciliation section of references/b.md → stops receipt fields from drifting",
        "Hand over a receipt → read the reconciliation section of references/b.md → stops receipt fields from drifting\n"
        "Change the pointer form → read the pointer section of references/ghost.md → stops dead links"),
        **green_refs()}
    d = make_repo(files)
    try:
        with raises(RefsError) as e:
            assert_no_dead_links(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "SKILL.md:10" in msg, f"the error must carry file:line: {msg!r}"
        assert "ghost.md" in msg, f"it must name the missing file: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 2. orphans: every references article must be pointed at from SKILL.md ────
def test_orphan_green_when_every_ref_is_pointed():
    d = make_repo()
    try:
        assert_no_orphans(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_orphan_red_names_the_unreferenced_file():
    files = {"SKILL.md": green_skill(), **green_refs(),
             "references/extra.md": "# An extra article\n\nNobody points here."}
    d = make_repo(files)
    try:
        with raises(RefsError) as e:
            assert_no_orphans(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "extra.md" in msg, f"it must name the orphan file: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 3. cross-links: references must not link to each other (M-D6, one level) ─
def test_cross_link_green_when_refs_stay_disconnected():
    d = make_repo()
    try:
        assert_no_reference_cross_links(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cross_link_red_names_offending_file_and_line():
    a = "\n".join(["# Four-quadrant readout", "",
                   "Reconciliation details are in the reconciliation section of references/b.md."])   # line 3 holds the cross-link
    d = make_repo({"SKILL.md": green_skill(), "references/a.md": a,
                   "references/b.md": green_refs()["references/b.md"]})
    try:
        with raises(RefsError) as e:
            assert_no_reference_cross_links(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "references/a.md:3" in msg, f"it must name the file and line of the cross-link: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 4. TOC: references past 100 lines must have "## Contents" at the top (M-D7) ─
def test_toc_green_short_file_needs_no_toc():
    d = make_repo()
    try:
        assert_toc_required(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_toc_green_at_hundred_line_boundary():
    """Boundary pinned: the criterion is "> 100 lines"; exactly 100 does not
    exceed it."""
    d = make_repo({"SKILL.md": green_skill(), "references/a.md": long_ref(100)})
    try:
        assert_toc_required(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_toc_green_when_long_file_has_toc_on_top():
    d = make_repo({"SKILL.md": green_skill(),
                   "references/a.md": long_ref(101, with_toc=True)})
    try:
        assert_toc_required(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_toc_red_names_long_file_without_toc():
    d = make_repo({"SKILL.md": green_skill(), "references/a.md": long_ref(101)})
    try:
        with raises(RefsError) as e:
            assert_toc_required(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "a.md" in msg, f"it must name the file missing a TOC: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 5. host variables: references must not contain ${CLAUDE_ (M-D5) ─────────
def test_host_var_green_when_refs_clean():
    d = make_repo()
    try:
        assert_no_host_vars_in_references(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_host_var_red_names_ref_file_and_line():
    a = "\n".join(["# Four-quadrant readout", "",
                   "The scripts directory is hard-coded as ${CLAUDE_SKILL_DIR}/scripts."])
    d = make_repo({"SKILL.md": green_skill(), "references/a.md": a,
                   "references/b.md": green_refs()["references/b.md"]})
    try:
        with raises(RefsError) as e:
            assert_no_host_vars_in_references(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "references/a.md:3" in msg, f"it must name the line holding the host variable: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_host_var_scan_stays_inside_references():
    """The scan surface is pinned to references/: a host variable in the
    SKILL.md body/frontmatter is legal (plan §host-variable section), and
    scanning beyond would drag legal files into a false red."""
    d = make_repo({"SKILL.md": green_skill()
                   + "\n\nInstall the hook with ${CLAUDE_SKILL_DIR}."})
    try:
        assert_no_host_vars_in_references(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 6. pointer form: every references pointer holds two → (M-P3) ────────────
def test_pointer_form_green_with_three_part_pointers():
    """The three-part form follows the plan §3.2.3 source shape: trigger
    condition → which section to read → what it solves. Injecting skill_text is
    enough to test it; SKILL.md need not be on disk — text injection is part of
    the contract."""
    d = _tmpdir()
    try:
        assert_pointer_form(d, skill_text=green_skill())
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_pointer_form_red_when_pointer_has_one_arrow():
    skill = green_skill().replace(
        "Change something in the claim differential → read the four-quadrant section of references/a.md → stops a zero readout being read as a pass",
        "Change something in the claim differential → read the four-quadrant section of references/a.md")
    d = _tmpdir()
    try:
        with raises(RefsError) as e:
            assert_pointer_form(d, skill_text=skill)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "SKILL.md:8" in msg, f"it must name the line of the two-part pointer: {msg!r}"
        assert "a.md" in msg, f"it must name which pointer it is: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_pointer_form_red_when_pointer_has_no_arrow():
    skill = green_skill().replace(
        "Change something in the claim differential → read the four-quadrant section of references/a.md → stops a zero readout being read as a pass",
        "Read the four-quadrant readout in references/a.md")
    d = _tmpdir()
    try:
        with raises(RefsError) as e:
            assert_pointer_form(d, skill_text=skill)
        assert "SKILL.md:8" in str(e.value), f"no arrow must still locate the line: {e.value!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 7. pointer promises: what a pointer promises must be present in the target
#       file as content words (B11) ─────────────────────────────────────────
def test_pointer_promises_green_when_fixture_promises_fulfilled():
    """All-green fixture: SKILL.md promises "four-quadrant section" and
    "reconciliation section", and a.md/b.md really contain the matching content
    (four-quadrant readout / receipt reconciliation) → the forward check passes
    and leaves no SKIP — with the file on disk a promise is always decidable, so
    this check has no suspended state."""
    d = make_repo()
    try:
        _clear_logs()
        assert_pointer_promises(d)
        assert refs_guard.SKIP_LOG == [], f"the promise check must not SKIP: {refs_guard.SKIP_LOG!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


def test_pointer_promises_red_names_promise_and_file():
    """Reconciliation-semantics red text: tamper with the pointer's promise word
    (four-quadrant section → ghost section) → "pointer promises X, but a.md does
    not deliver", naming SKILL.md:8 at the same time — the agent receiving the
    error can locate which pointer's which promise broke, instead of the old
    "phrase missing" wording."""
    skill = green_skill().replace("the four-quadrant section", "the ghost section")
    d = make_repo({"SKILL.md": skill, **green_refs()})
    try:
        with raises(RefsError) as e:
            assert_pointer_promises(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "SKILL.md:8" in msg, f"it must name the line the promise sits on: {msg!r}"
        assert "[RG:POINTER_PROMISE_UNFULFILLED]" in msg, f"it must use reconciliation semantics (criterion code is fixed): {msg!r}"
        assert "a.md" in msg, f"it must name the file that did not deliver: {msg!r}"
        assert "ghost" in msg, f"it must name the promise word that came up empty: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_promise_tokens_support_english_words():
    """i18n: English promises must tokenize into content words.

    The Chinese path splits on \\W and keeps whole phrases; the English path
    splits on \\W into words, so stopwords such as the/of/to must be filtered
    out -- otherwise a failed promise looks fulfilled because a stopword matched.
    """
    tokens = refs_guard._promise_tokens(
        "change the claim differential -> read references/a.md's judge-order section")
    for word in ("claim", "differential", "judge", "order"):
        assert word in tokens, f"English content word not tokenized: {word} not in {tokens}"
    for stop in ("the", "read"):
        assert stop not in tokens, f"English stopword/action word counted as promise: {stop} in {tokens}"


def test_pointer_promises_leaves_missing_target_to_dead_links():
    """A pointer to a file that does not exist is no_dead_links' territory:
    nothing goes red here, nothing is reported twice, and nothing enters
    SKIP_LOG — reporting twice dresses one dead link as two diseases, and
    suspending it invents a state that does not exist."""
    skill = green_skill() + "\nChange the pointer form → read the pointer section of references/ghost.md → stops dead links"
    d = make_repo({"SKILL.md": skill, **green_refs()})
    try:
        _clear_logs()
        assert_pointer_promises(d)
        assert refs_guard.SKIP_LOG == []
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


def test_pointer_promises_red_when_pointer_bares_no_promise():
    """The pointer line yields no content word after stripping the file name →
    the promise cannot be reconciled, red. The three-part form only guarantees
    that arrows exist; this guarantees that the words the arrows point at are
    checkable (the red cause in live-repo acceptance mutation ⑥a)."""
    skill = green_skill().replace(
        "Change something in the claim differential → read the four-quadrant section of references/a.md → stops a zero readout being read as a pass",
        "→ read references/a.md → stops a zero readout being read as a pass")
    d = make_repo({"SKILL.md": skill, **green_refs()})
    try:
        with raises(RefsError) as e:
            assert_pointer_promises(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "SKILL.md:8" in msg, f"it must name the line of the wordless pointer: {msg!r}"
        assert "[RG:POINTER_PROMISE_EMPTY]" in msg, f"it must say the promise is empty: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_pointer_promises_multi_pointer_line_reports_own_trigger():
    """A line with several pointers (chained "read the section of a.md → stops
    drift; change the differential core → read the section of b.md"): the
    trigger segment of the 2nd+ pointer is extracted independently and no longer
    mistakenly reuses the line-start segment — b.md's red text reports its own
    trigger words "change the differential core" and must not put the first
    pointer's trigger words "change the receipt handover" on its head (F2 review
    counter-example). The green direction is verified too: both pointers'
    promises are delivered in their targets' bodies."""
    line = ("Change the receipt handover → read the reconciliation section of references/a.md → stops drift;"
            "change the differential core → read the four-quadrant section of references/b.md → stops errors")
    refs = {
        "references/a.md": "# Receipt reconciliation\n\nThe reconciliation block compares expected/surprise key by key.",
        "references/b.md": "# Four-quadrant readout\n\nHow each of the four quadrants is read.",
    }
    d = make_repo({"SKILL.md": "# Skill\n\n" + line, **refs})
    try:
        assert_pointer_promises(d)                  # each promise is delivered → green
        bad = "# Skill\n\n" + line.replace("four-quadrant section", "ghost section")
        d2 = make_repo({"SKILL.md": bad, **refs})
        try:
            with raises(RefsError) as e:
                assert_pointer_promises(d2)
            msg = str(e.value)
            assert "b.md" in msg, f"it must name the file that did not deliver: {msg!r}"
            assert "core" in msg, f"it must report by the second pointer's own trigger segment: {msg!r}"
            assert "ghost" in msg, f"it must name the promise word that came up empty: {msg!r}"
            assert "receipt" not in msg, \
                f"the first pointer's trigger words must not be put on b.md: {msg!r}"
        finally:
            shutil.rmtree(d2, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_live_skill_pointer_promises_all_fulfilled():
    """Live-repo acceptance (the B11 core): every promise of every pointer in
    SKILL.md is delivered in the target file. This is the live green anchor of
    "promises reconciled forward" — if a pointer's promise words change while
    the file does not follow, it goes red on the spot, and pointers and content
    reconcile both ways from then on."""
    assert_pointer_promises(B4_ROOT)


# ── 8. navigation prose: AGENTS.md must not carry verb-style instructions (M-N1) ─
def test_nav_prose_green_for_plain_map():
    d = _tmpdir()
    try:
        _write(d, "AGENTS.md", NAV_CLEAN)
        assert_no_prose_in_nav(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_prose_red_names_instruction_line():
    """The pattern words are not invented: the two samples the plan names — "Do
    not change P" and "must write red first" — go straight into the fixture,
    anchoring the plan's own wording."""
    nav = nav_table(["| Batch flow | Do not change P, must write red first |"], col2="Notes")
    d = _tmpdir()
    try:
        with raises(RefsError) as e:
            assert_no_prose_in_nav(d, agents_text=nav)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "AGENTS.md:5" in msg, f"it must name the line holding the instruction: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_prose_skips_when_agents_missing():
    """AGENTS.md is a B4 artifact: before B4 it SKIPs and leaves a trace —
    silence is not allowed."""
    d = _tmpdir()
    try:
        _clear_logs()
        assert_no_prose_in_nav(d)
        assert any("AGENTS.md" in s for s in refs_guard.SKIP_LOG), \
            f"the SKIP must name the target file: {refs_guard.SKIP_LOG!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


# ── 9. navigation dead links: path cells must exist (M-N2) ─────────────────
def test_nav_links_green_when_cells_resolve():
    d = _tmpdir()
    try:
        _write(d, "AGENTS.md", NAV_CLEAN)
        _write(d, "SKILL.md", green_skill())
        _write(d, "scripts/breakingdiff.py", "# core entry")
        assert_nav_links_exist(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_links_red_names_dead_cell_path():
    nav = nav_table(["| Lost item | scripts/ghost.py |"])
    d = _tmpdir()
    try:
        _write(d, "AGENTS.md", nav)
        with raises(RefsError) as e:
            assert_nav_links_exist(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "AGENTS.md:5" in msg, f"it must name the line of the dead cell: {msg!r}"
        assert "ghost.py" in msg, f"it must name the missing path: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_links_skips_when_agents_missing():
    d = _tmpdir()
    try:
        _clear_logs()
        assert_nav_links_exist(d)
        assert any("AGENTS.md" in s for s in refs_guard.SKIP_LOG)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


# ── 10. line-count warning: AGENTS.md lines ∉ [40,120] → warn, no raise ─────
def test_nav_line_count_quiet_at_both_bounds():
    """[40,120] is a closed interval: both endpoints are quiet; only going
    outside raises the warning."""
    d = _tmpdir()
    try:
        _clear_logs()
        _write(d, "AGENTS.md", nav_with_lines(40))
        warn_nav_line_count(d)
        _write(d, "AGENTS.md", nav_with_lines(120))
        warn_nav_line_count(d)
        assert refs_guard.WARN_LOG == [], f"inside the band must not warn: {refs_guard.WARN_LOG!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


def test_nav_line_count_warns_below_floor():
    d = _tmpdir()
    try:
        _clear_logs()
        _write(d, "AGENTS.md", nav_with_lines(39))
        warn_nav_line_count(d)                # not raising is itself the criterion of this test
        assert any("AGENTS.md" in s and "39" in s for s in refs_guard.WARN_LOG), \
            f"the warning must leave a trace and report the actual count: {refs_guard.WARN_LOG!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


def test_nav_line_count_warns_above_ceiling():
    d = _tmpdir()
    try:
        _clear_logs()
        _write(d, "AGENTS.md", nav_with_lines(121))
        warn_nav_line_count(d)
        assert any("121" in s for s in refs_guard.WARN_LOG), \
            f"going above the ceiling must warn: {refs_guard.WARN_LOG!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


def test_nav_line_count_skips_when_agents_missing():
    d = _tmpdir()
    try:
        _clear_logs()
        warn_nav_line_count(d)
        assert any("AGENTS.md" in s for s in refs_guard.SKIP_LOG)
        assert refs_guard.WARN_LOG == [], "SKIP is not warn; do not mix it into the warning record"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


# ── 11. hooks pairing: the two test files must exist together (M-H4) ───────
def test_hooks_pair_green_when_both_exist():
    d = _tmpdir()
    try:
        _write(d, "scripts/hooks_contract_test.py", "")
        _write(d, "scripts/hook_entry_test.py", "")
        assert_hooks_contract_pair(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_hooks_pair_red_names_the_missing_half():
    d = _tmpdir()
    try:
        _write(d, "scripts/hooks_contract_test.py", "")
        with raises(RefsError) as e:
            assert_hooks_contract_pair(d)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "hook_entry_test.py" in msg, f"it must name the missing half: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_hooks_pair_skips_until_contract_test_lands():
    """hooks_contract_test.py is a B5 artifact: while it is absent the check
    SKIPs (naming the file it waits for), and once B5 lands it automatically
    turns into a real check. Both stages are pinned."""
    d = _tmpdir()
    try:
        _clear_logs()
        assert_hooks_contract_pair(d)                     # neither exists
        _write(d, "scripts/hook_entry_test.py", "")
        assert_hooks_contract_pair(d)                     # only half exists
        assert any("hooks_contract_test.py" in s for s in refs_guard.SKIP_LOG), \
            f"the SKIP must name the file being waited for: {refs_guard.SKIP_LOG!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


# ── 12. changing SKILL requires changing CHANGELOG (M-D8, injected change list) ─
def test_changelog_red_when_skill_changed_alone():
    with raises(RefsError) as e:
        assert_changelog_on_skill_change(["SKILL.md", "scripts/refs_guard.py"])
    msg = str(e.value)
    assert "[refs_guard]" in msg
    assert "SKILL.md" in msg and "CHANGELOG.md" in msg, f"it must name both sides: {msg!r}"


def test_changelog_green_when_both_changed():
    assert_changelog_on_skill_change(["SKILL.md", "CHANGELOG.md"])


def test_changelog_green_when_skill_untouched():
    assert_changelog_on_skill_change(["scripts/refs_guard.py", "references/a.md"])


def test_changelog_green_when_nothing_changed():
    assert_changelog_on_skill_change([])


def test_changelog_matches_paths_with_backslashes():
    """git speaks forward slashes while an injector may hand backslashes — a
    separator difference must not let "changed SKILL without changing
    CHANGELOG" slip through."""
    with raises(RefsError):
        assert_changelog_on_skill_change(["src\\SKILL.md"])


# ── empty set does not blow up: an empty references/ is the input most easily
#    hit by an index error ───────────────────────────────────────────────────
def test_empty_references_dir_passes_all_file_scans():
    d = _tmpdir()
    try:
        _write(d, "SKILL.md", "# Empty repo\n\nNo pointers.")
        os.makedirs(os.path.join(d, "references"))
        assert_no_dead_links(d)
        assert_no_orphans(d)
        assert_no_reference_cross_links(d)
        assert_toc_required(d)
        assert_no_host_vars_in_references(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── CLI: run_checks summary + three exit tiers + main printing ──────────────
def _boom():
    raise ZeroDivisionError("injected runtime error")


def test_run_checks_green_fixture_exit_zero_with_skips_listed():
    """The all-green fixture walks the whole default surface: exit 0, zero red,
    the check surface equal to the frozen list key by key, and every SKIP named
    in the trace. The list grew to 14 by the B4 scheduler ruling, then to 12
    after B10 retired two invariant checks, then to 13 after B11 added
    pointer-promise reconciliation (M-N3/N4 are on the default surface so a
    programmatic consumer calling run_checks(root) cannot silently skip them) —
    only the key set is pinned, not each key's color; the expansion rationale is
    registered in the DEFAULT_CHECKS comment."""
    d = make_repo()
    try:
        _clear_logs()
        rep = run_checks(d)
        _clear_logs()
        assert set(rep) == RUN_CHECK_KEYS, f"summary structure drifted: {set(rep) ^ RUN_CHECK_KEYS}"
        assert rep["exit_code"] == 0, f"the all-green fixture should be 0: {rep['reds']}"
        assert rep["reds"] == []
        assert set(rep["checks"]) == DEFAULT_CHECKS, \
            f"the default check surface must be exactly 14: {set(rep['checks']) ^ DEFAULT_CHECKS}"
        assert all(st in ("pass", "skip") for st in rep["checks"].values())
        joined = "\n".join(rep["skips"])
        assert "AGENTS.md" in joined, "the navigation checks' SKIP must name its target"
        assert "hooks_contract_test.py" in joined, "the hooks pairing SKIP must name its target"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_checks_pointer_form_active_by_default():
    """M-P3 is active by default since B8 (spec D4): run_checks runs it without
    pointer_form_active. The all-green fixture (all pointers three-part) → pass,
    and the SKIP record must no longer contain an assert_pointer_form suspended
    entry — with the suspended branch deleted, that record must disappear."""
    d = make_repo()
    try:
        _clear_logs()
        rep = run_checks(d)
        _clear_logs()
        assert rep["checks"]["assert_pointer_form"] == "pass", \
            f"M-P3 should be active by default and the all-green fixture should pass: {rep['checks']['assert_pointer_form']!r}"
        assert all("assert_pointer_form" not in s for s in rep["skips"]), \
            f"no suspended SKIP may remain after activation: {rep['skips']!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        _clear_logs()


def test_run_checks_pointer_form_red_by_default_without_flag():
    """The other half of default activation: the red fixture (one-arrow pointer)
    must go red without passing pointer_form_active. If the default were still
    False, this would sneak out as skip with exit 0 — the suspended state coming
    back to life shows up on the spot."""
    skill = green_skill().replace(
        "Change something in the claim differential → read the four-quadrant section of references/a.md → stops a zero readout being read as a pass",
        "Change something in the claim differential → read the four-quadrant section of references/a.md")
    d = make_repo({"SKILL.md": skill, **green_refs()})
    try:
        rep = run_checks(d)
        assert rep["checks"]["assert_pointer_form"] == "red", \
            f"the red fixture must go red under the default run: {rep['checks']['assert_pointer_form']!r}"
        assert rep["exit_code"] == 1, f"something red is 1: {rep['exit_code']}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_checks_red_fixture_exit_one_with_attribution():
    skill = green_skill().replace(
        "Change something in the claim differential → read the four-quadrant section of references/a.md → stops a zero readout being read as a pass",
        "Change something in the claim differential → read the four-quadrant section of references/a.md")
    d = make_repo({"SKILL.md": skill, **green_refs()})
    try:
        rep = run_checks(d, pointer_form_active=True)
        assert rep["exit_code"] == 1
        assert rep["checks"]["assert_pointer_form"] == "red"
        assert len(rep["reds"]) == 1, f"the red fixture should produce exactly one red: {rep['reds']}"
        name, msg = rep["reds"][0]
        assert name == "assert_pointer_form", f"the red must be attributed to the check name: {name}"
        assert "SKILL.md:8" in msg, f"the red text must be locatable: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_checks_runtime_error_maps_to_two():
    """RefsError is gate semantics (1); any other exception is a runtime error
    (2) — business failure and "did not run" must be separated, following
    receipt.py's three-tier exit codes."""
    d = make_repo()
    try:
        rep = run_checks(d, checks=[("ok", lambda: None), ("boom", _boom)])
        assert rep["exit_code"] == 2, f"a non-RefsError must count as a runtime error: {rep}"
        assert rep["checks"]["ok"] == "pass"
        assert rep["checks"]["boom"] == "error"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_main_exit_codes_and_skip_printing():
    """main is the CLI facade: the three tiers 0/1/2, plus SKIP must be printed
    (the last link of the no-silence chain — a log that is not printed is still
    invisible to people)."""
    green = make_repo()
    red = make_repo({
        "SKILL.md": green_skill()
        + "\n\nChange the pointer form → read the pointer section of references/ghost.md → stops dead links",
        **green_refs()})
    missing_parent = _tmpdir()
    missing = os.path.join(missing_parent, "absent-dir")
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            # Scoped call: the collector def main() at the bottom of this file
            # rebinds this name, so a bare call resolves to the collector and
            # blows up — the module attribute is not affected by that rebinding.
            code = refs_guard.main(root=green)
        assert code == 0
        printed = out.getvalue()
        assert "AGENTS.md" in printed and "hooks_contract_test.py" in printed, \
            f"the SKIP must print the target name: {printed!r}"
        assert refs_guard.main(root=red) == 1
        assert refs_guard.main(root=missing) == 2
    finally:
        shutil.rmtree(green, ignore_errors=True)
        shutil.rmtree(red, ignore_errors=True)
        shutil.rmtree(missing_parent, ignore_errors=True)


# ── 13. agent-visible set boundary: paths exist + no grader-only prefix + no
#        test_ function name (M-N3) ───────────────────────────────────────────
# Division of labor with M-N2: M-N2 checks table cells only (map completeness),
# M-N3 checks the full text (visible-set boundary). Each of the three
# sub-criteria has its own red fixture and none substitutes for another — a
# missing line number may have been caught by the prefix check instead, a
# missing path by the test_ check; every source of false green must be closed.
def test_agent_manifest_red_when_text_path_missing():
    """A repo-relative path anywhere in the full text (not just tables, not just
    code blocks) must exist. The red fixture puts one dead path on a prose line,
    and the text must name AGENTS.md:line and the missing path."""
    nav = "\n".join([
        "# Navigation", "",
        "Read scripts/ghost.py to change the core.",          # line 3: prose, not a table, dead path
    ])
    d = _tmpdir()
    try:
        with raises(RefsError) as e:
            refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "AGENTS.md:3" in msg, f"it must name the line holding the dead path: {msg!r}"
        assert "ghost.py" in msg, f"it must name the missing path: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agent_manifest_red_on_probes_prefix():
    """probes/ belongs to grader_read_set and is forbidden in the agent-visible
    set. It must go red anywhere in AGENTS.md, not only in a table cell."""
    nav = "# Navigation\n\nProbes live in probes/something.json."
    d = _tmpdir()
    try:
        with raises(RefsError) as e:
            refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
        assert "probes/" in str(e.value), f"it must name the forbidden prefix: {e.value!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agent_manifest_red_on_evidence_prefix():
    nav = "# Navigation\n\nEvidence is in evidence/something."
    d = _tmpdir()
    try:
        with raises(RefsError):
            refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agent_manifest_red_on_test_function_name_in_prose():
    """A test_ function name is assertion content; outside a command-line
    context it means the grading map was written into the navigation — P11
    refinement, must go red. A test file name on a command line is not in
    scope."""
    nav = "# Navigation\n\nGuarded by the test_spec_files_enumerates assertion."
    d = _tmpdir()
    try:
        with raises(RefsError) as e:
            refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
        assert "test_spec_files_enumerates" in str(e.value), \
            f"it must name the leaked assertion function: {e.value!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agent_manifest_allows_test_filename_in_command_line():
    """A test file name on a command line is allowed by P11 (it has to be run).
    The criterion must tell "a file name on a command line" from "an assertion
    function in prose"; the former passes. The path is built too, isolating the
    test_ rule from the path-existence rule."""
    d = _tmpdir()
    try:
        _write(d, "examples/test_alignment_bootstrap_test.py", "# test")
        nav = "\n".join([
            "# Navigation", "",
            "## Verification", "",
            "    python examples/test_alignment_bootstrap_test.py",
        ])
        refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agent_manifest_ignores_external_urls():
    """An external URL is not a repo-relative path:
    https://example.com/docs/page.md would be cut by the path regex into
    "example.com/docs/page.md" and looked up on disk, a false dead link (B4
    review evidence). Tokens starting with scheme:// are exempt as a whole; a
    real dead path on the same line is still judged, not exempted."""
    d = _tmpdir()
    try:
        nav = "\n".join([
            "# Navigation", "",
            "The spec source is https://example.com/docs/page.md.",
            "Read scripts/ghost.py to change the core.",
        ])
        with raises(RefsError) as e:
            refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
        msg = str(e.value)
        assert "ghost.py" in msg, f"a real dead path must still be named: {msg!r}"
        assert "example.com" not in msg, f"an external link must not be misreported as a dead link: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agent_manifest_allows_test_filename_in_prose():
    """Mentioning a test file name in a non-command context (the whole path
    token) also passes: paths are stripped first, function names judged after —
    "tests are in xxx_test.py" is a file-level pointer, not an assertion map.
    The shape most easily hit as a false assertion function is a file name that
    happens to start with test_, so that shape gets its own test."""
    d = _tmpdir()
    try:
        _write(d, "SKILL.md", "# Skill")
        _write(d, "examples/test_alignment_bootstrap_test.py", "# test")
        nav = ("# Navigation\n\nThe alignment bootstrap test is "
               "examples/test_alignment_bootstrap_test.py; rerun it after changing SKILL.md.")
        refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agent_manifest_green_when_all_paths_resolve_and_clean():
    """Every path really exists (temp files), no grader-only prefix, no test_
    function name in prose → pass. Path existence is checked over the full text,
    not only table cells."""
    d = _tmpdir()
    try:
        _write(d, "scripts/breakingdiff.py", "# core")
        _write(d, "references/writing-claims.md", "# guide")
        nav = "\n".join([
            "# Navigation", "",
            "Read scripts/breakingdiff.py to change the core.",
            "Read references/writing-claims.md before writing a Claim.",
        ])
        refs_guard.assert_agent_visible_manifest(d, agents_text=nav)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 14. zero content overlap between the two files (M-N4) ───────────────────
# AGENTS.md non-blank lines ∩ SKILL.md non-blank lines = ∅. Copying sentences
# means drift — navigation is another map. Title lines count too: the two
# files' title wording must differ.
def test_agents_skill_overlap_red_lists_shared_line():
    skill = "# breakingdiff\n\nN-account claim differential engine."
    nav = "# breakingdiff\n\nThis line differs from the skill body."     # line 1 copies the skill title
    d = _tmpdir()
    try:
        with raises(RefsError) as e:
            refs_guard.assert_no_overlap_between_agents_and_skill(
                d, agents_text=nav, skill_text=skill)
        msg = str(e.value)
        assert "[refs_guard]" in msg
        assert "# breakingdiff" in msg, f"it must name the shared line: {msg!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_agents_skill_overlap_green_when_no_shared_nonblank_line():
    """Empty intersection → pass. Blank lines do not count (layout is not
    content)."""
    skill = "# breakingdiff\n\nN-account claim differential engine."
    nav = "# AGENTS.md navigation\n\nOnly where to go, never how to do it."
    d = _tmpdir()
    try:
        refs_guard.assert_no_overlap_between_agents_and_skill(
            d, agents_text=nav, skill_text=skill)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 15. AGENTS.md live-repo acceptance (C1) + navigation checks activated (C4) ─
B4_ROOT = os.path.dirname(HERE)   # the parent of scripts/ = the repository root

# Five structural anchors: the responsibility statement (the map declaration on
# the first line) plus the five English section titles. The English section
# names are frozen by plan §3.2.2; changing one means the navigation layer
# drifted.
AGENTS_RESPONSIBILITY_ANCHOR = "This file is a map"
AGENTS_SECTION_ANCHORS = (
    "Start here",
    "Repository map",
    "Runtime entry points",
    "Source-of-truth",
    "Verification",
)


def _read_live_agents():
    path = os.path.join(B4_ROOT, "AGENTS.md")
    assert os.path.isfile(path), "AGENTS.md does not exist yet (B4 artifact not landed)"
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_live_agents_md_exists_with_responsibility_and_five_sections():
    """C1: AGENTS.md exists, the responsibility statement is there, the five
    structural anchors are there, and the line count falls in [40,120]. The
    anchors are checked verbatim; the line count counts physical lines, the
    M-N5 warn account."""
    text = _read_live_agents()
    assert AGENTS_RESPONSIBILITY_ANCHOR in text, \
        f"AGENTS.md lacks the responsibility anchor \"{AGENTS_RESPONSIBILITY_ANCHOR}\""
    for anchor in AGENTS_SECTION_ANCHORS:
        assert anchor in text, f"AGENTS.md lacks the structural anchor \"{anchor}\""
    n = len(text.splitlines())
    assert 40 <= n <= 120, f"AGENTS.md line count {n} is outside the [40,120] reference band"


def test_live_agents_md_verification_commands_resolve():
    """C1: command-line files cited in the Verification section must really
    exist — the verification section lists executable commands, and pointing at
    a missing file is false verification. Only .py tokens on indented lines
    inside the Verification section are scanned."""
    text = _read_live_agents()
    lines = text.splitlines()
    in_verification = False
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("## Verification"):
            in_verification = True
            continue
        if in_verification and stripped.startswith("## "):
            break
        if in_verification and ln.startswith("    "):
            for tok in ln.split():
                if tok.endswith(".py"):
                    full = os.path.join(B4_ROOT, tok.replace("/", os.sep))
                    assert os.path.isfile(full), \
                        f"a Verification command references a file that does not exist: {tok}"


def test_live_agents_md_has_no_forbidden_references():
    """C1: the full text must not contain AGENT.md (the pre-2026-10-20 name; now a
    dead link), probes/ or evidence/ (grader-only prefixes), nor any local
    development artifact shape — drive-letter paths, backslash paths, and
    dot-directory names are private to the development platform, not release
    artifacts.

    ORCHESTRATION.md used to sit in this tuple on the ground that it was "a B11
    artifact, a dead link today". That was a fact about the file's absence, not a
    rule about navigation pointing at tutorials, and it expired the moment the
    file landed: the manual is at the repository root, tracked, and until now
    reachable only through README and INDEX, never through the file an agent
    actually opens first. A navigation that hides an existing file is the same
    defect as one that points at a missing file — both make the reader believe
    there is no road. The entry is removed; the manual's own opening line still
    states who its reader is, and the nav row says so as well."""
    text = _read_live_agents()
    for forbidden in ("AGENT.md", "probes/", "evidence/"):
        assert forbidden not in text, \
            f"AGENTS.md contains a forbidden reference \"{forbidden}\""
    for pat, why in ((r"[A-Za-z]:[\\/]", "drive-letter path"),
                     (r"\\", "backslash path"),
                     (r"(?<!\S)\.[A-Za-z]", "dot-directory name")):
        hit = re.search(pat, text)
        assert hit is None, \
            f"AGENTS.md contains a local development artifact shape ({why}): {hit.group(0)!r}"


def test_live_run_checks_navigation_checks_activate_after_agents_lands():
    """C4: after AGENTS.md lands, the three navigation checks (M-N1/N2/N5) no
    longer SKIP; after B8 activates M-P3 it becomes a real check and the live
    repo is all green; the hooks pairing becomes a real check after the B5
    artifact lands. Asserts on run_checks result keys, not on log text."""
    rep = run_checks(B4_ROOT)
    checks = rep["checks"]
    assert checks.get("assert_no_prose_in_nav") != "skip", \
        "M-N1 should activate after AGENTS.md lands"
    assert checks.get("assert_nav_links_exist") != "skip", \
        "M-N2 should activate after AGENTS.md lands"
    assert checks.get("warn_nav_line_count") != "skip", \
        "M-N5 should activate after AGENTS.md lands"
    assert checks.get("assert_pointer_form") == "pass", \
        "M-P3 should be active since B8 and every live pointer should be three-part"
    assert checks.get("assert_hooks_contract_pair") == "pass", \
        "the hooks pairing should become real and pass after B5 lands"


# ── 16. B8 live-repo acceptance: M-P3 active + three-part pointers + suspended
#        records cleared ──────────────────────────────────────────────────────
_LIVE_REF_LINK = re.compile(r"references/[\w.-]+\.md")


def _read_live_skill():
    path = os.path.join(B4_ROOT, "SKILL.md")
    assert os.path.isfile(path), "SKILL.md is not at the repository root; live-repo acceptance has no object"
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_live_skill_pointer_lines_are_three_part():
    """Independent recheck of the B8 hard constraint: every line of the live
    SKILL.md that contains references/*.md must hold → ≥ 2 (trigger condition →
    which section to read → what it solves). The measured denominator on the eve
    of B8: 8 pointer lines (L58/93/165/183/267/298/351/362), all with 0 arrows,
    so this test had to go red; after the B8 relocation the pointer shell took
    over and each line must still hold ≥ 2."""
    text = _read_live_skill()
    total, bad = 0, []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _LIVE_REF_LINK.search(line):
            total += 1
            arrows = line.count("→")
            if arrows < 2:
                bad.append(f"SKILL.md:{lineno} ({arrows} →)")
    assert total >= 1, "no references pointer line found in the live SKILL.md; the scan surface drifted"
    assert not bad, (
        f"the live SKILL.md has {len(bad)}/{total} pointer lines that are not three-part: {bad}")


def test_live_run_checks_fully_clean_after_mp3_activation():
    """B8 acceptance readout (spec §4 first line): the live refs_guard has 0 red,
    0 SKIP, 0 warn. Baseline on the eve of B8: 0 red, 1 SKIP (M-P3 suspended),
    0 warn — after activation the SKIP must be cleared, and no suspended record
    may remain. This is the red-to-green anchor."""
    rep = run_checks(B4_ROOT)
    assert rep["reds"] == [], f"the live repo must not have red: {[n for n, _ in rep['reds']]}"
    assert rep["skips"] == [], \
        f"the live repo must not have SKIP (suspended records cleared after M-P3 activation): {rep['skips']!r}"
    assert rep["warnings"] == [], f"the live repo must not have warn: {rep['warnings']!r}"
    assert rep["checks"]["assert_pointer_form"] == "pass"
    assert rep["exit_code"] == 0


# ── 17. SPEC_FILES contract (the only replacement after the B8 contract suite
#        retired; see CHANGELOG 2026-10-17): spec_files contains
#        writing-claims, has no duplicates, and its paths exist — three
#        reconciliations, evaluated against the real implementation, no text
#        guessing ─────────────────────────────────────────────────────────────
_LIVE_BOOTSTRAP = os.path.join(B4_ROOT, "examples", "test_alignment_bootstrap.py")


def test_live_spec_files_includes_writing_claims_and_has_no_duplicates():
    """Three SPEC_FILES reconciliations: it must contain
    references/writing-claims.md (the S-4/S-5 landing point, where a CATALOG
    phrase lands; a Q-side corpus missing it is a first-order under-report); no
    duplicate entries (registration is not copy-paste); and every path really
    exists. Loading follows the original suite: importlib evaluates the live
    examples/test_alignment_bootstrap.py, and reading in all the corpus files is
    part of the contract under test, not an extra dependency."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_refs_guard_spec_probe",
                                                  _LIVE_BOOTSTRAP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    files = [os.path.relpath(p, B4_ROOT).replace(os.sep, "/")
             for p in mod.SPEC_FILES]
    assert "references/writing-claims.md" in files, \
        f"SPEC_FILES must contain writing-claims.md (the Q-side corpus landing point): {files}"
    dupes = sorted({f for f in files if files.count(f) > 1})
    assert not dupes, f"SPEC_FILES has duplicate entries (registration is not copy-paste): {dupes}"
    for rel in files:
        assert os.path.isfile(os.path.join(B4_ROOT, rel)), \
            f"SPEC_FILES points at a file that does not exist: {rel}"


# ── 14. the two surfaces added after the live-repo measurement ──────────────
# Before this batch the nav-cell check was mounted on AGENTS.md alone, and measured
# 0 path-like cells there — a green over an empty surface. Two things were added:
#   · the check now reads three navigation documents, each against its own base;
#   · a separate check for relative markdown links, the syntax the prose files
#     actually use (the casestudy README has 11 links and 0 path-like cells).
# Both need their own red/green pair, or the extension is unverifiable.


def _md(*lines):
    return "\n".join(lines) + "\n"


def test_nav_links_green_when_every_table_cell_resolves():
    files = {
        "AGENTS.md": _md("| file | note |", "|---|---|",
                         "| `scripts/breakingdiff.py` | core |"),
        "INDEX.md": _md("## scripts/", "", "| file | note |", "|---|---|",
                        "| `scripts/coverage_guard.py` | gate |"),
        os.path.join("casestudy", "README.md"): _md(
            "| file | note |", "|---|---|", "| k8s | case |"),
        "scripts/breakingdiff.py": "x = 1\n",
        "scripts/coverage_guard.py": "y = 2\n",
    }
    d = make_repo(files)
    try:
        _clear_logs()
        assert_nav_links_exist(d)
        assert not refs_guard.WARN_LOG, refs_guard.WARN_LOG
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_links_red_names_document_line_and_dead_cell():
    """The red must carry THREE things or it is unactionable: which document (the
    check no longer reads only AGENTS.md), which line, and which path."""
    files = {
        "AGENTS.md": _md("| file | note |", "|---|---|",
                         "| `scripts/breakingdiff.py` | core |"),
        "INDEX.md": _md("## scripts/", "", "| file | note |", "|---|---|",
                        "| `scripts/ghost.py` | removed upstream |"),
        "scripts/breakingdiff.py": "x = 1\n",
    }
    d = make_repo(files)
    try:
        _clear_logs()
        with raises(RefsError) as e:
            assert_nav_links_exist(d)
        msg = str(e.value)
        assert "INDEX.md" in msg, msg
        assert "ghost.py" in msg, msg
        assert ":5" in msg, msg
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_links_warns_once_when_the_whole_surface_is_empty():
    """The vacuity guard. Before the extension this was the live state and it read
    as a pass. Now it warns — but ONCE for the whole surface, not per document:
    two of the three documents legitimately carry no path-like cell, and a warning
    per document is noise, which is worse than the miss."""
    files = {
        "AGENTS.md": _md("| item | note |", "|---|---|", "| the entry | prose only |"),
        "INDEX.md": _md("| item | note |", "|---|---|", "| another | prose only |"),
    }
    d = make_repo(files)
    try:
        _clear_logs()
        assert_nav_links_exist(d)
        assert len(refs_guard.WARN_LOG) == 1, refs_guard.WARN_LOG
        assert "0 path-like cell" in refs_guard.WARN_LOG[0]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_links_no_warn_when_any_document_has_cells():
    """Too-tight direction: the vacuity warning must not fire while there is still
    something to check. Without this, the warning would become a constant."""
    files = {
        "AGENTS.md": _md("| file | note |", "|---|---|",
                         "| `scripts/breakingdiff.py` | core |"),
        "INDEX.md": _md("| item | note |", "|---|---|", "| another | prose only |"),
        "scripts/breakingdiff.py": "x = 1\n",
    }
    d = make_repo(files)
    try:
        _clear_logs()
        assert_nav_links_exist(d)
        assert not refs_guard.WARN_LOG, refs_guard.WARN_LOG
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_nav_links_directory_cell_counts_as_existing():
    """A cell naming a directory (`examples/data/`) is a real target. Requiring
    isfile would red it for the wrong reason — the noise discipline, applied to
    ourselves."""
    files = {
        "INDEX.md": _md("## examples/", "", "| file | note |", "|---|---|",
                        "| `examples/data/` | corpus |"),
        "examples/data/keep.txt": "x\n",
    }
    d = make_repo(files)
    try:
        _clear_logs()
        assert_nav_links_exist(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_relative_links_green_when_every_href_resolves():
    files = {
        "SKILL.md": green_skill().replace(
            "references/b.md", "references/b.md") + _md(
            "", "See [the case](casestudy/k8s/aligned.py) and [dir](casestudy/k8s/)."),
        **green_refs(),
        "casestudy/k8s/aligned.py": "x = 1\n",
    }
    d = make_repo(files)
    try:
        _clear_logs()
        assert_no_dead_relative_links(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_relative_links_red_names_file_line_and_href():
    """This is the check that would have caught the broken `TEACHING-port.md` link:
    a pointer written into a table and followed into empty space."""
    files = {
        "SKILL.md": green_skill() + _md(
            "", "See [the lesson](casestudy/TEACHING-ghost.md)."),
        **green_refs(),
    }
    d = make_repo(files)
    try:
        _clear_logs()
        with raises(RefsError) as e:
            assert_no_dead_relative_links(d)
        msg = str(e.value)
        assert "TEACHING-ghost.md" in msg, msg
        assert "SKILL.md" in msg, msg
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_relative_links_ignore_external_and_anchor_only_targets():
    files = {
        "SKILL.md": _md("",
                        "[ext](https://example.com/x.md)",
                        "[mail](mailto:a@b.c)",
                        "[anchor](#section-3)",
                        "[local](#nope)"),
        **green_refs(),
    }
    d = make_repo(files)
    try:
        _clear_logs()
        assert_no_dead_relative_links(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_relative_links_catch_a_file_deleted_from_disk():
    """Mutation evidence, too-tight direction: the check must key on disk state,
    not on anything the document asserts about itself. Deleting the target is the
    only mutation; the document is untouched."""
    files = {
        "SKILL.md": green_skill() + _md("", "[case](casestudy/k8s/aligned.py)"),
        **green_refs(),
        "casestudy/k8s/aligned.py": "x = 1\n",
    }
    green = make_repo(files)
    red = make_repo(files)
    try:
        _clear_logs()
        assert_no_dead_relative_links(green)          # green before the mutation
        os.remove(os.path.join(red, "casestudy", "k8s", "aligned.py"))
        with raises(RefsError):
            assert_no_dead_relative_links(red)        # red after
    finally:
        shutil.rmtree(green, ignore_errors=True)
        shutil.rmtree(red, ignore_errors=True)


def test_relative_links_scan_every_markdown_file_not_just_skill():
    """A guard that only reads SKILL.md misses every other document — which is
    where the only dead link in this repository actually lived."""
    d = make_repo({"SKILL.md": green_skill(), **green_refs(),
                   "casestudy/README.md": _md("[gone](k8s/ghost.md)")})
    try:
        _clear_logs()
        with raises(RefsError) as e:
            assert_no_dead_relative_links(d)
        assert "README.md" in str(e.value)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_checks_includes_the_relative_link_check_on_the_default_surface():
    """Registered, not merely importable: a check mounted only on an injection
    channel runs silently never."""
    d = make_repo()
    try:
        _clear_logs()
        rep = run_checks(d)
        _clear_logs()
        assert "assert_no_dead_relative_links" in rep["checks"], rep["checks"]
        assert "assert_nav_links_exist" in rep["checks"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
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
          + (f"; failures: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

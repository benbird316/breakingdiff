# -*- coding: utf-8 -*-
"""
reanchor red-first tests (3.2 quote ledger re-anchor helper)
==============================================
Frozen contract (this repository's refinement plan landing batch §3.2; see the
matching CHANGELOG.md entry):
  · an independent small script (does not touch compare): input a quote ledger + a
    new-file path;
  · output three states — alive (quote verbatim in the new file) / dead (not
    present) / suspect new position (difflib nearest neighbor + line candidates);
  · candidates only, confirmation belongs to a human; never edit the ledger
    automatically.

This file is a red-first test: scripts/reanchor.py did not exist yet, and each test
goes explicitly red with NotImplementedError (each red cause maps to a contract
clause, see each test's docstring). Once the implementation lands, the guard stops
applying automatically and all assertions take real effect — no always-true
placeholder anywhere.

Ledger shape (why the fixture uses Claim; the grounds are recorded in the matching
CHANGELOG.md entry):
  the repository contains no ledger entity file; the "ledger" in the docs
  (SKILL.md/ORCHESTRATION.md) is the rejected "cannot block" ledger, unrelated to
  quote. The only data structure in the repository that carries quote is
  breakingdiff.Claim — the consumer of provenance.verify (.name/.quote/.source), and
  2.2's line anchors (L120-L124 prefixes) also live on Claim. So this test pins the
  ledger as a Claim sequence. P4's qa_claims_v1.yaml is another ledger (the Q list,
  owned by q_ledger_check, 4.1) and is outside this helper's input surface.

Test contract (the API shape the implementation must obey, frozen by this test;
changing the shape = the red cause turns into "implementation vs contract", which
goes to the scheduler for a decision):

    import reanchor
    results = reanchor.reanchor(entries, new_path)

  · entries : a Claim sequence, duck-typed to read only .name/.quote (the same shape
    as provenance.verify's claim: Any; a SimpleNamespace can be fed in too, see the
    probe in the no-side-effects case);
  · new_path : the new file path (str);
  · returns list[dict], in input order, each entry containing at least four keys:
      name       — ledger entry identity (the anchor that matches entry by entry)
      state      — one of the module constants ALIVE / DEAD / SUSPECT (a closed
                   three-state set, constants distinct)
      line       — the line number where quote sits when alive (1-based int; a
                   multiline quote takes its start line); None when dead / suspect
      candidates — line candidates for a suspect new position, list[int] (1-based,
                   pointing at real lines in the new file); dead must be an empty
                   list (the dead/suspect boundary)
  · line numbers are 1-based: the same writing family as 2.2's quote_source_ref
    L-prefixed line anchors.
  · the threshold is not frozen (implementation detail): only the boundary behavior
    is frozen — a near neighbor = SUSPECT with non-empty candidates; no near
    neighbor = DEAD with empty candidates. The fixture's near/far neighbor gap is
    measured with difflib (suspect 0.826 vs dead 0.293, see the fixture self-check
    case), so any threshold in (0.3, 0.7) separates them.
  · empty file / empty ledger do not crash and have explicit output (empty file:
    everything dead; empty ledger: empty report).

Red-cause distribution in the red-first phase: scripts/reanchor.py missing → each
test raises NotImplementedError (_impl guard); when the module exists but lacks the
entry point or a three-state constant, the red cause names the missing API.

No pytest dependency. Usage: python scripts/reanchor_test.py
"""
import difflib
import os
import shutil
import sys
import tempfile
import traceback
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from breakingdiff import Claim

try:
    import reanchor as _reanchor_mod
except ImportError:
    _reanchor_mod = None          # red-first phase: the implementation module does not exist yet

_REANCHOR_API = ("reanchor", "ALIVE", "DEAD", "SUSPECT")
REQUIRED_KEYS = {"name", "state", "line", "candidates"}


def _impl():
    """Red-first guard + API access: go explicitly red when the module is missing;
    the cause is "not implemented" rather than an ImportError crashing the whole
    file — that way each test's red cause maps to its own contract clause. Once the
    implementation lands, this guard stops applying automatically."""
    if _reanchor_mod is None:
        raise NotImplementedError(
            "reanchor module does not exist (3.2 quote ledger re-anchor helper, red-first phase)")
    missing = [n for n in _REANCHOR_API if not hasattr(_reanchor_mod, n)]
    if missing:
        raise NotImplementedError(
            f"reanchor is missing API {missing} (3.2 frozen contract: entry reanchor + three state constants)")
    return _reanchor_mod


# ── fixture: the new file (LF line endings, written as binary, no line-ending assumption) ─────────
NEW_FILE_LINES = [
    "# Order flow spec",                                              # L1
    "",                                                               # L2
    "The user must sign in before placing an order.",                 # L3 — drifted line: the old version read "The user must sign in and then place an order."
    "Orders are archived within seven days of creation.",             # L4
    "",                                                               # L5
    "Refunds are processed within three business days.",              # L6
    "",                                                               # L7
    "A notification email is sent when the order ships.",             # L8
]
NEW_FILE_TEXT = "\n".join(NEW_FILE_LINES) + "\n"
NEW_FILE_BYTES = NEW_FILE_TEXT.encode("utf-8")

Q_ALIVE_SINGLE = "Orders are archived within seven days of creation."                            # verbatim at L4
Q_ALIVE_MULTI = "Orders are archived within seven days of creation.\n\nRefunds are processed within three business days."   # verbatim at L4-L6
Q_SUSPECT = "The user must sign in and then place an order."                                 # verbatim miss; near neighbor L3
Q_DEAD = "WeChat Pay and Alipay are supported."                                    # no near neighbor in the text

REPEAT_FILE_TEXT = "\n".join([
    "Header note",                       # L1
    "A notification email is sent when the order ships.",     # L2 — the same sentence occurs twice
    "Middle note",                       # L3
    "A notification email is sent when the order ships.",     # L4
]) + "\n"


def _tmpdir():
    return tempfile.mkdtemp(prefix="bd_reanchor_test_")


def _write_new_file(d, text=None, name="spec_v2.md"):
    path = os.path.join(d, name)
    with open(path, "wb") as f:                    # binary write: Windows does not change line endings
        f.write(NEW_FILE_BYTES if text is None else text.encode("utf-8"))
    return path


def mk_entry(name, quote):
    """A ledger entry = a Claim (the provenance consumer shape, grounds in the module
    docstring). The predicate/domain are a minimal stub unrelated to the ledger: the
    re-anchor helper should consume only .name/.quote."""
    return Claim(name=name, predicate=lambda x: True, applies=lambda x: True,
                 domain_note="quote ledger entry",
                 source="spec/order-flow-spec.md", quote=quote)


def mk_mixed_ledger():
    """Mixed ledger: all three states present and deliberately interleaved (alive
    single / suspect / alive multi / dead) — if the output reorders by state instead
    of input order, "matches entry by entry" goes red on the spot."""
    return [mk_entry("alive single", Q_ALIVE_SINGLE),
            mk_entry("suspect", Q_SUSPECT),
            mk_entry("alive multi", Q_ALIVE_MULTI),
            mk_entry("dead", Q_DEAD)]


def _assert_report_shape(r):
    """Per-entry report shape: a dict with all four contract keys (extra keys from the
    implementation are allowed; missing keys are not)."""
    assert isinstance(r, dict), "a per-entry result must be a dict report; do not return the ledger entry as is"
    assert REQUIRED_KEYS <= set(r), f"the report lacks a contract key: {REQUIRED_KEYS - set(r)}"


# ── 0. fixture control-state self-check (green first: only when the control states are true are the later cases testing the target state) ──────
def test_fixture_control_states_hold():
    """The fixture self-check does not depend on the implementation: the alive quote
    is verbatim present, the dead/suspect quotes are not; the suspect has a single
    high-similarity near neighbor (L3), and the dead quote's best similarity is too
    low to latch onto under any reasonable threshold. The gap is the evidence that
    the three-state boundary criterion can separate them; the threshold value is not
    frozen."""
    assert Q_ALIVE_SINGLE in NEW_FILE_TEXT
    assert Q_ALIVE_MULTI in NEW_FILE_TEXT
    assert Q_SUSPECT not in NEW_FILE_TEXT
    assert Q_DEAD not in NEW_FILE_TEXT
    best3 = max((difflib.SequenceMatcher(None, Q_SUSPECT, ln).ratio(), i)
                for i, ln in enumerate(NEW_FILE_LINES, 1) if ln.strip())
    assert best3[1] == 3 and best3[0] >= 0.7, \
        f"the suspect fixture must have a single near neighbor L3 with high similarity; measured {best3}"
    bestd = max((difflib.SequenceMatcher(None, Q_DEAD, ln).ratio(), i)
                for i, ln in enumerate(NEW_FILE_LINES, 1) if ln.strip())
    assert bestd[0] <= 0.3, f"the dead fixture must have no near neighbor to latch onto; measured {bestd}"


# ── 1. alive: quote verbatim in the new file → alive state + line location (contract three states · alive) ──
def test_alive_quote_located_with_line_number():
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d)
        res = m.reanchor([mk_entry("alive single", Q_ALIVE_SINGLE)], path)
        assert isinstance(res, list) and len(res) == 1, "one input entry must yield one result"
        r = res[0]
        _assert_report_shape(r)
        assert r["name"] == "alive single", "the report must carry the ledger entry identity"
        assert r["state"] == m.ALIVE, \
            f"a quote verbatim in the new file must be judged alive; got {r['state']!r}"
        assert isinstance(r["line"], int), f"alive must give a line location (int); got {r['line']!r}"
        assert r["line"] == 4, f'"{Q_ALIVE_SINGLE}" is on line 4 of the new file; got {r["line"]}'
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 2. alive · multiline quote: the line number is the start line (API assumption, see docstring) ─────
def test_alive_multiline_quote_reports_start_line():
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d)
        res = m.reanchor([mk_entry("alive multi", Q_ALIVE_MULTI)], path)
        r = res[0]
        _assert_report_shape(r)
        assert r["state"] == m.ALIVE, "a multiline quote verbatim present must also be judged alive"
        assert r["line"] == 4, f"the location of a multiline quote (L4-L6) must be its start line L4; got {r['line']}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 3. dead: the quote is absent with no near neighbor → dead state, candidates must be empty (three-state boundary) ──
def test_dead_quote_has_no_candidates():
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d)
        res = m.reanchor([mk_entry("dead", Q_DEAD)], path)
        r = res[0]
        _assert_report_shape(r)
        assert r["state"] == m.DEAD, \
            f"a quote absent with no near neighbor must be judged dead; got {r['state']!r}"
        assert r["candidates"] == [], \
            "the dead/suspect boundary: no near neighbor means no candidates; with candidates it should be judged suspect"
        assert r["line"] is None, "a dead entry has no new anchor; line must be an explicit None, not a leftover value"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 4. suspect new position: verbatim miss but a similar passage exists → suspect state + line candidates ───────
def test_drifted_quote_yields_candidate_lines():
    """Contract three states · suspect new position: surrounding text drifted so the
    quote no longer matches verbatim, and difflib's nearest neighbor gives line
    candidates. Candidates are only a suggestion: the report contains no rewrite
    action (see the no-side-effects case)."""
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d)
        res = m.reanchor([mk_entry("suspect", Q_SUSPECT)], path)
        r = res[0]
        _assert_report_shape(r)
        assert r["state"] == m.SUSPECT, \
            f"a verbatim miss with a single high-similarity near neighbor must be judged suspect; got {r['state']!r}"
        assert isinstance(r["candidates"], list) and r["candidates"], \
            "a suspect new position must give line candidates; an empty candidate list misjudges suspect as dead"
        assert 3 in r["candidates"], \
            f"the drifted line is L3 (measured similarity 0.826); candidates must cover it; got {r['candidates']}"
        for c in r["candidates"]:
            assert isinstance(c, int) and 1 <= c <= len(NEW_FILE_LINES), \
                f"a candidate must be a real line number in the new file (1..{len(NEW_FILE_LINES)}); got {c!r}"
        assert r["line"] is None, "before a candidate is confirmed there is no new anchor, so line must be None"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 5. candidates only: no "already updated" side effect at all (contract: confirmation belongs to a human, never edit the ledger automatically) ──
def test_candidates_only_no_side_effects():
    """Three structural assertions: the new file's bytes are unchanged (re-anchoring is
    a read-only report and must not write back); ledger entries are not rewritten (use
    a mutable SimpleNamespace probe — Claim's frozen structure itself cannot change,
    so it cannot show whether the helper intended to act; SimpleNamespace also
    verifies duck-typing); the return value is a report copy, not the ledger objects
    themselves. States are closed to three, with no "already updated" state."""
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d)
        entries = [SimpleNamespace(name="alive single", quote=Q_ALIVE_SINGLE),
                   SimpleNamespace(name="suspect", quote=Q_SUSPECT),
                   SimpleNamespace(name="dead", quote=Q_DEAD)]
        before = [(e.name, e.quote) for e in entries]
        res = m.reanchor(entries, path)
        with open(path, "rb") as f:
            assert f.read() == NEW_FILE_BYTES, "the new file was modified: the re-anchor helper has no right to write back"
        assert [(e.name, e.quote) for e in entries] == before, \
            "a ledger entry was modified: confirmation belongs to a human, candidates must not be recorded automatically"
        assert res is not entries, "the return value must be a report; do not hand the input ledger back as the result"
        assert all(r is not e for r, e in zip(res, entries)), \
            "a report entry must not be the ledger entry object itself (a candidate is not a confirmation; replacing the object is an unauthorized rewrite)"
        closed = {m.ALIVE, m.DEAD, m.SUSPECT}
        assert len(closed) == 3 and all(r["state"] in closed for r in res), \
            'states must be one of three: a fourth state (such as "already updated") is a signal of an unauthorized rewrite'
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 6. mixed ledger: all three states in one batch, matching entry by entry, count conserved ──────────────────
def test_mixed_ledger_conservation_and_per_entry_mapping():
    """Acceptance item 4: input count = sum of the three states; output and input share
    order and names one-to-one; each entry's state matches that entry's fixture
    semantics (not just the counts — the entries must match too)."""
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d)
        entries = mk_mixed_ledger()
        res = m.reanchor(entries, path)
        assert isinstance(res, list) and len(res) == len(entries), \
            f"count conservation: output has {len(res) if isinstance(res, list) else 'not a list'} entries != input {len(entries)}"
        names_in = [e.name for e in entries]
        names_out = [r["name"] for r in res]
        assert names_out == names_in, \
            f"entry-by-entry match: output must share input order and names; got {names_out} vs {names_in}"
        assert len(set(names_out)) == len(names_out), "entry identities are one-to-one; no merging by duplicate name"
        closed = {m.ALIVE, m.DEAD, m.SUSPECT}
        assert len(closed) == 3, "the three state constants must be distinct; two overlapping means collapsed classification"
        states = [r["state"] for r in res]
        assert all(s in closed for s in states), \
            f"a state outside the three appeared: {set(states) - closed}"
        assert states.count(m.ALIVE) == 2 and states.count(m.SUSPECT) == 1 \
            and states.count(m.DEAD) == 1, \
            f"three-state distribution drifted (expected 2/1/1): {states}"
        by_name = {r["name"]: r for r in res}
        assert by_name["alive single"]["state"] == m.ALIVE \
            and by_name["alive single"]["line"] == 4
        assert by_name["alive multi"]["state"] == m.ALIVE \
            and by_name["alive multi"]["line"] == 4
        assert by_name["suspect"]["state"] == m.SUSPECT \
            and 3 in by_name["suspect"]["candidates"]
        assert by_name["dead"]["state"] == m.DEAD \
            and by_name["dead"]["candidates"] == []
        for r in res:
            _assert_report_shape(r)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 7. boundary: empty ledger → empty report, no crash ─────────────────────────────
def test_empty_ledger_returns_empty_report():
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d)
        res = m.reanchor([], path)
        assert res == [], "an empty ledger needs explicit output (empty report); no exception or None"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 8. boundary: empty file → everything dead, no candidates, no crash ─────────────────────
def test_empty_file_classifies_everything_dead_without_crash():
    """Nothing is verbatim present in an empty file, and there are no lines for
    difflib to latch onto — the three-state criterion produces all-dead on its own,
    with no special-case branch; explicit output means reaching a conclusion per entry
    without crashing."""
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d, text="")
        res = m.reanchor([mk_entry("should be alive", Q_ALIVE_SINGLE),
                          mk_entry("should be dead", Q_DEAD)], path)
        assert isinstance(res, list) and len(res) == 2, "an empty file must not crash: conclude per entry"
        for r in res:
            _assert_report_shape(r)
            assert r["state"] == m.DEAD, \
                f"no quote can be verbatim in an empty file; must be judged dead; got {r['state']!r}"
            assert r["candidates"] == [], "an empty file has no lines to latch onto; candidates must be empty"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 9. an alive line number must point at a real occurrence (first/last not frozen when repeated) ─────
def test_repeated_occurrence_line_points_at_real_hit():
    """A wrong line anchor is worse than none — line drift is exactly the disease. When
    the same sentence occurs twice, choosing the first or the last is not frozen, but
    the line number given must really be a line where the quote sits."""
    m = _impl()
    d = _tmpdir()
    try:
        path = _write_new_file(d, text=REPEAT_FILE_TEXT, name="repeat_v2.md")
        res = m.reanchor([mk_entry("repeated occurrence", "A notification email is sent when the order ships.")], path)
        r = res[0]
        _assert_report_shape(r)
        assert r["state"] == m.ALIVE, "verbatim present (in two places) must be judged alive"
        assert r["line"] in (2, 4), \
            f"the line number must point at a real occurrence L2/L4; got {r['line']}"
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
          + (f", failed: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

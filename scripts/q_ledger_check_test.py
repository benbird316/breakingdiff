# -*- coding: utf-8 -*-
"""
q_ledger_check red-first tests (4.1 Q ledger versioning and precise gap detection)
==========================================================
Frozen contract (this repository's refinement plan landing batch P4; see the matching
CHANGELOG.md entry):
  · the Q ledger is a standalone file qa_claims_v1.yaml, four keys per entry:
      - id: R-001 / status: implemented|superseded|draft /
        source_spec: path/to/spec.md@<40-char sha> / quote: "verbatim commitment"
  · the reverse check = precise gap detection (not an order-of-magnitude comparison):
    each commitment item from the spec diff is looked up by ID in the Q ledger; a miss
    is marked unknown and put in the report; warning level does not block;
  · boundary condition: precise gap detection presupposes that spec commitment items
    have stable machine-parseable IDs (such as R-001); free-form markdown with no
    extractable items → degrade to a hint-level order-of-magnitude note, do not do
    precise gap detection, and the implementation must declare this precondition in
    its documentation.

Warning blocking semantics (established before writing the tests, 2026-10-16):
  scripts/breakingdiff.py has no warning/severity machinery at all (grep find zero
  matches); the ⚠️ in reports is rendering decoration; coverage_guard.py's design note
  says "raise rather than warn"; delivery_gate.py always raises
  CoverageError/DeliveryError. In other words the repository's existing machinery has
  only one tier, raise to block, with no warning tiering precedent. Contract 4.1's
  "warning level does not block" lands, grounded in the real machinery, as a behavioral
  assertion: with an unknown gap check_q_ledger **raises nothing** and returns normally,
  and the gap is presented as an explicit data state (unknown_ids) and report text —
  raise means block, no raise means no block. But structural errors (missing quote /
  sha shorter than 40 chars) must fail loudly (raise), aligned with coverage_guard's
  repository discipline that "missing data must become a non-zero cost".

Test contract (the API shape the implementation must obey, frozen by this test):

    from q_ledger_check import check_q_ledger, render_q_ledger
    res = check_q_ledger(spec_diff_text: str, qa_claims_path: str)

  · res.mode        : str   "precise" = precise gap detection | "hint" = degraded
                            order-of-magnitude note | "unavailable" = Q ledger missing
                            or empty (explicit state, not silent)
  · res.unknown_ids : list  in precise mode, IDs the spec has and the ledger lacks
                            (ascending); hint mode must be empty (no precise gap
                            detection)
  · res.covered_ids : list  in precise mode, IDs matched on both sides (ascending)
  · res.hint        : str   a human-readable note (magnitude/reason) in hint/unavailable
                            mode, non-empty; may be an empty string in precise mode
  · render_q_ledger(res) -> str   render the report; in precise mode with gaps the
                            report text must contain every unknown ID and the "unknown"
                            marker
  · a structural error raises QLedgerError (a ValueError subclass) whose message
    carries the entry location (id or source_spec); never swallow it into a silent
    degraded return

ID extraction criterion (external grounding on the test side; the implementation may be
broader but not narrower):
  a stable machine-parseable ID = an R-<number> shape occurring in spec_diff_text
  (contract example R-001). The fixture self-check (test 0, green first) verifies the
  criterion itself is decidable — preventing a false red/green caused by a distorted
  fixture.

yaml dependency decision (2026-10-16, see the matching CHANGELOG.md entry):
  the repository has no PyYAML (grep for "import yaml" finds zero matches repository-wide).
  This test has zero yaml parsing dependency: fixtures write the four-key yaml text the
  contract pins directly to a temporary file, and parsing is the implementation's job
  (the contract structure is only a top-level list + four scalar keys, so stdlib
  self-parsing is entirely feasible; prefer adding no new dependency).

This file is a red-first test: scripts/q_ledger_check.py did not exist yet, and every
test except the fixture self-check goes explicitly red with NotImplementedError (each
red cause maps to a contract clause, see the section headings). Once the implementation
lands, the guard stops applying automatically and the assertions take real effect — no
always-true placeholder anywhere.

No pytest dependency. Usage: python q_ledger_check_test.py
"""
import os
import re
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import q_ledger_check
    from q_ledger_check import check_q_ledger, render_q_ledger
except ImportError:
    q_ledger_check = None       # red-first phase: the implementation module does not exist yet
    check_q_ledger = None
    render_q_ledger = None


def _require_impl():
    """Red-first guard: go explicitly red when the module is missing; the cause is
    "not implemented" rather than an ImportError crashing the whole file — each test's
    red cause maps to its own contract clause, and we can verify every assertion is
    loaded with live ammunition. Once the implementation lands, this guard stops
    applying automatically."""
    if check_q_ledger is None:
        raise NotImplementedError(
            "q_ledger_check.check_q_ledger is not implemented "
            "(4.1 Q ledger precise gap detection, red-first phase)")


class raises:
    """Minimal context manager: a stand-in for pytest.raises (same as receipt_test.py)."""

    def __init__(self, exc):
        self.exc, self.value = exc, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"expected {self.exc.__name__} to be raised, but nothing was")
        self.value = ev
        return issubclass(et, self.exc)


# ── fixture constants ─────────────────────────────────────────────────────
SHA40 = "a" * 40
SHA39 = "b" * 39     # structural-error fixture: one character short

# spec-side fixture: diff text containing three commitment items (stable ID shape R-<number>)
SPEC_DIFF_WITH_IDS = """\
+ R-001 support CSV export
+ R-002 timeout is configurable
+ R-003 logs include a timestamp
"""

# spec-side fixture: free-form markdown with no stable ID at all
SPEC_DIFF_FREE_MARKDOWN = """\
## Commitments this time
Support CSV export, make the timeout configurable, and include a timestamp in logs.
See the review record for details.
"""


def qa_entry(eid, status, sha, quote):
    """Build one Q ledger yaml text entry in the contract's four-key structure."""
    return (
        f"- id: {eid}\n"
        f"  status: {status}\n"
        f"  source_spec: docs/spec.md@{sha}\n"
        f"  quote: \"{quote}\"\n"
    )


def write_claims(tmpdir, text):
    """Write the Q ledger text to a temporary yaml file and return its path (contract:
    the ledger is a standalone file)."""
    p = os.path.join(tmpdir, "qa_claims_v1.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


ID_RE = re.compile(r"\bR-\d+\b")


# ── 0. fixture self-check (green first, no implementation dependency): the ID criterion
#      is decidable and the fixtures are not distorted ──
def test_fixture_ids_are_machine_parseable():
    got = set(ID_RE.findall(SPEC_DIFF_WITH_IDS))
    assert got == {"R-001", "R-002", "R-003"}, (
        "distorted fixture: the spec text with IDs must contain exactly three stable IDs; got " + repr(got))
    assert not ID_RE.search(SPEC_DIFF_FREE_MARKDOWN), (
        "distorted fixture: the free markdown fixture must contain no parseable ID, "
        "otherwise the hint degradation case is not testing the target state")


# ── 1. precise gap (contract: a miss is marked unknown and put in the report; warning level does not block) ──
def test_precise_gap_marks_unknown_and_does_not_block():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = write_claims(td, qa_entry("R-001", "implemented", SHA40, "support CSV export")
                         + qa_entry("R-002", "implemented", SHA40, "timeout is configurable"))
        res = check_q_ledger(SPEC_DIFF_WITH_IDS, p)     # must not raise: does not block
    assert res.mode == "precise", (
        "the spec side has stable IDs and the ledger parses, so precise gap detection is "
        "required; got mode=" + repr(res.mode))
    assert res.unknown_ids == ["R-003"], (
        "R-003 is committed on the spec side with no match in the Q ledger and must be marked "
        "unknown; got " + repr(res.unknown_ids))
    assert res.covered_ids == ["R-001", "R-002"], (
        "matched IDs must be listed explicitly; got " + repr(res.covered_ids))
    report = render_q_ledger(res)
    assert "R-003" in report, "an unknown gap must enter the report text; got:\n" + report
    assert "unknown" in report, "the report must carry the unknown marker (the contract's own wording)"


# ── 2. full coverage (contract: all IDs matched → no unknown) ────────────────────
def test_full_coverage_no_unknown():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = write_claims(td, qa_entry("R-001", "implemented", SHA40, "support CSV export")
                         + qa_entry("R-002", "implemented", SHA40, "timeout is configurable")
                         + qa_entry("R-003", "implemented", SHA40, "logs include a timestamp"))
        res = check_q_ledger(SPEC_DIFF_WITH_IDS, p)
    assert res.mode == "precise"
    assert res.unknown_ids == [], (
        "every spec-side commitment has a matching ID in the ledger; no gap may be reported; got "
        + repr(res.unknown_ids))
    assert set(res.covered_ids) == {"R-001", "R-002", "R-003"}


# ── 3. superseded account (explicitly pinned: superseded does not count as a gap) ──────────
def test_superseded_entry_not_a_gap():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = write_claims(td, qa_entry("R-001", "superseded", SHA40, "the old commitment has been superseded"))
        res = check_q_ledger("+ R-001 old commitment item\n", p)
    assert "R-001" not in res.unknown_ids, (
        "when a Q ledger entry has status=superseded, the corresponding spec item is not a gap "
        "(one of the contract's three states; this test pins that account explicitly); got "
        + repr(res.unknown_ids))


# ── 4. boundary degradation (contract: no stable ID → hint-level order-of-magnitude note,
#      no precise gap detection, and the implementation must declare this precondition in
#      its documentation) ────────────────────────
def test_free_markdown_degrades_to_hint():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = write_claims(td, qa_entry("R-001", "implemented", SHA40, "support CSV export"))
        res = check_q_ledger(SPEC_DIFF_FREE_MARKDOWN, p)
    assert res.mode == "hint", (
        "the spec has no stable machine-parseable ID and must degrade to hint level; got mode="
        + repr(res.mode))
    assert res.unknown_ids == [], (
        "hint mode must not produce a precise gap list (no precise gap detection); got "
        + repr(res.unknown_ids))
    assert isinstance(res.hint, str) and res.hint.strip(), (
        "hint mode must give an order-of-magnitude note; never return an empty hint silently")
    doc = (getattr(q_ledger_check, "__doc__", "") or "") + \
          (getattr(check_q_ledger, "__doc__", "") or "")
    assert "ID" in doc, (
        "the contract explicitly requires: the implementation must declare in its documentation "
        "the precondition that \"spec commitment items need stable machine-parseable IDs\" "
        "(either the module or the function docstring will do)")


# ── 5a. structural validation (contract: missing quote → explicit error, not silently swallowed) ──────────
def test_structural_error_missing_quote():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = write_claims(td, "- id: R-001\n  status: implemented\n"
                             f"  source_spec: docs/spec.md@{SHA40}\n")
        with raises(ValueError) as ctx:
            check_q_ledger(SPEC_DIFF_WITH_IDS, p)
    assert ctx.value is not None and str(ctx.value).strip(), \
        "a structural error message must not be empty (explicit error, not silently swallowed)"


# ── 5b. structural validation (contract: sha not 40 chars → explicit error, not silently swallowed) ──────
def test_structural_error_bad_sha():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = write_claims(td, qa_entry("R-001", "implemented", SHA39,
                                      "the quote is fine; the sha is one character short"))
        with raises(ValueError) as ctx:
            check_q_ledger(SPEC_DIFF_WITH_IDS, p)
    assert ctx.value is not None and str(ctx.value).strip(), \
        "a structural error message must not be empty (explicit error, not silently swallowed)"


# ── 6. missing file (no crash, explicit output) ────────────────────────────────
def test_missing_file_explicit_not_crash():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "no_such_claims.yaml")     # does not exist
        res = check_q_ledger(SPEC_DIFF_WITH_IDS, p)     # must not raise
    assert res.mode == "unavailable", (
        "a missing Q ledger file must be marked explicitly unavailable; it must neither crash "
        "nor be silently treated as an empty ledger; got mode=" + repr(res.mode))
    assert isinstance(res.hint, str) and res.hint.strip(), \
        "a missing file must get an explicit human-readable explanation"


# ── 7. empty ledger (no crash, explicit output) ────────────────────────────────
def test_empty_claims_explicit_not_crash():
    _require_impl()
    with tempfile.TemporaryDirectory() as td:
        p = write_claims(td, "")
        res = check_q_ledger(SPEC_DIFF_WITH_IDS, p)     # must not raise
    assert res.mode == "unavailable", (
        "an empty Q ledger must be marked explicitly unavailable; got mode=" + repr(res.mode))
    assert isinstance(res.hint, str) and res.hint.strip(), \
        "an empty ledger must get an explicit human-readable explanation"


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

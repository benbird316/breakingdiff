# -*- coding: utf-8 -*-
"""
q_ledger_check — Q ledger versioning and precise gap detection (4.1)
====================================================
The four quadrants answer "are the listed commitments upheld"; this module answers
"is everything that should be listed actually listed": take each commitment item from
the spec diff and reconcile it by ID against the Q ledger (qa_claims_v1.yaml); items
the spec has but the ledger lacks are marked unknown and put in the report.

## Preconditions (contract boundary conditions, declared in plain text)

Precise gap detection presupposes that **spec commitment items have stable,
machine-parseable IDs** (criterion \\bR-\\d+\\b, contract example R-001). When the spec
is free-form markdown and no ID can be extracted, do not do precise gap detection — a
guessed "gap" misleads more than no gap — and degrade to a hint-level order-of-magnitude
note that puts both sides' magnitudes in front of a human for checking.

## Q ledger contract (top-level list + four keys per entry, standalone file)

    - id: R-001
      status: implemented | superseded | draft
      source_spec: path/to/spec.md@<40-char sha>
      quote: "verbatim commitment"

Structural errors raise QLedgerError loudly; never swallow them into a silent
degradation: missing key / empty quote / sha not 40 chars / status outside the three
states / duplicate id / a stray line outside an entry. The cost of missing data must
be non-zero (the same discipline as coverage_guard's "raise rather than warn"). The
repository has no PyYAML dependency, so this module parses the minimal pinned structure
above with stdlib — the narrower the parser, the less it can silently let through.

## The three-state mode and what "warning level does not block" means here

    precise      the spec side has stable IDs and the ledger is usable → precise
                 reconciliation; unknown_ids / covered_ids ascending
    hint         the spec side has no stable ID → order-of-magnitude hint;
                 unknown_ids always empty (no precise gap detection)
    unavailable  the ledger file is missing or empty → an explicit unavailable state,
                 not silently treated as an empty ledger

"Warning level does not block" lands in this repository as behavioral semantics (there
is no warning tiering precedent; raise means block): with an unknown gap,
check_q_ledger raises nothing and returns normally; the gap is presented as an explicit
data state (unknown_ids) and report text (render_q_ledger). Only a ledger structural
error raises QLedgerError.

Usage:

    from q_ledger_check import check_q_ledger, render_q_ledger
    res = check_q_ledger(spec_diff_text, "qa_claims_v1.yaml")
    print(render_q_ledger(res))     # a gap does not block; look for unknown in the report

Command line: python q_ledger_check.py --self-check    # run this module's own regression
"""
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODE_PRECISE = "precise"
MODE_HINT = "hint"
MODE_UNAVAILABLE = "unavailable"

# Stable machine-parseable ID criterion: R-<number> (contract example R-001). The same
# regex as the acceptance test q_ledger_check_test.py's ID_RE, so the two sides do not
# tell different stories.
_ID_RE = re.compile(r"\bR-\d+\b")

# source_spec must end with @<40-char hex sha> — a spec reference without a version
# anchor mismatches as soon as the data version changes, a typical entry point for
# ledger failure.
_SHA_AT_RE = re.compile(r"@([0-9a-fA-F]{40})$")

_STATUSES = ("implemented", "superseded", "draft")
_REQUIRED_KEYS = ("id", "status", "source_spec", "quote")


class QLedgerError(ValueError):
    """Q ledger structural error (missing key / empty quote / sha shorter than 40 chars
    / status outside the three states / duplicate id / a stray line outside an entry).
    Messages carry the entry location; fail loudly, never degrade silently."""


@dataclass(frozen=True)
class QClaim:
    """One Q ledger entry (four keys)."""
    claim_id: str
    status: str
    source_spec: str
    quote: str


@dataclass(frozen=True)
class QLedgerResult:
    """check_q_ledger's readout. The three-state mode semantics are in the module docstring."""
    mode: str
    unknown_ids: List[str]
    covered_ids: List[str]
    hint: str


def _unquote(value: str) -> str:
    """Strip one layer of paired double quotes (the contract quote shape). Keep the
    value as is when the quotes are unbalanced."""
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _extract_spec_ids(spec_diff_text: str) -> List[str]:
    """Extract stable IDs on the spec side: the R-<number> values that occur, deduped
    and ascending."""
    return sorted(set(_ID_RE.findall(spec_diff_text)))


def _validate_entry(lineno: int, kv: Dict[str, str], path: str) -> QClaim:
    """Validate one entry's structure: all four keys present, non-empty id, a status in
    the three states, and an @40-char sha version anchor."""
    where = f"{path}, starting at line {lineno}"
    missing = [k for k in _REQUIRED_KEYS if k not in kv]
    if "quote" in kv and not kv["quote"]:
        missing.append("quote(empty)")
    if missing:
        raise QLedgerError(
            f"{where}: entry is missing structural keys: {missing}. All four are required "
            f"(id/status/source_spec/quote), id={kv.get('id')!r} "
            f"source_spec={kv.get('source_spec')!r}")
    claim_id = kv["id"]
    if not claim_id:
        raise QLedgerError(
            f"{where}: entry id is empty — id is the reconciliation key, and an empty id cannot be reconciled")
    if kv["status"] not in _STATUSES:
        raise QLedgerError(
            f"{where}: entry status must be {'|'.join(_STATUSES)}, "
            f"got {kv['status']!r} (id={claim_id})")
    if not _SHA_AT_RE.search(kv["source_spec"]):
        raise QLedgerError(
            f"{where}: entry source_spec must end with @<40-char hex sha>, "
            f"got {kv['source_spec']!r} (id={claim_id}) — "
            "a spec reference without a version anchor mismatches as soon as the data version changes")
    return QClaim(claim_id=claim_id, status=kv["status"],
                  source_spec=kv["source_spec"], quote=kv["quote"])


def _parse_claims(text: str, path: str) -> List[QClaim]:
    """Minimal stdlib parse + structural validation. The contract pins the structure
    (top-level list + four scalar keys), so no general yaml parser is needed; the
    narrower the parse, the less slips through silently."""
    entries: List[Tuple[int, Dict[str, str]]] = []
    current: Dict[str, str] = {}
    start_line = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            if current:
                entries.append((start_line, current))
            current = {}
            start_line = lineno
            line = line[2:].strip()
        if ":" not in line:
            if not current and not start_line:
                raise QLedgerError(
                    f"{path} line {lineno} appears before the first entry and is not the contract shape "
                    f"(top-level list + four scalar keys per entry): {raw!r}")
            raise QLedgerError(
                f"{path} line {lineno} is not in 'key: value' form: {raw!r}")
        key, _, value = line.partition(":")
        current[key.strip()] = _unquote(value.strip())
    if current:
        entries.append((start_line, current))

    claims: List[QClaim] = []
    seen: Dict[str, int] = {}
    for lineno, kv in entries:
        claim = _validate_entry(lineno, kv, path)
        if claim.claim_id in seen:
            raise QLedgerError(
                f"{path}: entry id {claim.claim_id!r} is duplicated "
                f"(first seen at line {seen[claim.claim_id]}, repeated at line {lineno})"
                " — id is the reconciliation key; a duplicate is ambiguity")
        seen[claim.claim_id] = lineno
        claims.append(claim)
    return claims


def check_q_ledger(spec_diff_text: str, qa_claims_path: str) -> QLedgerResult:
    """Reverse check: reconcile each spec diff commitment item by ID against the Q ledger.

    Three exits, see the module docstring: precise (precise reconciliation) / hint (the
    spec has no stable ID, degrade to an order-of-magnitude hint) / unavailable (the
    ledger is missing or empty, explicitly unavailable). An unknown gap raises nothing —
    warning level does not block; a ledger structural error raises QLedgerError (a
    ValueError subclass).
    """
    if not os.path.exists(qa_claims_path):
        return QLedgerResult(
            mode=MODE_UNAVAILABLE, unknown_ids=[], covered_ids=[],
            hint=f"Q ledger file does not exist: {qa_claims_path}. The reverse check has no "
                 "ledger to compare against; mark it unavailable explicitly instead of silently "
                 "treating it as an empty ledger")
    with open(qa_claims_path, "r", encoding="utf-8") as f:
        text = f.read()
    claims = _parse_claims(text, qa_claims_path)
    if not claims:
        return QLedgerResult(
            mode=MODE_UNAVAILABLE, unknown_ids=[], covered_ids=[],
            hint=f"Q ledger is empty ({qa_claims_path} parsed to 0 entries). There is nothing to "
                 "reconcile; mark it unavailable explicitly instead of silently judging all green "
                 "or all gaps")

    spec_ids = set(_extract_spec_ids(spec_diff_text))
    if not spec_ids:
        return QLedgerResult(
            mode=MODE_HINT, unknown_ids=[], covered_ids=[],
            hint=f"no stable machine-parseable ID (R-<number> shape) was found on the spec side; "
                 f"degrading to a hint-level order-of-magnitude note: spec text has "
                 f"{len(spec_diff_text.splitlines())} lines, the Q ledger has {len(claims)} entries — "
                 "check by hand whether the magnitudes agree. Precise gap detection needs spec "
                 "commitment items with stable IDs")

    claim_ids = {c.claim_id for c in claims}
    return QLedgerResult(
        mode=MODE_PRECISE,
        unknown_ids=sorted(spec_ids - claim_ids),
        covered_ids=sorted(spec_ids & claim_ids),
        hint="")


def render_q_ledger(res: QLedgerResult) -> str:
    """Render the human-readable report. In precise mode with gaps, every unknown ID
    carries an unknown marker into the report text; hint / unavailable explicitly state
    the reason."""
    if res.mode == MODE_PRECISE:
        lines = ["== Q ledger reconciliation (precise gap detection) ==",
                 f"unknown gaps: {len(res.unknown_ids)}"
                 " (the spec has a commitment and the Q ledger has no match; warning level, does not block)"]
        for i in res.unknown_ids:
            lines.append(f"  - {i} unknown")
        lines.append("covered matches: " + str(len(res.covered_ids)) + ""
                     + (": " + ", ".join(res.covered_ids)
                        if res.covered_ids else ""))
    elif res.mode == MODE_HINT:
        lines = ["== Q ledger reconciliation (hint: order-of-magnitude note, no precise gap detection) ==",
                 f"hint: {res.hint}"]
    else:
        lines = ["== Q ledger reconciliation (unavailable: the Q ledger is not usable) ==",
                 f"hint: {res.hint}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    if "--self-check" in sys.argv:
        import q_ledger_check_test
        return q_ledger_check_test.main()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

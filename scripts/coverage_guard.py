# -*- coding: utf-8 -*-
"""
coverage_guard — surface-under-test coverage gate
==================================================
Backstops tier three of breakingdiff's silence: when a change falls entirely
outside the parameter space, the four quadrants return a "zero change" readout,
and a zero readout gets misread as "verified".

This is not a capability of the core; it is a precondition for reading the core's
readout. The core answers "do the two claims have the same value at a given
parameter point"; it cannot answer "does this set of parameter points still cover
the change". The latter must be judged separately, before the readout.

Usage:
    from coverage_guard import require_covered
    require_covered(changed_keys, catalog_keys, what="this round's changes")
    # raises CoverageError: lists the changed items that fall outside the parameter
    # space but are assumed to be covered

Design notes:
  1. Only verbatim-checkable markers are recognized; no semantic guessing —
     better to under-report blindness than to falsely claim coverage.
  2. Raise instead of warn: a zero readout must carry a non-zero cost, or it is
     still read as a pass.
  3. Distinguish two kinds of miss: items that should never be in the space
     (allowlist) vs items that should be in it but are not (gaps).
"""
from typing import Iterable, Sequence, Set, Tuple


class CoverageError(ValueError):
    """A change falls outside the parameter space under test — the four-quadrant
    readout is invalid for it.

    Structured fields (i18n Phase 0): `reason` is a stable criterion code, and
    `gaps` / `allowed` are the raw sets of gaps and exemptions. Tests assert these
    fields, not the message text — the message is translated, the code never changes.
    """

    def __init__(self, message: str, *, reason: str = "UNCOVERED",
                 gaps=(), allowed=()):
        super().__init__(message)
        self.reason = reason
        self.gaps = frozenset(gaps)
        self.allowed = frozenset(allowed)


def _norm(s: str) -> str:
    """Normalize: whitespace and full-width/half-width differences must not make a
    real gap look covered."""
    return "".join(s.split()).replace("　", "")


def find_uncovered(changed: Iterable[str], covered: Iterable[str],
                   exempt: Iterable[str] = ()) -> Tuple[Set[str], Set[str]]:
    """Split: return (real gaps, exempt items that never belonged in the space).

    changed  — markers touched by this round's actual changes
    covered  — markers the parameter space (catalog) already covers
    exempt   — items explicitly declared out of scope (pure style edits, comments)

    Exemption matching is **verbatim equality**, not substring.
    Lesson learned: substring matching (`_norm(e) in n or n in _norm(e)`) silently
    over-exempts — `exempt=['cover']` would swallow `coverage gate description`,
    and the latter is a real gap. Substring matching is the very "semantic guessing"
    this file explicitly rejects; the exemption mechanism is no exception.
    When a prefix-based relaxation is genuinely needed, write `PREFIX:xxx`
    explicitly, so the relaxation is a checkable declaration rather than a
    coincidence.
    """
    cov = {_norm(x) for x in covered}
    exempt_exact, exempt_prefix = set(), []
    for e in exempt:
        if e.startswith("PREFIX:"):
            exempt_prefix.append(_norm(e[len("PREFIX:"):]))
        else:
            exempt_exact.add(_norm(e))

    gaps, allowed = set(), set()
    for c in changed:
        n = _norm(c)
        if n in cov:
            continue
        if n in exempt_exact or any(n.startswith(p) for p in exempt_prefix):
            allowed.add(c)
        else:
            gaps.add(c)
    return gaps, allowed


def coverage_ratio(changed: Iterable[str], covered: Iterable[str],
                   exempt: Iterable[str] = ()) -> Tuple[int, int]:
    """Return (covered count, total changes this round); the caller computes the percentage.

    The denominator includes gaps — that is the real coverage ratio. An earlier
    implementation returned `len(in_scope), len(in_scope)`, two values from the same
    source, so it could never mathematically give a coverage below 100%: that is not
    "anti-false-green", it reports "nothing is covered" as 100% too (and returns
    0/0 when everything is out of the space, which is worse).
    The ratio itself is not wrapped: return bare counts and let the caller decide how
    to present them, so a function that always reports 100% never lives in the library.
    """
    changed = list(changed)
    gaps, _ = find_uncovered(changed, covered, exempt)
    return len(changed) - len(gaps), len(changed)


def require_covered(changed: Iterable[str], covered: Iterable[str],
                    exempt: Iterable[str] = (),
                    what: str = "this round's changes") -> None:
    """The coverage gate. Raise when something is uncovered — not raising condones
    "zero readout = verified".

    Mirrors the P3 reasoning in SKILL.md: the silent zone is dangerous precisely
    because it raises nothing. The gate's job is to turn "raises nothing" into a
    "non-zero cost".
    """
    gaps, allowed = find_uncovered(changed, covered, exempt)
    if not gaps:
        return
    lines = [f"[CG:UNCOVERED] [coverage gate] {what} has {len(gaps)} item(s) outside the parameter space under test; "
             f"the four-quadrant readout is invalid for them:"]
    for g in sorted(gaps):
        lines.append(f"    · {g}")
    if allowed:
        lines.append(f"  ({len(allowed)} more item(s) declared exempt, no coverage required: "
                     + ", ".join(sorted(allowed)) + ")")
    lines += [
        "",
        "  A zero readout is not a pass. Two ways to fix it:",
        "    ① Fold these items into the parameter space (catalog / scope), then rerun",
        "    ② If they really are unrelated to this tool, add them to the exemption list explicitly; don't let them quietly disappear",
        "",
        "  Criterion: if this change were wrong, would the existing readout move at all? "
        "No → it is not inside the surface under test.",
    ]
    raise CoverageError("\n".join(lines), reason="UNCOVERED",
                        gaps=gaps, allowed=allowed)

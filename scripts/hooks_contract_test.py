# -*- coding: utf-8 -*-
"""
hooks consistency contract — executable assertions over the three hand-copied
judge-order copies (M-H1/H2/H3)
===============================================================
The hook's judge order is hand-copied in three places: the scripts/hook_entry.py
docstring (the canonical copy, a 7-item numbered list), the "Judge order and exit
codes" section of references/hooks.md, and the condensed paragraph in the "Host
hooks" section of SKILL.md. All three are synced by hand, and whoever changes the
judge order will not always remember to change the other two — which copy a reader
lands on decides the hook's semantics, and that is the hole this contract plugs.

This file is the red end of B5's TDD: the assertions are frozen per B5 spec
(2026-10-17) §3 and the live documentation was not yet complete, so it should run
red. Red is not failure; it is the first-hand evidence that makes the drift
explicit. Once the implementation side completes the docs to green, this file is
not touched again.

Division of labour among the three assertions (each reports what is missing; none
substitutes for another):
  M-H1 entry sets equal — two structured copies are checked entry by entry
    against the frozen anchor table (condition keyword + exit code, indexed by
    entry number); all seven condensed anchors must be present in SKILL.md
    (condensing may shorten wording, not drop entries). Missing anchors are named
    one by one and all at once, so a doc fixer does not need N runs to see the
    full picture.
  M-H2 same order — the structured copies must parse in ascending order 1..7.
    Parsing keeps file line order; a scrambled number means the judge order was
    swapped: the first two fast paths never touch disk, so order is the
    performance budget, and swapping it makes every turn's Stop pay disk IO for
    nothing. On the SKILL.md side, the first occurrence of the seven anchors must
    have strictly increasing offsets; when an anchor is missing, "the order of the
    seven anchors" is undefined, and the missing item is named by M-H1 — no
    fabricating an order red from an incomplete set here.
  M-H3 exit-code mapping consistent — three scopes (the whole docstring /
    the judge-order section of hooks.md / the host-hook section of SKILL.md) each
    contain both the literal "receipt internal 1" and "receipt internal 2".
    The literal anchors are the contract: internal 1 is a failing gate, internal 2
    is a runtime error; a combined "internal 1/2" form or a semantic paraphrase
    means whoever greps the anchors during an incident finds nothing — as good as
    an unwritten mapping.

Incomplete parsing (entry count ≠ 7, missing or duplicate numbers) counts as red;
never degrade it to SKIP — an incomplete copy is more dangerous than a drifted
one, and silently skipping mixes "checked" with "did not check" into one output.
Unreadable files and import failures are a different matter: not having run is not
the same as having run; the exit code follows receipt.py's three-tier convention
(0 all green / 1 red / 2 runtime error).

Red messages start with [hooks_contract] and name the file and the missing or
out-of-order entries. No pytest dependency; pytest can collect it directly when
present. Usage: python scripts/hooks_contract_test.py
"""
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                # repo root: one level above scripts/
sys.path.insert(0, HERE)

# Frozen anchor table (B5 spec freeze §3.1; only a spec revision may change it, and
# an implementation must not privately edit it to go green):
# (entry number, judge-order line condition anchor, SKILL.md condensed anchor,
#  frozen exit code).
# Entry 3 uses "no marker" as the SKILL anchor and entry 4 the merged phrase
# "pending without receipt"; both are existing condensed wordings — the state
# machine sentence at the start of that section writes "write pending before the
# differential" first, and a bare pending anchor would first occur before
# stop_hook_active, skewing M-H2's position-order check (scheduler decision).
FROZEN_TABLE = (
    (1, "stdin", "stdin", 0),
    (2, "stop_hook_active", "stop_hook_active", 0),
    (3, ".breakingdiff", "no marker", 0),
    (4, "pending", "pending without receipt", 2),
    (5, "gate", "gate", 2),
    (6, "claims", "claims", 2),
    (7, "otherwise", "otherwise", 0),
)

# M-H3 mapping literals: a paired criterion; either scope missing half counts as missing
# (see test_m_h3).
MAP_LITERALS = ("receipt internal 1", "receipt internal 2")

HOOKS_MD_REL = os.path.join("references", "hooks.md")

# The frozen shape of a judge-order line: 4-space indent, number, condition, →, exit,
# a one-digit exit code, all readable on one line — a wrapped line makes line-by-line
# parsing undercount entries, i.e. it lets an incomplete copy pass.
ORDER_LINE_RE = re.compile(r"^\s{4}(\d+)\.\s+(.+?)\s+→\s+exit\s+(\d)")


class HooksContractError(AssertionError):
    """Assertion red (exit-code 1 semantics). Running and judging drift differs
    from not running — the runner uses this type to split "red" and "runtime
    error" into two exit codes."""


# ------------------------------------------------------------ live sources
def _hook_entry_doc():
    """Canonical-side live source: import, then read __doc__. The lazy import is
    deliberate — an import failure counts as a runtime error (exit code 2); at
    module top level the script would crash outright, and "did not run" would
    disguise itself as "ran red"."""
    try:
        import hook_entry
    except Exception as e:
        raise RuntimeError(
            f"[hooks_contract] runtime error: import hook_entry failed: {e!r}") from e
    return hook_entry.__doc__ or ""


def _read(rel):
    """Read a repository source. Unreadable is a runtime error (exit code 2), not an
    assertion red: a missing source means the repository itself is wrong, and no
    red/green conclusion is meaningful then."""
    path = os.path.join(ROOT, rel)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise RuntimeError(
            f"[hooks_contract] runtime error: cannot read repository source {rel}: {e}") from e


def _section(text, heading_prefix, rel):
    """Take the section starting with "## <heading_prefix>", up to the next "## " or
    end of file. A heading may carry a suffix: the SKILL.md section is really
    "Host hooks (optional installation)", and only prefix matching lands on the
    "Host hooks" section the spec names. A drifted or deleted section heading is a
    structural failure and goes red on the spot — an assertion result without a
    live source cannot be trusted."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and ln[3:].strip().startswith(heading_prefix):
            start = i
            break
    if start is None:
        raise HooksContractError(
            f"[hooks_contract] {rel} has no section " + '"## ' + heading_prefix + '" — '
            "the section heading drifted or was deleted, and the contract check lost its live source")
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


def _parse_ordered(text, where):
    """Parse judge-order lines one by one; return [(entry number, condition, exit
    code)]. A structurally incomplete copy goes red on the spot: an entry count
    other than 7, or missing or duplicate numbers, means the copy is too broken for
    the anchor table to check, and continuing would only produce plausible-looking
    wrong conclusions."""
    found = []
    for ln in text.splitlines():
        m = ORDER_LINE_RE.match(ln)
        if m:
            found.append((int(m.group(1)), m.group(2), int(m.group(3))))
    nums = [no for no, _, _ in found]
    if len(found) != 7 or sorted(nums) != list(range(1, 8)):
        raise HooksContractError(
            f"[hooks_contract] {where} judge order parsed incomplete: got {len(found)} entries "
            f"(numbers {nums}), expected 7 entries numbered 1..7 with no gaps.\n"
            "A judge-order line must look like " + '"    1. condition → exit 0" '
            "(4-space indent, number, →, and exit on the same line).")
    return found


def _check_frozen_table(entries, where, reds):
    """Check the anchor table by entry number: the condition must contain the anchor
    word, and the exit code must equal the frozen value. Line order is not judged
    here — that is M-H2's job. Indexing by number has another use: when whole
    judge-order lines are swapped, anchor and exit code still match per entry, and
    the red lands only in M-H2 without collateral damage."""
    by_no = {no: (cond, code) for no, cond, code in entries}
    for no, anchor, _, frozen_code in FROZEN_TABLE:
        cond, code = by_no[no]
        if anchor not in cond:
            reds.append(f'{where} entry {no} condition "{cond}" lacks anchor "{anchor}"')
        if code != frozen_code:
            reds.append(f"{where} entry {no} exit code {code} ≠ frozen value {frozen_code}")


# ------------------------------------------------------------ the three assertions
def test_m_h1_entry_sets_match():
    """M-H1 entry sets equal. Red conditions: a structured copy's entry lacks an
    anchor or has a misplaced exit code, or the SKILL.md condensed anchors are
    missing — condensing may shorten wording, not drop entries."""
    reds = []

    doc_entries = _parse_ordered(_hook_entry_doc(),
                                 "scripts/hook_entry.py docstring")
    _check_frozen_table(doc_entries, "scripts/hook_entry.py docstring", reds)

    md_section = _section(_read(HOOKS_MD_REL), "Judge order and exit codes",
                          "references/hooks.md")
    md_entries = _parse_ordered(md_section, "references/hooks.md")
    _check_frozen_table(md_entries, "references/hooks.md", reds)

    skill_section = _section(_read("SKILL.md"), "Host hooks", "SKILL.md")
    reds.extend(
        f"SKILL.md host-hook section is missing entry {no} condensed anchor \"{anchor}\""
        for no, _, anchor, _ in FROZEN_TABLE if anchor not in skill_section)

    if reds:
        raise HooksContractError(
            "[hooks_contract] M-H1 entry sets equal: the three copies do not match the frozen anchor table.\n"
            + "\n".join("  - " + r for r in reds)
            + "\nThe anchor table in this file's FROZEN_TABLE is authoritative (frozen); "
              "fix the docs to match it, do not edit anchors to go green.")


def test_m_h2_order_identical():
    """M-H2 same order. Red conditions: a structured copy parses in an order other
    than ascending 1..7 (the judge order was swapped), or the first-occurrence
    offsets of the seven SKILL.md anchors are not strictly increasing. The SKILL
    side is not judged when anchors are missing — order presupposes a complete set,
    and M-H1 already records missing items. Entry 4 uses the merged phrase
    "pending without receipt" as its anchor so that a bare pending in the section's
    opening sentence does not steal its position (scheduler decision)."""
    doc_entries = _parse_ordered(_hook_entry_doc(),
                                 "scripts/hook_entry.py docstring")
    md_section = _section(_read(HOOKS_MD_REL), "Judge order and exit codes",
                          "references/hooks.md")
    md_entries = _parse_ordered(md_section, "references/hooks.md")
    for entries, where in ((doc_entries, "scripts/hook_entry.py docstring"),
                           (md_entries, "references/hooks.md")):
        nums = [no for no, _, _ in entries]
        if nums != list(range(1, 8)):
            raise HooksContractError(
                f"[hooks_contract] M-H2 same order: {where} judge-order line order is "
                f"{nums}, expected ascending 1..7 — order is the performance budget; the "
                "two fast paths never touch disk, so a swap = every turn's Stop pays disk IO for nothing")

    skill_section = _section(_read("SKILL.md"), "Host hooks", "SKILL.md")
    offsets = [skill_section.find(anchor) for _, _, anchor, _ in FROZEN_TABLE]
    if -1 in offsets:
        return    # not all seven anchors present: order is undefined; M-H1 reports the gap explicitly, do not fake it here
    for i in range(len(offsets) - 1):
        if offsets[i + 1] <= offsets[i]:
            raise HooksContractError(
                f"[hooks_contract] M-H2 same order: SKILL.md host-hook section anchor "
                f'"{FROZEN_TABLE[i + 1][2]}" (offset {offsets[i + 1]}) is not strictly after '
                f'anchor "{FROZEN_TABLE[i][2]}" (offset {offsets[i]}) — '
                "condensed-section anchor order must increase along judge order 1→7")


def test_m_h3_exit_code_mapping():
    """M-H3 exit-code mapping consistent. Red conditions: any scope lacks the literal
    "receipt internal 1" or "receipt internal 2". Missing literals are merged per
    file and reported all at once."""
    scopes = (
        ("scripts/hook_entry.py docstring (full text)", _hook_entry_doc()),
        ("references/hooks.md (judge order and exit codes section)",
         _section(_read(HOOKS_MD_REL), "Judge order and exit codes", "references/hooks.md")),
        ("SKILL.md (host hooks section)",
         _section(_read("SKILL.md"), "Host hooks", "SKILL.md")),
    )
    reds = []
    for name, text in scopes:
        gone = [lit for lit in MAP_LITERALS if lit not in text]
        if gone:
            reds.append(f'{name} is missing the mapping literal "{" / ".join(gone)}"')
    if reds:
        raise HooksContractError(
            "[hooks_contract] M-H3 exit-code mapping: the mapping literals must be present "
            "as a pair (" + '"receipt internal 1", "receipt internal 2").\n'
            + "\n".join("  - " + r for r in reds)
            + "\nFix: write out both literals (e.g. " + '"receipt internal 1, receipt internal 2 '
              '→ hook 2"), the combined "internal 1/2" form does not count.')


def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad, errs = [], []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS {name}")
        except HooksContractError:
            bad.append(name)
            print(f"  FAIL {name}")
            traceback.print_exc()
        except Exception:
            errs.append(name)
            print(f"  ERROR {name}")
            traceback.print_exc()
    parts = []
    if bad:
        parts.append(f"failed: {bad}")
    if errs:
        parts.append(f"runtime errors: {errs} (exit code 2, see ERROR above)")
    passed = len(fns) - len(bad) - len(errs)
    print(f"\n{passed}/{len(fns)} passed"
          + (", " + "; ".join(parts) if parts else ""))
    return 2 if errs else (1 if bad else 0)


if __name__ == "__main__":
    raise SystemExit(main())

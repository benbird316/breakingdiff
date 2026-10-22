# -*- coding: utf-8 -*-
"""
reanchor — quote ledger re-anchor helper (three states: alive / dead / suspect)
================================================================
After a spec revision, line numbers in the ledger drift as a whole. This module
answers one question: can this quote still be anchored in the new file; and if not,
which lines most likely hold its new position.

## The three states and their boundary

    ALIVE    alive    the quote appears verbatim (after CRLF→LF normalization) in the
                      new file; report the start line
    DEAD     dead     not verbatim, and no near neighbor anywhere above the similarity
                      threshold; report no candidates
    SUSPECT  suspect  not verbatim, but a near neighbor exists; report line candidates

The boundary between dead and suspect is hard: a near neighbor must yield candidates,
and no near neighbor must yield an empty candidate list. A report that says "dead but
carries candidates" mixes two situations, and a human cannot route reviews by state.

## Candidates only, confirmation belongs to a human (a contract clause, not a style preference)

Where a dead quote should be anchored is a semantic decision — was that passage
rewritten or deleted — and the tool does not adjudicate it. This module is therefore
read-only: it does not write the new file; it does not modify ledger entries (it reads
only .name / .quote, duck-typed, so a Claim or a lightweight object can both be fed
in); it returns a report copy, not the ledger object itself. The three states are
closed; there is no fourth state implying "already fixed it for you".

## Conventions

  · line numbers are 1-based, the same writing family as the L-prefixed line anchors
    in quote_source_ref;
  · for a live multiline quote, the line number is its start line; a suspect
    candidate points at the start line of the window, where window = the quote's line
    count (a single-line quote compares line by line, a multiline quote compares the
    whole block);
  · line-ending policy matches provenance: normalize CRLF→LF on both sides before
    comparing; make no line-ending assumption;
  · the near-neighbor threshold is 0.6, difflib.get_close_matches' standard default.
    The fixture measures 0.826 for suspect vs 0.293 for dead, so 0.6 sits in the middle
    with margin. The threshold is an implementation detail and is not frozen; what is
    frozen is the boundary behavior (near neighbor = non-empty candidates / no near
    neighbor = empty candidates).

Usage:

    from reanchor import reanchor, ALIVE, DEAD, SUSPECT
    res = reanchor(claims, "spec_v2.md")    # read-only report; confirmation belongs to a human

Command line: python reanchor.py --self-check    # run this module's own regression
"""
import difflib
import sys
from typing import Any, Dict, List, Sequence

ALIVE = "alive"      # alive: verbatim hit, line located, candidates empty
DEAD = "dead"        # dead: verbatim miss with no near neighbor; line and candidates both empty
SUSPECT = "suspect"  # suspect new position: verbatim miss with a near neighbor; candidates non-empty

NEIGHBOR_RATIO = 0.6   # difflib's standard default for near-neighbor judgment; the value is not frozen, the boundary behavior is


def _start_line(text: str, quote: str) -> int:
    """The 1-based start line of quote in text. Only called when quote in text holds."""
    return text.count("\n", 0, text.find(quote)) + 1


def _candidate_lines(lines: List[str], quote: str) -> List[int]:
    """Find near neighbors with a sliding window: the window line count is the
    quote's line count, and the window start line is the candidate. Those above the
    threshold are sorted by similarity descending, ties by line number ascending —
    the same input does not change order across two runs."""
    q_lines = quote.split("\n")
    while len(q_lines) > 1 and not q_lines[-1]:
        q_lines.pop()                     # a trailing newline does not shape the window
    k = len(q_lines)
    q_text = "\n".join(q_lines)
    scored = []
    for start in range(len(lines) - k + 1):
        window = "\n".join(lines[start:start + k])
        ratio = difflib.SequenceMatcher(None, q_text, window).ratio()
        if ratio >= NEIGHBOR_RATIO:
            scored.append((ratio, start + 1))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [line for _, line in scored]


def reanchor(entries: Sequence[Any], new_path: str) -> List[Dict[str, Any]]:
    """Produce a three-state report entry by entry, in ledger order. Each entry has at
    least four keys:

        name       ledger entry identity (the anchor that matches entry by entry)
        state      one of ALIVE / DEAD / SUSPECT
        line       the quote's start line when alive (1-based); None when dead / suspect
        candidates line candidates for a suspect new position; dead is always an empty
                   list (the boundary with suspect)

    Read-only: does not write the new file, does not modify ledger entries, and does
    not automatically record candidates — confirmation belongs to a human.
    """
    with open(new_path, "rb") as f:
        raw = f.read()
    # Fail loudly in place when UTF-8 cannot decode; do no character replacement:
    # replacing bad bytes would silently turn a "verbatim" comparison into an
    # "approximate" one, and all three states would be distorted.
    text = raw.decode("utf-8").replace("\r\n", "\n")
    lines = text.splitlines()
    report = []
    for entry in entries:
        quote = entry.quote.replace("\r\n", "\n")
        if quote in text:
            report.append({"name": entry.name, "state": ALIVE,
                           "line": _start_line(text, quote),
                           "candidates": []})
            continue
        candidates = _candidate_lines(lines, quote)
        report.append({"name": entry.name,
                       "state": SUSPECT if candidates else DEAD,
                       "line": None,
                       "candidates": candidates})
    return report


def main() -> int:
    if "--self-check" in sys.argv:
        import reanchor_test
        return reanchor_test.main()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

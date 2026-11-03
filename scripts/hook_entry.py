# -*- coding: utf-8 -*-
"""
hook_entry — artifact state machine for the Claude Code Stop event (thin adapter)
==============================================================
The decision object is **on-disk artifacts**, not transcript semantics: official
docs confirm the transcript lags asynchronously (at Stop time you read the previous
turn's data), and Stop fires every turn with no `if` filter — guessing "does this
turn need a differential" from the transcript is not implementable. The decision is
a pure disk check: deterministic, sub-second, transcript-free.

Convention: a `.breakingdiff/` working directory (relative to the project root):

    pending        written when the claim differential starts (begin_differential
                   in scripts/receipt.py); content is unconstrained
    receipt.json   the receipt persisted after compare (scripts/receipt.py)

Judge order (order is the performance budget; the first two never touch disk):

    1. stdin empty / non-JSON   → exit 0 silently. The hook must not interrupt the
                                  user's turn because of its own parse errors — a
                                  non-JSON payload is usually a host version
                                  difference or another event, not bad news
    2. stop_hook_active=true    → exit 0. Prevents the Stop→continue→Stop loop;
                                  the host force-overrides the hook after 8 times.
                                  The guard must run before any disk IO
    3. no .breakingdiff/ marker → exit 0, immediate. The fast path is the first
                                  branch: Stop fires every turn, slow = every turn
                                  is slow
    4. pending marker present    → exit 2 + actionable stderr
                                  (a differential started and no receipt closed
                                  it; receipt internal 2 = runtime-error shape: no
                                  receipt was produced)
    5. gate fails               → exit 2 + stderr feeds the diff back
                                  (receipt internal 1 → hook layer 2 mapping; Claude
                                  Code only blocks on exit 2, stderr feeds the model)
    6. otherwise                → exit 0

`pending` on disk is the whole "in flight" state: `write_receipt` removes it in
the same step that persists the receipt, and `begin_differential` writes it
before removing a previous receipt. A crash that leaves both markers is treated
as open (exit 2), and the next begin/write repairs it — the pair is never read
as "closed". Once the differential is closed, later edits to claim-bearing
files are not stale against it: the closed receipt describes the round that
ended, not the working tree.

Honest degradation (definitions live in references/hooks.md; not restated here):
the hook is a staleness reminder, not a requirement judge; if no differential
starts, the hook stays silent — it raises the cost of carelessness, not
of forgery; it is a fallback, not a replacement.

stderr encoding: the Windows console defaults to a legacy code page; non-ASCII
exit-2 feedback would be read as mojibake — as good as unwritten. Pin
reconfigure(utf-8, errors="replace") on the very first line of the entry point.

Usage (the complete snippet and the Windows PowerShell wrapper are in
references/hooks.md):

    command: python scripts/hook_entry.py
    Windows wrapper variant:
      powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "python scripts/hook_entry.py; exit $LASTEXITCODE"

Command line: python hook_entry.py --self-check    # run this module's own regression
"""
import json
import os
import sys

BD_DIR = ".breakingdiff"
PENDING_NAME = "pending"
RECEIPT_NAME = "receipt.json"

MSG_UNCLOSED = ("[HK:DIFFERENTIAL_UNCLOSED] .breakingdiff/pending is still on disk — a claim differential "
                "started and no receipt closed it. Run compare and persist the receipt with write_receipt; "
                "if this turn truly has no differential, delete the stale pending marker.")
MSG_GATE = ("[HK:RECEIPT_GATE_FAILED] receipt gate failed (expected.surprise=true), differences: {diffs}. "
            "Re-read the report to fix the divergence or amend the expectation, then rerun compare and "
            "persist a new receipt.")
MSG_BROKEN = ("[HK:BROKEN_RECEIPT] receipt cannot be parsed (runtime error): {err}. A broken receipt is "
              "not a pass — rerun compare to persist a new receipt, or delete the broken files under "
              ".breakingdiff/.")


def _stderr_text(payload) -> str:
    """Compress the receipt diff block into one line of prose. The surprise block
    comes from the reconcile contract in receipt.py."""
    diffs = payload.get("diffs") or []
    parts = []
    for d in diffs:
        if isinstance(d, dict) and d.get("field"):
            parts.append(f"{d['field']}(expected {d.get('expected')} actual {d.get('actual')})")
    return "; ".join(parts) if parts else json.dumps(payload, ensure_ascii=False)


def decide(payload) -> "tuple[int, str]":
    """Pure decision: returns (exit code, stderr text). Empty stderr = silent."""
    if payload.get("stop_hook_active"):
        return 0, ""
    cwd = payload.get("cwd") or os.getcwd()
    bd = os.path.join(cwd, BD_DIR)
    if not os.path.isdir(bd):              # fast path: one stat, the most common case
        return 0, ""
    pending = os.path.join(bd, PENDING_NAME)
    receipt = os.path.join(bd, RECEIPT_NAME)
    if os.path.exists(pending):
        return 2, MSG_UNCLOSED
    if os.path.exists(receipt):
        try:
            with open(receipt, "rb") as f:
                data = json.loads(f.read().decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            return 2, MSG_BROKEN.format(err=e)
        exp = data.get("expected")
        if isinstance(exp, dict) and exp.get("surprise"):
            return 2, MSG_GATE.format(diffs=_stderr_text(exp))
    return 0, ""


def main() -> int:
    try:                                   # Windows GBK console chain: pin UTF-8 first
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if "--self-check" in sys.argv:
        import hook_entry_test
        return hook_entry_test.main()
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        if not isinstance(payload, dict):
            return 0                       # malformed input counts as a parse failure; stay silent
    except (ValueError, UnicodeDecodeError):
        return 0                           # parse failure stays silent: do not interrupt the user's turn
    try:
        code, msg = decide(payload)
    except Exception as e:                 # unexpected error in the decision path: a loud failure beats a silent pass
        code, msg = 2, f"hook internal error (runtime error): {e!r}"
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

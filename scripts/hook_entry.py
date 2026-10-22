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

    pending        written by the agent right before it does the claim differential
                   (required by the SKILL.md workflow); content is unconstrained
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
    4. pending without receipt  → exit 2 + actionable stderr
                                  (receipt internal 2 = runtime-error shape: no
                                  receipt was produced)
    5. gate fails               → exit 2 + stderr feeds the diff back
                                  (receipt internal 1 → hook layer 2 mapping; Claude
                                  Code only blocks on exit 2, stderr feeds the model)
    6. claims files newer than receipt → exit 2 + stderr (artifacts stale: changed
                                  without rerunning the differential)
    7. otherwise                → exit 0

Claim-file list sources (by priority):

    1. env BD_CLAIMS_FILES (os.pathsep separated, relative to cwd; tests and special
       hosts inject it)
    2. git status --porcelain (cwd; includes untracked files). Non-git repo / git
       unavailable / timeout → empty list, **staleness check skipped** — a silent
       degradation: with no list source, silence beats a false red (pinned by
       test_non_git_dir_without_claims_env_skips_staleness)

Honest degradation (definitions live in the SKILL.md "Host hooks" section; not
restated here): the hook is a staleness reminder, not a requirement judge; if the
agent never writes pending, the hook stays silent — it raises the cost of
carelessness, not of forgery; it is a fallback, not a replacement.

stderr encoding: the Windows console defaults to a legacy code page; non-ASCII
exit-2 feedback would be read as mojibake — as good as unwritten. Pin
reconfigure(utf-8, errors="replace") on the very first line of the entry point.

Usage (the complete snippet is in the SKILL.md "Host hooks (optional installation)"
section):

    command: python scripts/hook_entry.py
    Windows wrapper variant:
      powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "python scripts/hook_entry.py"

Command line: python hook_entry.py --self-check    # run this module's own regression
"""
import json
import os
import subprocess
import sys

BD_DIR = ".breakingdiff"
PENDING_NAME = "pending"
RECEIPT_NAME = "receipt.json"
CLAIMS_ENV = "BD_CLAIMS_FILES"
GIT_TIMEOUT_S = 10          # a hung git must not stall every turn; on timeout, treat it as no list

MSG_PENDING = ("[HK:PENDING_WITHOUT_RECEIPT] .breakingdiff/pending is still there but there is no receipt — "
               "the previous claim differential never wrote a receipt. Run compare and persist it with "
               "write_receipt; if this turn truly has no differential, delete the stale pending marker.")
MSG_GATE = ("[HK:RECEIPT_GATE_FAILED] receipt gate failed (expected.surprise=true), differences: {diffs}. "
            "Re-read the report to fix the divergence or amend the expectation, then rerun compare and "
            "persist a new receipt.")
MSG_STALE = ("[HK:CLAIMS_STALE] claims-bearing files are newer than the latest receipt — stale artifacts "
             "(changed without rerunning the differential): {files}. Rerun compare and persist a new "
             "receipt, or delete pending.")
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


def _claims_files(cwd: str):
    """List of claims-bearing files. The env var wins (tests inject it); otherwise
    git status. Drop any .breakingdiff/ paths from the list: pending/receipt are
    always newer than the receipt (just written), and keeping them would turn the
    staleness check permanently red."""
    raw = os.environ.get(CLAIMS_ENV)
    if raw:
        names = [n for n in raw.split(os.pathsep) if n.strip()]
    else:
        names = _git_status_names(cwd)
    return [n for n in names
            if not (n == BD_DIR or n.startswith(BD_DIR + "/")
                    or n.startswith(BD_DIR + "\\"))]


def _git_status_names(cwd: str):
    """The git status --porcelain list (untracked files included). Failure or
    timeout yields an empty list — missing git is normal (.breakingdiff works in
    non-git projects too), not an error."""
    cmd = ["git", "-C", cwd, "-c", "core.quotepath=false", "status", "--porcelain"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    out = []
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:                 # rename: take the new name
            path = path.split(" -> ", 1)[1]
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if path:
            out.append(path)
    return out


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
    if os.path.exists(pending) and not os.path.exists(receipt):
        return 2, MSG_PENDING
    if os.path.exists(receipt):
        try:
            with open(receipt, "rb") as f:
                data = json.loads(f.read().decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            return 2, MSG_BROKEN.format(err=e)
        exp = data.get("expected")
        if isinstance(exp, dict) and exp.get("surprise"):
            return 2, MSG_GATE.format(diffs=_stderr_text(exp))
    # staleness reconciliation: only meaningful with a receipt; skip when the list
    # source is missing (honest degradation)
    if os.path.exists(receipt):
        try:
            receipt_mtime = os.path.getmtime(receipt)
        except OSError:
            receipt_mtime = 0.0
        newer = [n for n in _claims_files(cwd)
                 if _mtime_of(os.path.join(cwd, n)) > receipt_mtime]
        if newer:
            return 2, MSG_STALE.format(files=", ".join(newer[:8]))
    return 0, ""


def _mtime_of(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0                        # deleted files in the list do not affect staleness


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

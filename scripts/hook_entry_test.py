# -*- coding: utf-8 -*-
"""
Regression tests and mutation evidence for hook_entry itself
==================================================
The hook is attached to the Stop event and fires every turn. It has two ways to
die: false blocking (it stops a normal turn, the user gets annoyed and uninstalls
the hook) and a silent pass (it does not block what it should, so installing it
changed nothing). Both ways are pinned here:

  · guard order: stop_hook_active must run before every disk decision (prevents
    the Stop blocking loop);
  · fast path: a directory with no marker must exit 0 instantly with empty stderr;
  · the stderr of the three negative paths must be readable text (pinned by a
    real Windows GBK chain transcoding run);
  · exit-code mapping: receipt gate fails (1) → hook 2; runtime error → 2; pass → 0.

Everything runs hook_entry.py for real through subprocess — the hook's contract is
"process exit code + stderr", and only a real run tests the real contract. No pytest
dependency. Usage: python hook_entry_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hook_entry.py")


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


def run_hook(cwd, payload=None, stdin_text=None):
    """Run hook_entry.py for real: feed stdin, set cwd, return (exit code, stderr)."""
    if stdin_text is None:
        stdin_text = json.dumps(payload or {})
    proc = subprocess.run([sys.executable, HOOK],
                          input=stdin_text.encode("utf-8"), cwd=cwd,
                          capture_output=True, env=os.environ.copy(), timeout=60)
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def stop_payload(cwd, **kw):
    """The minimal shape of a Claude Code Stop event payload."""
    p = {"session_id": "s", "transcript_path": "t.jsonl", "cwd": cwd,
         "hook_event_name": "Stop", "stop_hook_active": False}
    p.update(kw)
    return p


def make_project():
    """A one-shot temporary project directory; return (root, .breakingdiff path)."""
    d = tempfile.mkdtemp(prefix="bd_hook_")
    return d, os.path.join(d, ".breakingdiff")


def write(path, text, mtime=None):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))   # pin mtime explicitly; do not gamble on sleep ordering


RECEIPT_OK = json.dumps({"schema_version": 2, "run_kind": "pairwise",
                         "expected": None}, ensure_ascii=False)
RECEIPT_GATE_FAIL = json.dumps({"schema_version": 2, "run_kind": "pairwise",
                                "expected": {"surprise": True, "diffs": [
                                    {"field": "counters.common",
                                     "expected": 0, "actual": 1}]}},
                               ensure_ascii=False)


# ── guard order and fast path (architect acceptance gates 1 and 2) ────────────────────
def test_stop_hook_active_short_circuits_before_any_disk_check():
    """stop_hook_active=true → exit 0 with no report — even when the disk is in a
    state that should exit 2 (pending marker on disk). This proves the guard runs
    before every disk decision: otherwise Stop blocks → the model continues → the
    next Stop is blocked again, and after 8 times the host force-overrides the hook."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        write(os.path.join(bd, "pending"), "")
        code, err = run_hook(d, stop_payload(d, stop_hook_active=True))
        assert code == 0, f"guard failed: exit code {code}"
        assert err == "", f"the guard path must not report anything: {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_no_marker_dir_exit_zero_fast():
    """No .breakingdiff/ → exit 0 in a split second, empty stderr. The fast path is
    the first branch: Stop fires every turn, so slow = slow every turn. The timing
    assertion is an order-of-magnitude guard (it stops slow IO such as git from
    moving ahead of the fast path), not an exact budget."""
    d, _ = make_project()
    try:
        t0 = time.perf_counter()
        code, err = run_hook(d, stop_payload(d))
        dt = time.perf_counter() - t0
        assert code == 0 and err == "", f"the fast path must stay silent: {code} {err!r}"
        assert dt < 2.0, f"fast path took {dt:.2f}s — slow IO leaked into a branch that runs every turn"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── three negative paths (architect acceptance gate 3 + exit-code mapping) ──────────────
def test_unclosed_pending_blocks_with_actionable_stderr():
    """pending exists → exit 2, stderr is actionable text. `pending` is the whole
    in-flight state: it is written before a receipt and removed by write_receipt in
    the same step that persists one, so its presence means the differential was
    never closed.
    The literal text being present verbatim = the encoding chain is intact: the
    Windows console defaults to GBK, so if the hook does not pin UTF-8, decoding
    as UTF-8 here finds no keyword — a mojibake report is as good as unwritten."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        write(os.path.join(bd, "pending"), "")
        code, err = run_hook(d, stop_payload(d))
        assert code == 2, f"should block: exit code {code}"
        assert ".breakingdiff/pending" in err, f"the message must name the file to be actionable: {err!r}"
        assert "[HK:DIFFERENTIAL_UNCLOSED]" in err, f"decision code lost: {err!r}"
        assert "\ufffd" not in err, f"the message must be valid UTF-8 (a GBK console leaks U+FFFD): {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_receipt_gate_fail_maps_to_two():
    """receipt gate fails (surprise=true) → hook exit 2 + stderr feeds the diff back.
    receipt internal 1 maps to hook layer 2 — Claude Code only blocks on exit 2."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        write(os.path.join(bd, "receipt.json"), RECEIPT_GATE_FAIL)
        code, err = run_hook(d, stop_payload(d))
        assert code == 2, f"a failing gate must map to 2: {code}"
        assert "[HK:RECEIPT_GATE_FAILED]" in err and "counters.common" in err, f"the feedback must carry the decision code and the diff field: {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_broken_receipt_json_is_runtime_error():
    """receipt exists but the JSON is broken → runtime-error semantics → exit 2.
    A silent exit 0 would make "hand-write a broken receipt to fool the hook" a
    zero-cost channel."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        write(os.path.join(bd, "receipt.json"), "{not json")
        code, err = run_hook(d, stop_payload(d))
        assert code == 2, f"a broken receipt must block as a runtime error: {code}"
        assert "[HK:BROKEN_RECEIPT]" in err, f"the message must name the broken receipt: {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_non_json_stdin_exits_zero_silently():
    """Non-JSON stdin → exit 0 silently. The hook must not interrupt the user's
    turn because of its own parse error — non-JSON is usually a host version
    difference or another event that strayed in, not bad news."""
    d, _ = make_project()
    try:
        code, err = run_hook(d, stdin_text="this is not json")
        assert code == 0, f"a parse failure must pass silently: {code}"
        assert err == "", f"the silent path must not report anything: {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_empty_stdin_exits_zero():
    """Empty stdin is the same as a parse failure: exit 0 silently."""
    d, _ = make_project()
    try:
        code, err = run_hook(d, stdin_text="")
        assert (code, err) == (0, "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── the closed state stays closed ───────────────────────────────────────────────
def test_closed_receipt_ignores_later_claims_edits():
    """Receipt on disk, `pending` gone, claims file edited afterwards → exit 0.
    A closed differential describes the round that ended, not the working tree: if
    the hook reconciled every later edit it would scan the repo on idle turns and
    turn unrelated work into a permanent red — the loudest break of "if no
    differential starts, it stays silent"."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        now = time.time()
        claims = os.path.join(d, "claims.md")
        write(claims, "claim-bearing file", mtime=now + 100)   # newer than the receipt
        write(os.path.join(bd, "receipt.json"), RECEIPT_OK, mtime=now)
        code, err = run_hook(d, stop_payload(d))
        assert (code, err) == (0, ""), f"a closed differential must not be reopened by repo edits: {code} {err!r}"
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

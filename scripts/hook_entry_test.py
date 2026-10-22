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


def run_hook(cwd, payload=None, stdin_text=None, env_extra=None):
    """Run hook_entry.py for real: feed stdin, set cwd, return (exit code, stderr)."""
    env = os.environ.copy()
    env.pop("BD_CLAIMS_FILES", None)          # isolate the host env; tests inject their own
    if env_extra:
        env.update(env_extra)
    if stdin_text is None:
        stdin_text = json.dumps(payload or {})
    proc = subprocess.run([sys.executable, HOOK],
                          input=stdin_text.encode("utf-8"), cwd=cwd,
                          capture_output=True, env=env, timeout=60)
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
    state that should exit 2 (pending without receipt). This proves the guard runs
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
def test_pending_without_receipt_blocks_with_actionable_stderr():
    """pending exists without a receipt → exit 2, stderr is actionable text.
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
        assert "[HK:PENDING_WITHOUT_RECEIPT]" in err, f"decision code lost: {err!r}"
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


# ── mtime reconciliation: a claims-bearing file newer than the receipt → stale ─────────────
def test_claims_newer_than_receipt_blocks():
    """Control state (receipt newer) exits 0; target state (claims newer) exits 2 —
    one fixture for both, the only difference is mtime order, so a red can only come
    from the staleness decision."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        now = time.time()
        claims = os.path.join(d, "claims.md")
        write(claims, "claim-bearing file", mtime=now - 1000)
        write(os.path.join(bd, "receipt.json"), RECEIPT_OK, mtime=now - 500)
        code, err = run_hook(d, stop_payload(d),
                             env_extra={"BD_CLAIMS_FILES": "claims.md"})
        assert (code, err) == (0, ""), "must not report stale when the receipt is newer"
        os.utime(claims, (now + 100, now + 100))   # claims edited without rerunning the differential
        code, err = run_hook(d, stop_payload(d),
                             env_extra={"BD_CLAIMS_FILES": "claims.md"})
        assert code == 2, f"a newer claims file must report stale: {code}"
        assert "[HK:CLAIMS_STALE]" in err and "compare" in err, f"the message must give the action: {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_staleness_via_real_git_status():
    """A real git repo goes through the git status list path — BD_CLAIMS_FILES is a
    test-injection back door, and the main path beyond the back door needs at least
    one test pinning it, or the back door never touches the real chain."""
    d, bd = make_project()
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "t@t"

    def git(*args):
        subprocess.run(["git", "-C", d, *args], capture_output=True,
                       env=env, check=True)

    try:
        os.makedirs(bd)
        git("init")
        now = time.time()
        claims = os.path.join(d, "src_spec.md")
        write(claims, "# spec", mtime=now - 1000)
        write(os.path.join(bd, "receipt.json"), RECEIPT_OK, mtime=now)
        # untracked files are in the status list too (?? prefix); no commit needed
        code, err = run_hook(d, stop_payload(d))
        assert (code, err) == (0, ""), f"must not report stale when the receipt is newer: {code} {err!r}"
        os.utime(claims, (now + 100, now + 100))
        code, err = run_hook(d, stop_payload(d))
        assert code == 2 and "stale" in err, f"the git list path missed the staleness: {code} {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_non_git_dir_without_claims_env_skips_staleness():
    """A non-git directory with no injected list → skip the staleness check, exit 0.
    With no list source, silence beats a false red — this is a deliberate degradation
    (declared in the docstring), not a defect; this test pins "degradation does not
    become a false red"."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        write(os.path.join(bd, "receipt.json"), RECEIPT_OK)
        code, err = run_hook(d, stop_payload(d))
        assert (code, err) == (0, ""), f"no list source must not produce a false red: {code} {err!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_breakingdiff_files_excluded_from_staleness():
    """Files under .breakingdiff/ itself never appear in the staleness list —
    pending/receipt are always newer than the receipt (just written); without the
    exclusion the hook would report stale forever, i.e. per-turn noise."""
    d, bd = make_project()
    try:
        os.makedirs(bd)
        now = time.time()
        write(os.path.join(bd, "pending"), "", mtime=now)
        write(os.path.join(bd, "receipt.json"), RECEIPT_OK, mtime=now - 100)
        code, err = run_hook(d, stop_payload(d),
                             env_extra={"BD_CLAIMS_FILES": os.path.join(
                                 ".breakingdiff", "pending")})
        assert (code, err) == (0, ""), f"the module's own files in the list would be a permanent false red: {code} {err!r}"
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

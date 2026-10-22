# -*- coding: utf-8 -*-
"""
Regression tests and mutation evidence for provenance itself
==================================================
Provenance tiering is the criterion behind the "verified/unverified" binary. If the tier
label lies — calling self-attestation verified, or letting git-object verification quietly
loosen — the whole binary protocol collapses, and a collapsed one looks exactly like an
intact one. So four things are pinned here:

  1. backward compatibility and format guards for the new Claim fields (defaults must not
     break any existing construction);
  2. self-attested must never be worded as "verified", and must carry an upgrade path;
  3. git-object verification really runs git (measured in a temporary repository), and a
     failure goes red rather than silent;
  4. verification goes through a subprocess argument list, never a shell.

No pytest dependency. Usage: python provenance_test.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from breakingdiff import (Claim, ProvenanceError, SELF_ATTESTED_HINT,
                          antiforgery_line, compare, compare_n, render, render_n)
import provenance
from provenance import ProvenanceResult, summarize_results, verify, verify_all


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


BLOB_TEXT = "line one\nline two\n"


def mk_claim(**kw):
    base = dict(name="c", predicate=lambda x: True, applies=lambda x: True,
                domain_note="d", source="docs/spec.md", quote="line two",
                quote_source=BLOB_TEXT)
    base.update(kw)
    return Claim(**base)


# ── temporary git repository fixture (really runs git; no fake repository self-deception) ───────────────
def make_repo():
    """Create a one-shot git repository with docs/spec.md as two LF lines; return
    (path, full sha, blob path)."""
    d = tempfile.mkdtemp(prefix="bd_prov_")

    def git(*args):
        proc = subprocess.run(["git", "-C", d, *args], capture_output=True)
        assert proc.returncode == 0, f"fixture git {args} failed: {proc.stderr!r}"
        return proc.stdout

    spec = os.path.join(d, "docs", "spec.md")
    os.makedirs(os.path.dirname(spec))
    with open(spec, "wb") as f:            # binary write so Windows text mode cannot turn \n into \r\n
        f.write(BLOB_TEXT.encode("utf-8"))
    git("init")
    git("-c", "core.autocrlf=false", "add", "docs/spec.md")
    git("-c", "user.name=t", "-c", "user.email=t@t",
        "-c", "commit.gpgsign=false", "commit", "-m", "init")
    sha = git("rev-parse", "HEAD").decode("ascii").strip()
    return d, sha, "docs/spec.md"


# ── new Claim fields: backward compatibility + format guards ─────────────────────────
def test_claim_defaults_keep_backward_compatibility():
    """Not passing the new fields = zero change from old behavior. Every existing Claim
    construction in the repository relies on this guarantee."""
    c = mk_claim()
    assert c.source_obj == ""
    assert c.source_kind == "self-attested"


def test_source_kind_whitelist_two_levels_only():
    """Only two tiers this round. The executed/AST tier keeps an interface but no
    implementation — making it constructible would be a false tier report, so it is
    refused outright."""
    with raises(ProvenanceError) as e:
        mk_claim(source_kind="executed")
    assert e.value.reason == "SOURCE_KIND_INVALID"


def test_source_obj_requires_full_lowercase_sha():
    """A short sha is ambiguous (objects with the same prefix may coexist in a
    repository), and uppercase is not git's writing form. The format guard catches it at
    construction; do not wait until verification to find out."""
    with raises(ProvenanceError) as e:
        mk_claim(source_obj="abc123:docs/spec.md")
    assert e.value.reason == "SOURCE_OBJ_FORMAT"
    with raises(ProvenanceError):
        mk_claim(source_obj="A" * 40 + ":docs/spec.md")
    full = "a" * 40
    c = mk_claim(source_kind="git-object", source_obj=f"{full}:docs/spec.md")
    assert c.source_obj == f"{full}:docs/spec.md"


def test_source_obj_path_must_use_forward_slash():
    """git's internal path convention is forward slash. A backslash finds nothing in a git
    object name; rather than reporting "object not found" at verification time, say the
    format is wrong at construction."""
    with raises(ProvenanceError) as e:
        mk_claim(source_obj="a" * 40 + ":docs\\spec.md")
    assert e.value.reason == "BACKSLASH_PATH"


def test_source_obj_contradicts_self_attested_kind():
    """Supplying an external anchor but still marking self-attested — the tier field
    contradicts itself, which means the writer did not think it through; refuse rather
    than guessing on their behalf."""
    with raises(ProvenanceError) as e:
        mk_claim(source_obj="a" * 40 + ":docs/spec.md")   # kind is still the default self-attested
    assert e.value.reason == "KIND_CONTRADICTION"


def test_git_object_kind_requires_source_obj():
    """git-object without an object anchor = nothing verifiable, just self-attestation in
    different words."""
    with raises(ProvenanceError) as e:
        mk_claim(source_kind="git-object")
    assert "source_obj" in str(e.value)


# ── verify: dependency injection and two-tier semantics ────────────────────────────────
def test_verify_requires_explicit_repo_root():
    """repo_root must be injected explicitly (a required keyword argument), never guessed.
    A version that guesses cwd verifies the wrong repository in hook/cross-directory
    scenarios — "verified" against the wrong repository is worse than no verification."""
    c = mk_claim()
    try:
        verify(c)
        raise AssertionError("explicit repo_root should be required (a required keyword argument)")
    except TypeError:
        pass


def test_verify_self_attested_never_claims_verified():
    """A self-attested label must never contain "verified", and must carry an upgrade
    path — the label must be actionable, not a mere warning (otherwise, with everything
    self-attested by default, the label is wallpaper)."""
    res = verify(mk_claim(), repo_root=".")   # repo_root is unused at the self-attested tier
    assert res.verified is False
    assert res.kind == "self-attested"
    assert "git-object verified" not in res.label, "the self-attested label is lying"
    assert "self-attested" in res.label
    assert "source_obj" in res.label, "the upgrade path must appear in the hint"


def test_verify_git_object_happy_path():
    """Measured on a real repository: quote verbatim in the blob → verified, positively
    labeled."""
    d, sha, path = make_repo()
    try:
        res = verify(mk_claim(source_kind="git-object",
                              source_obj=f"{sha}:{path}"), repo_root=d)
        assert res.verified is True
        assert res.kind == "git-object"
        assert "git-object verified" in res.label
        assert sha[:12] in res.label, "a positive label must point back to the object"
        assert res.normalized is False, "LF against LF must not trigger the normalization marker"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_git_object_normalizes_crlf_and_records_it():
    """A working-tree quote is often changed to CRLF by an editor/checkout. Policy is
    pinned: normalize CRLF→LF on both sides, then match, and record the normalization in
    the result — neither a false failure nor silence."""
    d, sha, path = make_repo()
    try:
        # quote_source left empty: the construction-time verbatim check and external-anchor
        # verification are two paths, and this tests the latter (quote coming from a
        # working-tree editor that changed line endings)
        res = verify(mk_claim(source_kind="git-object",
                              source_obj=f"{sha}:{path}",
                              quote="line one\r\nline two\r\n",
                              quote_source=""), repo_root=d)
        assert res.verified is True
        assert res.normalized is True, "normalization that happened must be recorded; it must not pretend to be byte-identical"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_git_object_rejects_absent_quote():
    """quote not in the blob → ProvenanceError. External-anchor verification failure is a
    loud failure and must never degrade to "passes with a warning"."""
    d, sha, path = make_repo()
    try:
        with raises(ProvenanceError) as e:
            verify(mk_claim(source_kind="git-object",
                            source_obj=f"{sha}:{path}",
                            quote="this line is not in the source at all",
                            quote_source=""), repo_root=d)
        assert "blob" in str(e.value)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_missing_object_raises_loudly():
    """Wrong repository root / object absent → git errors, wrapped as ProvenanceError and
    raised. It must not be swallowed into "verification passed"."""
    d = tempfile.mkdtemp(prefix="bd_prov_empty_")
    try:
        with raises(ProvenanceError):
            verify(mk_claim(source_kind="git-object",
                            source_obj="a" * 40 + ":docs/spec.md"), repo_root=d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_blob_size_limit_raises_not_truncates():
    """A blob over the cap must raise. Truncating before an "contains" check would judge a
    false quote in a large file as true — the cap is not a performance optimization, it is
    anti-false-match."""
    d, sha, path = make_repo()
    try:
        with raises(ProvenanceError) as e:
            verify(mk_claim(source_kind="git-object",
                            source_obj=f"{sha}:{path}"),
                   repo_root=d, max_blob_bytes=5)
        assert "cap" in str(e.value) or "bytes" in str(e.value)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_git_runs_without_shell_list_args():
    """The verification command must use an argument list and never a shell — special
    characters in rev/paths are not interpreted a second time by a shell; that is the
    injection surface. Pin the call shape with a fake subprocess."""
    calls = []

    class _FakeProc:
        returncode = 0
        stderr = b""

        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, capture_output=False, **kw):
        calls.append((cmd, kw))
        if "cat-file" in cmd and "-s" in cmd:
            return _FakeProc(b"17")
        return _FakeProc(BLOB_TEXT.encode("utf-8"))

    orig = provenance.subprocess.run
    provenance.subprocess.run = fake_run
    try:
        res = verify(mk_claim(source_kind="git-object",
                              source_obj="a" * 40 + ":docs/spec.md"),
                     repo_root="X:/fake")
        assert res.verified is True
    finally:
        provenance.subprocess.run = orig
    assert calls, "subprocess was never reached; this test is invalid"
    for cmd, kw in calls:
        assert isinstance(cmd, list), "the git command must use an argument list"
        assert not kw.get("shell", False), "shell=True is forbidden"


# ── aggregate presentation ────────────────────────────────────────────────
def test_antiforgery_line_aggregates_with_upgrade_hint():
    """One aggregate line: git-object positively labeled, self-attested with an upgrade
    path, unknown tiers listed explicitly (enumeratively complete; never silently
    dropped)."""
    claims = [SimpleNamespace(source_kind="git-object"),
              SimpleNamespace(source_kind="self-attested"),
              SimpleNamespace(source_kind="self-attested"),
              SimpleNamespace(source_kind="executed")]
    line = antiforgery_line(claims)
    assert line.count("git-object 1 (") == 1
    assert "self-attested 2 (" in line
    assert "promote to git-object" in line, "the upgrade path must be in the aggregate line"
    assert "executed 1 (" in line and "unknown tier" in line, "an unknown tier must also appear explicitly"


def test_verify_all_and_results_line():
    """Aggregate one line after verification: git-object positively "verified x/x",
    self-attested explicitly unverified."""
    d, sha, path = make_repo()
    try:
        claims = [mk_claim(source_kind="git-object", source_obj=f"{sha}:{path}"),
                  mk_claim(name="self-attested one", quote="line one", quote_source=BLOB_TEXT)]
        results = verify_all(claims, repo_root=d)
        assert all(isinstance(r, ProvenanceResult) for r in results)
        line = summarize_results(results)
        assert "git-object verified 1/1" in line
        assert "self-attested 1 not verified" in line
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_render_carries_antiforgery_line_and_anchor():
    """Render side: an aggregate line at the end of the report, plus per-entry positive
    labels for git-object; self-attestation does not spam one line per entry."""
    d, sha, path = make_repo()
    try:
        g = mk_claim(name="anchored", source_kind="git-object",
                     source_obj=f"{sha}:{path}")
        s = mk_claim(name="self-attested one")
        r = compare(g, s, ["a", "b"])
        out = render(g, s, r)
        assert "[Attestation tiers]" in out
        assert "external anchor: git-object" in out, "git-object must be positively labeled per entry"
        assert out.count("self-attested, not verified against an external anchor") == 1, "self-attestation goes only into the aggregate line, not per entry"
        out_n = render_n([g, s], compare_n([g, s], ["a", "b"]))
        assert "[Attestation tiers]" in out_n and "external anchor: git-object" in out_n
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══ 2.2 quote_source_ref line-range external evidence (red-first tests, contract freeze 2026-10-16) ══
# Contract (refinement plan §2.2):
#   · Claim gains quote_source_ref: str = "", not reusing quote_source (the construction-time
#     `in` check and backward compatibility are not broken); format
#     path/to/spec.md@<40-char lowercase hex sha>:L120-L124;
#   · verification reads the corresponding lines of that blob from git and compares them
#     verbatim with quote (verify wiring);
#   · line numbers use the L prefix (no clash with the path colon); the full SHA is forced
#     to 40 chars (consistent with SOURCE_OBJ_RE);
#   · reuse the existing CRLF→LF normalization and record the normalization in the result;
#   · three verification states (the GitPin spirit, aligned with provenance's existing
#     structure): supported / contradicted (a definite mismatch, must not pass) /
#     unproven (the range does not exist).
# API assumptions (if the implementation changes the shape, the red cause turns into
# "implementation vs contract" and goes to the scheduler for a decision):
#   · verification entry = provenance.verify() (normalization/cap/loud-failure philosophy
#     all live there; line-range verification wiring is most natural there);
#   · coupling with source_obj: the verification cases carry both source_obj and
#     source_kind="git-object" (no conflict with the existing construction guards); the
#     standalone shape with only ref and no source_obj is not pinned by contract and is not
#     tested.
# Red-cause distribution in the red-first phase: field absent (TypeError / AttributeError /
# fields probe) → capability absent (the SimpleNamespace discrimination cases: verify
# ignores ref, and a wrong line anchor is not refused).
# Discrimination note: the supported and CRLF cases would falsely go green in the
# intermediate state "field added but verification not wired" (the existing quote-in-blob
# check happens to pass on the same path); their discriminating power is carried by the two
# SimpleNamespace cases (wrong line anchor / out-of-bounds anchor); only when the whole
# group is green and the discrimination cases are green is the implementation complete.

import dataclasses

MULTILINE_BLOB = b"alpha\nbeta\ngamma\ndelta\n"          # L1..L4
CRLF_MULTILINE_BLOB = b"alpha\r\nbeta\r\ngamma\r\ndelta\r\n"


def make_repo_bytes(data: bytes):
    """Parameterized variant of make_repo: arbitrary bytes enter the blob; return
    (repository path, HEAD sha, blob path). Read the blob back after committing as a
    self-check — if Windows text mode or autocrlf changed the fixture bytes, the fixture
    itself goes red first (only when the fixture's control state is true are the cases
    valid)."""
    d = tempfile.mkdtemp(prefix="bd_prov_ref_")

    def git(*args):
        proc = subprocess.run(["git", "-C", d, *args], capture_output=True)
        assert proc.returncode == 0, f"fixture git {args} failed: {proc.stderr!r}"
        return proc.stdout

    spec = os.path.join(d, "docs", "spec.md")
    os.makedirs(os.path.dirname(spec))
    with open(spec, "wb") as f:            # binary write, no line-ending assumption
        f.write(data)
    git("init")
    git("-c", "core.autocrlf=false", "add", "docs/spec.md")
    git("-c", "user.name=t", "-c", "user.email=t@t",
        "-c", "commit.gpgsign=false", "commit", "-m", "init")
    sha = git("rev-parse", "HEAD").decode("ascii").strip()
    back = git("cat-file", "blob", f"{sha}:docs/spec.md")
    assert back == data, f"fixture blob read-back differs from the write: {back!r} != {data!r}"
    return d, sha, "docs/spec.md"


def _verify_outcome(claim, repo_root):
    """The presentation form of a line-range verification failure is not pinned by
    contract (raise ProvenanceError or return a verified=False result); either counts as
    "a definite mismatch". Returns (result or None, exception or None); assertions go
    through this unified exit."""
    try:
        return verify(claim, repo_root=repo_root), None
    except ProvenanceError as e:
        return None, e


def _outcome_text(res, err):
    """Unified extraction of the failure wording: the exception message or the result label."""
    if err is not None:
        return str(err)
    return res.label if res is not None else ""


def _claim_has_ref_field() -> bool:
    return any(f.name == "quote_source_ref" for f in dataclasses.fields(Claim))


# ── 2.2.1 field default and backward compatibility ──────────────────────────────────
def test_quote_source_ref_field_defaults_to_empty():
    """The new field exists and defaults to the empty string: not passing it = zero change
    from old behavior."""
    assert _claim_has_ref_field(), "Claim lacks the quote_source_ref field"
    c = mk_claim()
    assert c.quote_source_ref == ""


def test_quote_source_ref_is_not_reused_as_quote_source():
    """Mutation-evidence surface for "do not reuse quote_source": give ref a legal
    reference and empty quote_source, and construction must succeed — ref is a git
    reference format in which a literal quote cannot appear, so if construction-time
    mistakenly `in`-checks ref as quote_source, every legal construction would be killed."""
    c = mk_claim(quote_source_ref=f"docs/spec.md@{'a' * 40}:L2-L3",
                 quote_source="")
    assert c.quote_source_ref == f"docs/spec.md@{'a' * 40}:L2-L3"


def test_quote_source_in_check_unchanged():
    """The existing construction-time `in` check behavior is unchanged: a quote not inside
    quote_source is still refused. Adding the new field must not touch this existing
    semantics."""
    with raises(ProvenanceError) as e:
        mk_claim(quote="this line is not in the full text", quote_source="some other text")
    assert e.value.reason == "QUOTE_NOT_LITERAL"


# ── 2.2.2 format guards (construction time, same shape as source_obj) ────────────────
def test_quote_source_ref_rejects_sha_not_full_40():
    """The full SHA is forced to 40 chars (consistent with SOURCE_OBJ_RE): a short sha is
    ambiguous, and uppercase is not git's writing form."""
    bad = ["a" * 39, "a" * 41, "A" * 40]
    for s in bad:
        with raises(ProvenanceError) as e:
            mk_claim(quote_source_ref=f"docs/spec.md@{s}:L2-L3")
        assert e.value.reason == "QUOTE_REF_FORMAT", \
            f"{s!r} was let through with no length hint: {e.value}"


def test_quote_source_ref_rejects_malformed_line_range():
    """Line-range format guard: missing L prefix, missing L on the second line number,
    missing @ with mixed colons, incomplete range. The line-number prefix is pinned to L
    (no clash with the path colon)."""
    sha = "a" * 40
    bad_refs = [
        f"docs/spec.md@{sha}:2-3",        # missing L prefix
        f"docs/spec.md@{sha}:L2-3",       # the second line number lacks L
        f"docs/spec.md:{sha}:L2-L3",      # missing @, mixed colons
        f"docs/spec.md@{sha}:L2-",        # incomplete range
    ]
    for ref in bad_refs:
        with raises(ProvenanceError) as e:
            mk_claim(quote_source_ref=ref)
        assert str(e.value), f"{ref!r} was let through with no explanation"


# ── 2.2.3 line-range verbatim verification (measured on a real repository) ─────────────────────────
def test_verify_line_range_supported_when_verbatim():
    """quote verbatim-consistent with the declared line range → supported."""
    assert _claim_has_ref_field(), "the quote_source_ref field does not exist — implement the field before discussing verification wiring"
    d, sha, path = make_repo_bytes(MULTILINE_BLOB)
    try:
        c = mk_claim(source_kind="git-object", source_obj=f"{sha}:{path}",
                     quote="beta\ngamma", quote_source="",
                     quote_source_ref=f"{path}@{sha}:L2-L3")
        res, err = _verify_outcome(c, d)
        assert err is None, f"a verbatim-consistent line range must not fail verification: {err}"
        assert res is not None and res.verified is True
        assert res.kind == "git-object"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_rejects_quote_anchored_to_wrong_lines():
    """Discrimination case: quote is in the blob (L1) but anchored to L2-L3 — a blob
    containment check alone would pass it, while line-range verbatim comparison must
    refuse. quote in the file does not equal quote on the declared lines; that is exactly
    the anti-forgery value of line-range external evidence over source_obj."""
    d, sha, path = make_repo_bytes(MULTILINE_BLOB)
    try:
        c = SimpleNamespace(source_kind="git-object", name="wrong line anchor",
                            source_obj=f"{sha}:{path}",
                            quote="alpha", quote_source="",
                            quote_source_ref=f"{path}@{sha}:L2-L3")
        res, err = _verify_outcome(c, d)
        assert res is None or res.verified is not True, \
            "quote in the blob but not on the declared line range was worded as verified — line-range verification is decoration"
        assert _outcome_text(res, err), "a mismatch must have an explicit wording"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_unproven_when_line_range_out_of_bounds():
    """Referencing a nonexistent line range → unproven (must not pass). quote itself is in
    the blob, excluding the "quote mismatch" confounder, to pin the "range out of bounds"
    failure state alone."""
    d, sha, path = make_repo_bytes(MULTILINE_BLOB)
    try:
        c = SimpleNamespace(source_kind="git-object", name="out-of-bounds anchor",
                            source_obj=f"{sha}:{path}",
                            quote="beta\ngamma", quote_source="",
                            quote_source_ref=f"{path}@{sha}:L90-L99")
        res, err = _verify_outcome(c, d)
        assert res is None or res.verified is not True, \
            "an out-of-bounds line range was worded as verified — the unproven state is lost"
        assert _outcome_text(res, err), "unproven needs a wording too; never silent"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verify_line_range_normalizes_crlf_and_records():
    """CRLF fixture measurement: the blob has CRLF and the quote has LF; line-range
    verification still matches after normalization, and the normalization is recorded in
    the result. The order of normalization and line slicing is a real implementation risk
    (slicing before normalizing leaves the carriage return at the line end); this case pins
    "normalization takes effect before comparison"."""
    assert _claim_has_ref_field(), "the quote_source_ref field does not exist"
    d, sha, path = make_repo_bytes(CRLF_MULTILINE_BLOB)
    try:
        c = mk_claim(source_kind="git-object", source_obj=f"{sha}:{path}",
                     quote="beta\ngamma", quote_source="",
                     quote_source_ref=f"{path}@{sha}:L2-L3")
        res, err = _verify_outcome(c, d)
        assert err is None, f"should match after normalization; it must not fail falsely: {err}"
        assert res is not None and res.verified is True
        assert res.normalized is True, "normalization that happened must be recorded; it must not pretend to be byte-identical"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_line_range_failure_modes_are_distinguishable():
    """The three-state spirit: the failure wording of a line-content mismatch
    (contradicted) and that of an out-of-bounds line range (unproven) must be
    distinguishable — if both failures share one sentence, consumers cannot reconcile the
    three-state semantics."""
    d, sha, path = make_repo_bytes(MULTILINE_BLOB)
    try:
        wrong = SimpleNamespace(source_kind="git-object", name="wrong line anchor",
                                source_obj=f"{sha}:{path}",
                                quote="alpha", quote_source="",
                                quote_source_ref=f"{path}@{sha}:L2-L3")
        oob = SimpleNamespace(source_kind="git-object", name="out-of-bounds anchor",
                              source_obj=f"{sha}:{path}",
                              quote="beta\ngamma", quote_source="",
                              quote_source_ref=f"{path}@{sha}:L90-L99")
        w_res, w_err = _verify_outcome(wrong, d)
        o_res, o_err = _verify_outcome(oob, d)
        assert w_res is None or w_res.verified is not True, "a wrong line anchor must not pass"
        assert o_res is None or o_res.verified is not True, "an out-of-bounds anchor must not pass"
        w_text, o_text = _outcome_text(w_res, w_err), _outcome_text(o_res, o_err)
        assert w_text and o_text, "both failures need a wording"
        assert w_text != o_text, "the mismatch and unproven wordings must be distinguishable (three-state spirit)"
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

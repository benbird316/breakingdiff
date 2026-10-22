# -*- coding: utf-8 -*-
"""
provenance — provenance tiers and the minimal external-anchor implementation (two tiers: git-object / self-attested)
====================================================================================================================
Claim carries two tier fields, source_kind / source_obj (format guards run at Claim construction;
the source of truth for the format constants is breakingdiff.py). This module answers one question:
how far this tier can be trusted.

## Honest boundary (what the tiers defend against and what they do not)

    self-attested  ≈ SLSA L1: the document exists (anti-sloppiness) — it only proves "someone declared this"
    git-object     ≈ SLSA L2: content addressing (anti-post-hoc-tampering) — the quote is verbatim in
                     some commit's blob; change the source and you must change the sha
    What neither tier defends against: source forgery. git show only proves "the quote is in some object
    of some repository", not "that repository is a trustworthy upstream"; the client party controls
    everything, so forging a repository that satisfies verification costs the same as forging the
    declaration. The executed / AST tier is an interface left unimplemented.

## Label discipline (the tier is a verified/unverified binary criterion; the label is only presentation)

  · self-attested must never be worded as "verified", and the hint must carry the upgrade path (actionable, not wallpaper);
  · git-object is labeled "verified" only after verification passes; a failure is a ProvenanceError (loud failure);
  · aggregate into one line rather than per-item noise (label fatigue degrades the tier into wallpaper).

## The four traps of a minimal git show implementation (pinned by the architect's review)

  1. repo_root is dependency-injected (required keyword argument), never guessed — a version that guesses
     cwd verifies the wrong repository in hook / cross-directory scenarios, and "verified" against the
     wrong repository is worse than no verification;
  2. subprocess list arguments, not through the shell — special characters in rev/paths are not interpreted twice;
  3. line-ending policy is hard-wired: normalize both sides CRLF→LF before the verbatim match, and record the
     normalization in the result (normalized=True). The blob is committed bytes while the working-tree quote is
     often re-lined by editors / checkout; a hard byte-for-byte match would wrongly reject the
     most common real quote;
  4. blob size cap: over the cap raises ProvenanceError rather than truncating — truncating and then doing a
     "contains" check would judge a fake quote in a large file as true; the cap is not a performance optimization
     but anti-false-match.

Usage:

    from provenance import verify, verify_all, summarize_results
    res = verify(claim, repo_root="F:/some/repo")     # git-object tier; a failure raises
    line = summarize_results(verify_all(claims, repo_root=root))  # audit aggregate line

Command line: python provenance.py --self-check    # run this module's own regression
"""
import subprocess
import sys
import os
from dataclasses import dataclass
from typing import Any, List, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from breakingdiff import (ProvenanceError, SELF_ATTESTED_HINT, SOURCE_KINDS,
                          SOURCE_OBJ_RE, QUOTE_SOURCE_REF_RE, antiforgery_line)

DEFAULT_MAX_BLOB_BYTES = 5 * 1024 * 1024   # 5 MB; quote checks should not touch larger blobs


@dataclass(frozen=True)
class ProvenanceResult:
    """Verification result for a single account. verified=False belongs only to self-attested —
    the git-object tier raises outright when verification fails, and never returns a "pass with a
    warning"."""
    claim_name: str
    kind: str
    verified: bool
    label: str
    source_obj: str = ""
    normalized: bool = False     # whether both sides were normalized CRLF→LF before matching (the receipt/report must record it)


def _git(repo_root: str, *args: str) -> bytes:
    """Run git directly with list arguments, not through the shell. On failure, raise
    ProvenanceError carrying stderr."""
    cmd = ["git", "-C", repo_root, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError:
        raise ProvenanceError("git is unavailable (no git in PATH); external-anchor verification cannot proceed")
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise ProvenanceError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout


def _parse_source_obj(source_obj: str) -> Any:
    """Split "sha:path". The format was already guarded at Claim construction; it is guarded
    again here because this module also accepts hand-built lightweight objects, and does not
    assume the caller passed through that gate."""
    m = SOURCE_OBJ_RE.fullmatch(source_obj or "")
    if not m:
        raise ProvenanceError(
            f"source_obj must be \"full 40-char lowercase hex sha:path-in-repo\", got {source_obj!r}")
    path = m.group(2)
    if "\\" in path:
        raise ProvenanceError(
            f"source_obj paths use forward slashes (git's internal convention), got backslashes: {source_obj!r}")
    return m.group(1), path

def _parse_quote_source_ref(ref: str) -> Any:
    """Split "path@sha:Lstart-Lend". Same reasoning as _parse_source_obj: the format was already
    guarded at Claim construction, and it is guarded again here because this module also accepts
    hand-built lightweight objects."""
    m = QUOTE_SOURCE_REF_RE.fullmatch(ref or "")
    if not m:
        raise ProvenanceError(
            f"quote_source_ref must be \"path-in-repo@full 40-char lowercase hex sha:Lstart-Lend\", "
            f"got {ref!r}")
    return m.group(1), m.group(2), int(m.group(3)), int(m.group(4))



def verify(claim: Any, *, repo_root: str,
           max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> ProvenanceResult:
    """Verify according to claim.source_kind.

    self-attested → return a result with verified=False, the label carrying the upgrade path;
    git-object    → cat-file -s for the size (raise when over the cap) → cat-file blob for the
                    content → normalize both sides CRLF→LF, then match verbatim; on failure raise
                    ProvenanceError. With quote_source_ref, also verify the line range: the quote
                    must be verbatim equal to the blob content at the declared lines; a range out
                    of bounds = unprovable, a content mismatch = mismatch, and both failures raise
                    loudly with distinguishable wording.

    repo_root is a required keyword argument: dependency injection, never guessing cwd.
    """
    if not repo_root:
        raise ProvenanceError(
            "repo_root must be injected explicitly (an empty value will not do). \"Verified\" "
            "against the wrong repository is worse than no verification, so do not guess any default")
    kind = claim.source_kind
    name = claim.name
    if kind == "self-attested":
        return ProvenanceResult(
            claim_name=name, kind=kind, verified=False,
            label=f"[{name}] {SELF_ATTESTED_HINT}")
    if kind != "git-object":
        raise ProvenanceError(
            f"[{name}] unknown provenance tier {kind!r} (this round supports only "
            f"{'|'.join(SOURCE_KINDS)}); refusing to verify — silently treating it as self-attested "
            "would hide an unknown tier inside \"no error\"")
    sha, path = _parse_source_obj(claim.source_obj)
    obj = f"{sha}:{path}"
    size = int(_git(repo_root, "cat-file", "-s", obj).decode("ascii").strip())
    if size > max_blob_bytes:
        raise ProvenanceError(
            f"[{name}] blob {obj} is {size} bytes, over the cap {max_blob_bytes}. "
            "Over the cap fails rather than truncates: truncating and then doing a \"contains\" "
            "check would judge a fake quote as true. If you really must verify a large file, raise "
            "max_blob_bytes and record why")
    blob = _git(repo_root, "cat-file", "blob", obj)
    blob_norm = blob.replace(b"\r\n", b"\n")
    quote_norm = claim.quote.replace("\r\n", "\n").encode("utf-8")
    normalized = (blob != blob_norm) or ("\r\n" in claim.quote)
    ref = getattr(claim, "quote_source_ref", "")
    if not ref:
        if quote_norm not in blob_norm:
            raise ProvenanceError(
                f"[{name}] external-anchor verification failed: quote is not in the blob of {obj}"
                + (" (CRLF→LF normalization applied)" if normalized else "")
                + ". The quote does not match the external anchor object, so this claim's tier does not hold")
        label = (f"[{name}] git-object verified: quote is verbatim in the blob of {sha[:12]}…:{path}"
                 + (" (matched after CRLF→LF normalization on both sides)" if normalized else ""))
        return ProvenanceResult(claim_name=name, kind=kind, verified=True,
                                label=label, source_obj=claim.source_obj,
                                normalized=normalized)

    # Line-range anchor (2.2): quote being in the blob does not mean the quote is on the declared
    # lines; a containment check does not cover a line-range declaration, which must be compared
    # verbatim on its own.
    r_path, r_sha, start, end = _parse_quote_source_ref(ref)
    if (r_sha, r_path) == (sha, path):
        r_norm = normalized
        lines = blob_norm.splitlines()
    else:
        r_obj = f"{r_sha}:{r_path}"
        r_size = int(_git(repo_root, "cat-file", "-s", r_obj).decode("ascii").strip())
        if r_size > max_blob_bytes:
            raise ProvenanceError(
                f"[{name}] blob {r_obj} is {r_size} bytes, over the cap {max_blob_bytes}. "
                "Over the cap fails rather than truncates: truncating and then doing a \"contains\" "
                "check would judge a fake quote as true. If you really must verify a large file, raise "
                "max_blob_bytes and record why")
        r_blob = _git(repo_root, "cat-file", "blob", r_obj)
        r_norm = r_blob != r_blob.replace(b"\r\n", b"\n") or "\r\n" in claim.quote
        lines = r_blob.replace(b"\r\n", b"\n").splitlines()
    if start < 1 or end < start or end > len(lines):
        raise ProvenanceError(
            f"[{name}] line-range verification unprovable: the declared L{start}-L{end} exceeds "
            f"the actual line count {len(lines)} of {r_sha[:12]}…:{r_path}; the line range does not "
            "exist and the reference is unprovable — never pass silently")
    segment = b"\n".join(lines[start - 1:end])
    if segment != quote_norm:
        raise ProvenanceError(
            f"[{name}] line-range verification mismatch: the quote does not match the content of "
            f"lines L{start}-L{end} of {r_sha[:12]}…:{r_path}"
            + (" (CRLF→LF normalization applied)" if r_norm else "")
            + ". A quote in the blob does not mean the quote is on the declared lines; the "
              "line-range anchor does not hold")
    label = (f"[{name}] git-object verified: quote is verbatim in lines L{start}-L{end} of "
             f"{r_sha[:12]}…:{r_path}"
             + (" (matched after CRLF→LF normalization on both sides)" if r_norm else ""))
    return ProvenanceResult(claim_name=name, kind=kind, verified=True,
                            label=label, source_obj=claim.source_obj,
                            normalized=r_norm)


def verify_all(claims: Sequence[Any], *, repo_root: str,
               max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> List[ProvenanceResult]:
    """Batch verification. Any git-object failure raises (loud failure, never degraded into a
    list)."""
    return [verify(c, repo_root=repo_root, max_blob_bytes=max_blob_bytes)
            for c in claims]


def summarize(claims: Sequence[Any]) -> str:
    """Claim-level aggregate line (no git, only the tier fields). Used by the rendering side;
    the source of truth is breakingdiff.antiforgery_line, and this is a forwarding alias."""
    return antiforgery_line(claims)


def summarize_results(results: Sequence[ProvenanceResult]) -> str:
    """One aggregate line after verification: git-object marked positively with verified counts,
    self-attested explicitly unverified. verify's teeth are the verified/unverified binary — a
    self-attested count must never be worded as verified."""
    n_git = sum(1 for r in results if r.kind == "git-object")
    ok_git = sum(1 for r in results if r.kind == "git-object" and r.verified)
    n_self = sum(1 for r in results if r.kind == "self-attested")
    seen = {"git-object", "self-attested"}
    parts = []
    if n_git:
        parts.append(f"git-object verified {ok_git}/{n_git}")
    if n_self:
        parts.append(f"self-attested {n_self} not verified (supply source_obj to promote to git-object)")
    for r in results:
        if r.kind not in seen:
            seen.add(r.kind)
            parts.append(f"{r.kind} {sum(1 for x in results if x.kind == r.kind)}"
                         " (unknown tier, listed explicitly)")
    return "[Attestation verification] " + ("; ".join(parts) if parts else "no verification records")


def main() -> int:
    if "--self-check" in sys.argv:
        import provenance_test
        return provenance_test.main()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

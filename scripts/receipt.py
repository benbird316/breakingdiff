# -*- coding: utf-8 -*-
"""
receipt — deterministic JSON receipt (reconciliation context = a single delivery window)
========================================================================================
After compare / compare_n finishes, write one machine-reconcilable receipt. It answers two
questions: "what did this run read" and "what does the auditor re-execute to compare".

## Honest boundary (first, what it is not)

The receipt is produced by the same party that runs compare — someone who does not run compare
can hand-write an all-green receipt and it is equally green. So a receipt is in essence one more
layer of self-attestation, and its subject of verification is **re-execution**: the auditor (or
the hook) re-runs per rerun_cmd and compares byte for byte, which is the standard action for
verifying a receipt. This module can promise only two things: determinism (the same input
necessarily produces the same bytes) and field completeness (nothing the reconciliation needs is
missing).

## Three exit tiers (business failure and runtime error never mix)

    0  pass (including: no blind-written expectation to reconcile — no expectation, no gate)
    1  gate failure (single source: reconcile finds a surprise; see the expected block below)
    2  runtime error (carried by ReceiptError and other exceptions; the hook/outer layer maps it to 2)

The cost of mixing tiers is concrete: the hook layer gets one code and cannot tell
"should block" from "should fix the tool".

## Field contract (envelope + payload, two parts)

Envelope (who ran this, how it is replayed):
    schema_version     contract version; bumped when the field table changes
    run_kind           "pairwise" | "nway". Four-quadrant 4-counter and N-account shapes
                       are two readout families; without this key, reconcile has no key
                       to compare for compare_n
    claims_identity    identity reconciliation key: {name, predicate, applies} for every
                       account, as module_name.qualname. ★ It is an identity key, not a
                       completeness proof — changing a function body without renaming leaves
                       the key unchanged and tamper resistance at zero; tamper resistance goes
                       through provenance (the external anchor), not through this field
    rerun_cmd          replay command. Relative paths are enforced (absolute paths are
                       structurally rejected) — an absolute path becomes a lie after changing
                       machines or directories
    bd_home            absolute path of the skill repository root for this run. Distribution
                       diagnostic metadata, not a reconciliation key (reconcile does not
                       compare it; see the determinism iron rules for the exemption)
    bd_source          resolution level of bd_home; enum source of truth = bd_paths.SOURCES
    version            version number, read from {bd_home}/VERSION; semver single source of
                       truth (same regex and same file as version_stamp.py)

Payload (readout and provenance counts):
    domain_digest      {size, first, last} partial digest. It captures only "did the comparison
                       domain change" and does not pretend to be a completeness proof; domain
                       must be an already-materialized sequence, because a generator is consumed
                       by compare and the digest then silently reads as 0 points
    counters           pairwise: common/divergence/dominance/neither/
                       out_of_domain/total
                       nway: all_true/all_false/split/out_of_domain/total/
                       outliers/pioneers (account name → count, sparse, zero entries omitted)/
                       ratchet_total/ratchet_trusted/anchor
    witnesses          witness list (stringified). Subject to max_witness truncation and
                       discovery order, it is only soft-reconciled and never enters the gate
    max_witness        witness truncation threshold — you must know it to read witnesses
    provenance_summary provenance tier counts (bucketed by source_kind as-is, enumeration
                       complete; an unknown tier also appears explicitly)
    expected           blind-write reconciliation block, null when not reconciled (see A4:
                       write_expected/reconcile). null ≠ reconciled — never having reconciled
                       and having reconciled are not the same thing, so this key must not be
                       omitted

## Blind-written expectations (write_expected → compare → reconcile; audit for third-party review)

The expectation lands on disk before the readout. Minimal schema: schema_version / run_kind /
claims_identity / domain_digest / expected_counters + written_marker (content addressing, see below).

reconcile has two tiers: counters are **hard-reconciled** — run_kind / claims_identity /
domain_digest / counters compared key by key, and a missing key, an extra key, or any inequality
sets surprise=true plus a difference list (with both values), which is the only source of gate
failure; the witness list is **soft-reconciled** — differences only enter witness_notes and do
not enter the gate, because witnesses are subject to max_witness truncation and discovery order,
and a hard comparison necessarily produces false positives.

The reconciliation context = **a single delivery window**: if the account changes after the blind
write (even with the same behavior and the same name), a claims_identity change is a surprise —
that is the correct signal of "the expectation expired", not a false alarm; cross-session
reconciliation is not done here (replay and third-party verification go through rerun_cmd and audit).

Honest boundary (what the blind write defends against and what it does not): the order "write the
expectation first, run the readout afterwards" can never be proven on this machine (the client
party controls everything) — mtime is forgeable (one line of os.utime) and clone/checkout resets
it; the token check only guards against "forgot to write first" (an expectation not produced by
write_expected in this process is refused at gate reconciliation). mtime is recorded in the
receipt only as a sloppiness guard, explicitly downgraded, not anti-forgery. The real external
evidence is **third-party auditability**: the expected file and the receipt land on disk one after
the other in git history, so "writing the expectation after seeing the result" leaves an auditable
trace — written_marker in the expected file is the sha256 of its content, the receipt records the
marker seen at reconciliation, and if the expectation is touched afterwards, audit fails the check
on the spot.

## Determinism iron rules

sort_keys fixes key order + ensure_ascii=False + UTF-8 without BOM + read-back comparison after
writing + reconciliation keys contain no timestamp + no absolute paths. Acceptance is exactly
three checks: delete the receipt and rerun, byte-identical; rerun from a different CWD,
byte-identical; static assertion that there is no timestamp or absolute path.

B7 narrowing boundary (M-DIST2): the envelope adds three fields bd_home/bd_source/version, and
reconcile's reconciliation key set does not take them (diagnostic metadata, not payload); bd_home
is the running machine's absolute path, and cross-machine byte identity is not promised — this is
honest degradation, not an exception leak; when cross-machine comparable bytes are needed, strip
the three fields before comparing. The schema_version field itself is outside the iron-rule
exemption and is refreshed by hand by the upgrade script along with field-table changes (schema
1→2 is the same precedent).

Usage:

    from receipt import receipt_from_pairwise, write_receipt, gate_exit_code
    r = compare(P, Q, domain)
    rc = receipt_from_pairwise(P, Q, r, domain=domain, rerun_cmd="python run.py")
    write_receipt(rc, ".breakingdiff/receipt.json")
    sys.exit(gate_exit_code(rc))      # an exception blows up on its own → the outer layer maps it to 2

Command line: python receipt.py --self-check    # run this module's own regression
"""
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# bd_home self-resolution reuses bd_paths' four-level resolution, and the enum source of truth
# also references its SOURCES — writing the enum twice would make the receipt's self-report drift
# along with the source of truth
from bd_paths import BdPathError, SOURCES, resolve_bd_home

# B7 (M-DIST2): the envelope gains three distribution diagnostic fields bd_home/bd_source/version;
# the field table bump increments — reconcile's reconciliation key set does not change because of
# it (see the _diff comment).
SCHEMA_VERSION = 2
EXIT_PASS = 0
EXIT_GATE_FAIL = 1
EXIT_RUNTIME_ERROR = 2

_RUN_KINDS = ("pairwise", "nway")

# The three sources of an absolute path: a drive letter (F:\, F:/), UNC (\\host\share), and a
# leading single slash. The single slash must be checked explicitly: since Python 3.13
# ntpath.isabs no longer returns True for "/x" (it is classified as drive-relative), so isabs
# alone would miss it.
# The UNC separator is a single backslash (\\host\share), and the character class [\\/] also
# accepts the forward-slash spelling — B7 review G1: it was once written with \\\\ at the end
# (a double-backslash separator), which never matches actual UNC text.
_ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]|\\\\[A-Za-z0-9_.]+[\\/]")


class ReceiptError(ValueError):
    """Receipt contract violation or write verification failure. Runtime-error semantics → the
    outer layer maps it to exit code 2.

    Structured field (i18n Phase 0): `reason` is a stable criterion code; the message text is
    translated into English.
    """

    def __init__(self, message: str, *, reason: str = "UNSPECIFIED"):
        super().__init__(message)
        self.reason = reason


def _s(x: Any) -> str:
    """Stringify a parameter point/witness: strings as-is, everything else via repr (more
    reconcilable than str)."""
    return x if isinstance(x, str) else repr(x)


def _fn_id(fn: Any) -> str:
    """Function identity string: module name.qualname.

    A callable without a qualname (partial, functor) degrades to a type description — the
    degradation must also have a stable shape, and must not raise and blow up the whole receipt.
    """
    mod = getattr(fn, "__module__", None)
    qn = getattr(fn, "__qualname__", None)
    if mod and qn:
        return f"{mod}.{qn}"
    t = type(fn)
    return f"<unnamed:{t.__module__}.{t.__name__}>"


def claims_identity_of(claims: Sequence[Any]) -> List[Dict[str, str]]:
    """Identity reconciliation key. Order = input order: in pairwise the P/Q positions carry
    semantics (swapping them swaps the divergence/dominance columns), so do not sort on your own;
    nway follows the result.names order supplied by the caller."""
    return [{"name": c.name,
             "predicate": _fn_id(c.predicate),
             "applies": _fn_id(c.applies)} for c in claims]


def domain_digest_of(domain: Sequence[Any]) -> Dict[str, Any]:
    """Comparison domain partial digest: size + first and last points. Enough to capture "did the
    domain change", without pretending to be a completeness proof."""
    if not isinstance(domain, (list, tuple)):
        raise ReceiptError(
            "[RC:DOMAIN_NOT_MATERIALIZED] domain must be an already-materialized list/tuple. "
            "A generator is consumed by compare, so the receipt can only digest an empty sequence "
            "afterwards — a size=0 digest looks perfectly normal, which is the most typical silent "
            "failure. Call list(domain) before passing it in.",
            reason="DOMAIN_NOT_MATERIALIZED")
    if not domain:
        return {"size": 0, "first": None, "last": None}
    return {"size": len(domain), "first": _s(domain[0]), "last": _s(domain[-1])}


def provenance_summary(claims: Sequence[Any]) -> Dict[str, int]:
    """Bucket counts by source_kind as-is. Keys are not narrowed by an allowlist: when an
    executed/AST tier is added later, the receipt contract does not need to change, and an
    unknown tier also appears explicitly in the counts (enumeration complete)."""
    out: Dict[str, int] = {}
    for c in claims:
        k = getattr(c, "source_kind", "self-attested")
        out[k] = out.get(k, 0) + 1
    return out


def _check_rerun_cmd(rerun_cmd: str) -> str:
    if not isinstance(rerun_cmd, str) or not rerun_cmd.strip():
        raise ReceiptError(
            "rerun_cmd is missing. It is the anchor the auditor re-executes against — the "
            "receipt's subject of verification is exactly \"rerun per it and compare byte for "
            "byte\", and without it the receipt degrades into a self-attesting slip of paper.")
    if (os.path.isabs(rerun_cmd) or _ABS_PATH_RE.search(rerun_cmd)
            or rerun_cmd.startswith(("/", "\\"))):
        raise ReceiptError(
            f"rerun_cmd must use a relative path, got an absolute path: {rerun_cmd!r}. "
            "An absolute path becomes a lie after changing machines or directories; to locate "
            "this repository, use a relative path (in the hook scenario the host provides the "
            "project root).")
    return rerun_cmd


def _check_run_kind(run_kind: str) -> str:
    if run_kind not in _RUN_KINDS:
        raise ReceiptError(
            f"run_kind must be {'|'.join(_RUN_KINDS)}, got {run_kind!r}. "
            "Four-quadrant 4-counter and N-account shapes are two readout families; "
            "reconciling them together is reconciling nothing.")
    return run_kind


def validate_dispatch_fields(receipt: Dict[str, Any]) -> None:
    """Structural validation of the three distribution fields, a verification surface that
    validates at construction time (red text prefixed with [receipt]).

    Non-empty str bd_home / bd_source inside the enum / semver version. It is a public function
    so tests can call it directly, rather than hiding it in the constructor — the validation
    rules themselves are part of the contract.
    """
    v = receipt.get("bd_home")
    if not isinstance(v, str) or not v.strip():
        raise ReceiptError(
            f"[receipt] bd_home must be a non-empty string, got {v!r} (a missing field and an "
            "empty string both count as missing — a distribution diagnostic field has no \"leave "
            "it empty and reuse the old value\")")
    if receipt.get("bd_source") not in SOURCES:
        raise ReceiptError(
            f"[receipt] bd_source {receipt.get('bd_source')!r} is not in the enum; "
            f"legal values = {sorted(SOURCES)}")
    ver = receipt.get("version")
    if not isinstance(ver, str) or not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        raise ReceiptError(
            f"[receipt] version {ver!r} does not match semver ^\\d+\\.\\d+\\.\\d+$ — "
            "a v prefix or a two-part version is illegal; the version in the receipt must be "
            "directly comparable with the VERSION file")


def _read_version_file(bd_home: str) -> str:
    """Read {bd_home}/VERSION (single-line semver). Missing or illegal → ReceiptError.

    Single source of truth = the repository-root VERSION file; version_stamp.py uses the same
    file and the same regex; when the two readings diverge, the VERSION file is right and the
    code is wrong.
    """
    path = os.path.join(bd_home, "VERSION")
    if not os.path.isfile(path):
        raise ReceiptError(
            f"[receipt] {path} does not exist — the version field has nothing to self-resolve "
            "from; receipt construction fails loudly rather than substituting an approximation")
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", text):
        raise ReceiptError(
            f"[receipt] {path} content {text!r} is not semver ^\\d+\\.\\d+\\.\\d+$")
    return text


def _self_resolve_dispatch(bd_home: Optional[str], bd_source: Optional[str],
                           version: Optional[str]) -> Tuple[str, str, str]:
    """Self-resolve missing fields one by one (when None: resolve_bd_home() + read VERSION).

    bd_home/bd_source share one resolve_bd_home() call — they are two halves of the same
    resolution, and resolving them separately may yield different sources. Any step failing raises
    ReceiptError and exits loudly — the receipt must truthfully report the running environment; if
    it cannot self-resolve, fail, do not silently degrade and fill in fake values.
    """
    if bd_home is None or bd_source is None:
        try:
            resolved_home, resolved_source = resolve_bd_home()
        except BdPathError as e:
            raise ReceiptError(f"[receipt] bd_home self-resolution failed: {e}")
        if bd_home is None:
            bd_home = resolved_home
        if bd_source is None:
            bd_source = resolved_source
    if version is None:
        version = _read_version_file(bd_home)
    return bd_home, bd_source, version


def build_receipt(*, run_kind: str, claims_identity: List[Dict[str, str]],
                  domain_digest: Dict[str, Any], counters: Dict[str, Any],
                  witnesses: Dict[str, List[str]], max_witness: int,
                  provenance_summary: Dict[str, int], rerun_cmd: str,
                  expected: Optional[Dict[str, Any]] = None,
                  bd_home: Optional[str] = None,
                  bd_source: Optional[str] = None,
                  version: Optional[str] = None) -> Dict[str, Any]:
    """Assemble the receipt dict. The field table is the contract (see the module docstring);
    the key set is fixed.

    Three distribution fields (B7 M-DIST2): None fields are self-resolved one by one —
    bd_home/bd_source go through resolve_bd_home(), version reads {effective bd_home}/VERSION;
    when all are injected explicitly, no disk is touched (test isolation path). The normal case
    is passing all three or none; the mixed form that injects only bd_home is for tests that aim
    red at a specific spot (for example the missing-VERSION negative case). Construction runs
    validate_dispatch_fields, and an illegal value fails loudly with ReceiptError on the spot.
    """
    bd_home, bd_source, version = _self_resolve_dispatch(bd_home, bd_source, version)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "run_kind": _check_run_kind(run_kind),
        "claims_identity": claims_identity,
        "domain_digest": domain_digest,
        "counters": counters,
        "witnesses": witnesses,
        "max_witness": max_witness,
        "provenance_summary": provenance_summary,
        "rerun_cmd": _check_rerun_cmd(rerun_cmd),
        "expected": expected,
        "bd_home": bd_home,
        "bd_source": bd_source,
        "version": version,
    }
    validate_dispatch_fields(receipt)
    return receipt


def receipt_from_pairwise(P: Any, Q: Any, result: Any, *, domain: Sequence[Any],
                          rerun_cmd: str) -> Dict[str, Any]:
    """Assemble a receipt from compare's DiffResult. claims_identity keeps the P,Q order —
    swapping the two accounts swaps the divergence/dominance columns, so the order carries
    semantics and is not sorted."""
    counters = {
        "common": result.common,
        "divergence": result.divergence,
        "dominance": result.dominance,
        "neither": result.neither,
        "out_of_domain": result.out_of_domain,
        "total": result.total,
    }
    witnesses = {
        "divergence": [_s(w) for w in result.divergence_witnesses],
        "dominance": [_s(w) for w in result.dominance_witnesses],
    }
    return build_receipt(
        run_kind="pairwise",
        claims_identity=claims_identity_of([P, Q]),
        domain_digest=domain_digest_of(domain),
        counters=counters, witnesses=witnesses,
        max_witness=result.max_witness,
        provenance_summary=provenance_summary([P, Q]),
        rerun_cmd=rerun_cmd)


def receipt_from_nway(claims: List[Any], result: Any, *,
                      domain: Sequence[Any], rerun_cmd: str) -> Dict[str, Any]:
    """Assemble a receipt from compare_n's NWayResult. claims_identity follows result.names
    (the final order after order_key reordering) — the ratchet counts depend on this order, and
    a different order means different readouts; the receipt must record the order that actually
    participated in the computation, not the order the caller passed in."""
    by_name: Dict[str, Any] = {}
    for c in claims:
        if c.name in by_name:
            raise ReceiptError(
                f"account name {c.name!r} is duplicated. The receipt maps outliers/pioneers "
                "onto account names, so a collision makes the mapping ambiguous — give every "
                "account a unique name first.")
        by_name[c.name] = c
    ordered = [by_name[n] for n in result.names]
    counters = {
        "all_true": result.all_true,
        "all_false": result.all_false,
        "split": result.split,
        "out_of_domain": result.out_of_domain,
        "total": result.total,
        "outliers": {result.names[i]: n for i, n in result.outliers.items()},
        "pioneers": {result.names[i]: n for i, n in result.pioneers.items()},
        "ratchet_total": result.ratchet_total,
        "ratchet_trusted": result.ratchet_trusted,
        "anchor": result.anchor,
    }
    witnesses = {
        "split": [_s(w) for w in result.split_witnesses],
        "ratchet": [f"{result.names[j]}→{result.names[k]}@{_s(x)}"
                    for j, k, x in result.ratchet_witnesses],
    }
    return build_receipt(
        run_kind="nway",
        claims_identity=claims_identity_of(ordered),
        domain_digest=domain_digest_of(domain),
        counters=counters, witnesses=witnesses,
        max_witness=result.max_witness,
        provenance_summary=provenance_summary(ordered),
        rerun_cmd=rerun_cmd)


# ── Writing to disk: the three determinism pieces + read-back ───────────

def _canonical_bytes(obj: Any) -> bytes:
    """Fixed byte shape: sort_keys fixes key order, ensure_ascii=False keeps the original
    characters, no BOM, one trailing newline. Every write (receipt and expectation) shares this
    shape."""
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n").encode("utf-8")


def write_receipt(receipt: Dict[str, Any], path: str) -> None:
    """Write to disk and compare the read-back. "Written" is defined by the read-back result,
    not by the intent to write."""
    _write_canonical(receipt, path)


def _write_canonical(obj: Any, path: str) -> None:
    data = _canonical_bytes(obj)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    _verify_bytes(path, data)


def _verify_bytes(path: str, data: bytes) -> None:
    with open(path, "rb") as f:
        back = f.read()
    if back != data:
        raise ReceiptError(
            f"Write/read-back comparison failed: the bytes on disk at {path} differ from the "
            "bytes to write. \"Written\" is defined by the read-back result — the two sides "
            "disagree now, which means something else (a concurrent write, antivirus, a "
            "filesystem fault) touched the file; do not act as if it did not happen.")


def verify_receipt_file(receipt: Dict[str, Any], path: str) -> None:
    """Independent read-back check: the disk bytes must equal this receipt's canonical bytes.
    For the auditor's review."""
    _verify_bytes(path, _canonical_bytes(receipt))


def read_receipt(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ReceiptError(f"{path} has a BOM — a BOM breaks byte-for-byte reconciliation; forbidden")
    return json.loads(raw.decode("utf-8"))


# ── Blind-written expectations: the expectation lands before the readout (protocol in the module docstring) ──

# Counter contract: one-to-one with the counters key set produced by receipt_from_*.
# Keys and types are pinned — a "partial expectation" leaves room for comparing selectively,
# and a misspelled key is silently skipped during reconciliation, so missing/extra keys and
# type impersonation are all refused when writing the expectation.
COUNTER_SCHEMA: Dict[str, Tuple[str, ...]] = {
    "pairwise": ("common", "divergence", "dominance", "neither",
                 "out_of_domain", "total"),
    "nway": ("all_true", "all_false", "split", "out_of_domain", "total",
             "outliers", "pioneers", "ratchet_total", "ratchet_trusted", "anchor"),
}
_INT_KEYS = {"common", "divergence", "dominance", "neither", "out_of_domain",
             "total", "all_true", "all_false", "split", "ratchet_total"}
_MAP_KEYS = {"outliers", "pioneers"}          # account name → count (sparse)
_BOOL_KEYS = {"ratchet_trusted"}
_WITNESS_KEYS: Dict[str, Tuple[str, ...]] = {
    "pairwise": ("divergence", "dominance"),
    "nway": ("split", "ratchet"),
}


@dataclass(frozen=True)
class Expectation:
    """Blind-write expectation handle. in_process=True means this process's write_expected
    produced it (there is an in-process call order, so it can enter gate reconciliation); one
    loaded by load_expected has no such proof, so only pure comparison via audit is allowed.
    mtime is recorded as reference information (forgeable, explicitly downgraded)."""
    path: str
    schema_version: int
    run_kind: str
    claims_identity: List[Dict[str, str]]
    domain_digest: Dict[str, Any]
    expected_counters: Dict[str, Any]
    expected_witnesses: Optional[Dict[str, List[str]]]
    written_marker: str
    mtime_epoch: Optional[float]
    in_process: bool


def _validate_counters(run_kind: str, expected_counters: Dict[str, Any]) -> None:
    schema = COUNTER_SCHEMA.get(run_kind)
    if schema is None:
        raise ReceiptError(
            f"run_kind must be {'|'.join(COUNTER_SCHEMA)}, got {run_kind!r}")
    missing = [k for k in schema if k not in expected_counters]
    extra = [k for k in expected_counters if k not in schema]
    if missing or extra:
        raise ReceiptError(
            f"expected_counters must be complete per the {run_kind} contract: missing {missing}, "
            f"extra {extra}. A partial expectation leaves room for \"comparing selectively\", and "
            "a misspelled key is silently skipped during reconciliation")
    for k in schema:
        v = expected_counters[k]
        if k in _INT_KEYS:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ReceiptError(
                    f"counters.{k} must be int, got {v!r}"
                    + (" (a bool posing as int: true==1 in json creates reconciliation ambiguity)"
                       if isinstance(v, bool) else ""))
        elif k in _BOOL_KEYS:
            if not isinstance(v, bool):
                raise ReceiptError(f"counters.{k} must be bool, got {v!r}")
        elif k in _MAP_KEYS:
            if not isinstance(v, dict) or not all(
                    isinstance(kk, str) and isinstance(vv, int)
                    and not isinstance(vv, bool) for kk, vv in v.items()):
                raise ReceiptError(
                    f"counters.{k} must be a dict of account name → int (sparse, zero entries "
                    f"omitted), got {v!r}")
        elif k == "anchor":
            if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
                raise ReceiptError(
                    f"counters.anchor must be None or int, got {v!r}")


def _validate_witnesses(run_kind: str,
                        expected_witnesses: Optional[Dict[str, List[str]]]
                        ) -> Optional[Dict[str, List[str]]]:
    if expected_witnesses is None:
        return None
    allowed = _WITNESS_KEYS[run_kind]
    bad = [k for k in expected_witnesses if k not in allowed]
    if bad:
        raise ReceiptError(
            f"expected_witnesses only allows {allowed}, got unknown keys {bad}")
    return {k: [_s(w) for w in v] for k, v in expected_witnesses.items()}


def _apply_order_key(claims: Sequence[Any],
                     order_key: Optional[Callable[[int, Any], Any]]) -> List[Any]:
    """Exactly the reordering semantics of compare_n (stable sort, ties in input order).
    The expectation and the receipt must use the same order, otherwise the same batch of accounts
    produces false surprises because of enumeration order."""
    if order_key is None:
        return list(claims)
    keyed = [((order_key(i, c), i), c) for i, c in enumerate(claims)]
    keyed.sort(key=lambda pair: pair[0])
    return [c for _, c in keyed]


def _marker_of(content: Dict[str, Any]) -> str:
    """sha256 of the canonical bytes of all fields of the expected file (except written_marker
    itself). The rule is uniform: "remove the marker from the file, then hash" — the witness list
    is in scope too (it is part of the expectation and must be caught when touched), and the
    write side and the read side share this one rule; diverging rules would make a soft witness
    trigger a hard surprise as a false positive."""
    return hashlib.sha256(_canonical_bytes(content)).hexdigest()


_EXPECTED_PAYLOAD_KEYS = ("schema_version", "run_kind", "claims_identity",
                          "domain_digest", "expected_counters")


def write_expected(path: str, *, run_kind: str, claims: Sequence[Any],
                   domain: Sequence[Any], expected_counters: Dict[str, Any],
                   order_key: Optional[Callable[[int, Any], Any]] = None,
                   expected_witnesses: Optional[Dict[str, List[str]]] = None
                   ) -> Expectation:
    """Write the expectation to disk before compare (writing validates by reading back).

    order_key has the same semantics as compare_n (optional); when given, claims_identity records
    the final reordered order. The returned handle holds the written_marker and the in_process
    token, and is handed to reconcile in the same process for gate reconciliation.
    """
    run_kind = _check_run_kind(run_kind)
    _validate_counters(run_kind, expected_counters)
    witnesses = _validate_witnesses(run_kind, expected_witnesses)
    ordered = _apply_order_key(claims, order_key)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_kind": run_kind,
        "claims_identity": claims_identity_of(ordered),
        "domain_digest": domain_digest_of(domain),
        "expected_counters": dict(expected_counters),
    }
    if witnesses is not None:
        payload["expected_witnesses"] = witnesses
    marker = _marker_of(payload)                 # covers the whole expectation content (witnesses included)
    _write_canonical({**payload, "written_marker": marker}, path)
    return Expectation(path=os.path.abspath(path), schema_version=SCHEMA_VERSION,
                       run_kind=run_kind, claims_identity=payload["claims_identity"],
                       domain_digest=payload["domain_digest"],
                       expected_counters=payload["expected_counters"],
                       expected_witnesses=witnesses, written_marker=marker,
                       mtime_epoch=os.path.getmtime(path), in_process=True)


def load_expected(path: str) -> Expectation:
    """Load an expectation from disk (external expectation: no in-process token, audit only).
    A file that contradicts itself (marker does not match content) is refused outright — refuse
    to audit an expectation that is already untrustworthy."""
    data = read_receipt(path)      # reuse the "no BOM + UTF-8" reading discipline
    for k in (*_EXPECTED_PAYLOAD_KEYS, "written_marker"):
        if k not in data:
            raise ReceiptError(f"expected file is missing contract field {k}: {path}")
    payload = {k: v for k, v in data.items() if k != "written_marker"}
    if _marker_of(payload) != data["written_marker"]:
        raise ReceiptError(
            f"expected file contradicts itself: written_marker does not match the content "
            f"({path}). The file was modified after being written — refuse to load; better to fail "
            "loudly than to reconcile against a dirty expectation")
    return Expectation(path=os.path.abspath(path),
                       schema_version=data["schema_version"],
                       run_kind=_check_run_kind(data["run_kind"]),
                       claims_identity=data["claims_identity"],
                       domain_digest=data["domain_digest"],
                       expected_counters=data["expected_counters"],
                       expected_witnesses=data.get("expected_witnesses"),
                       written_marker=data["written_marker"],
                       mtime_epoch=os.path.getmtime(path), in_process=False)


def _diff(expected: Expectation, receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Hard reconciliation difference list: every entry carries the field name and both values
    (bare numbers cannot be reconciled)."""
    diffs: List[Dict[str, Any]] = []
    if expected.run_kind != receipt.get("run_kind"):
        diffs.append({"field": "run_kind", "expected": expected.run_kind,
                      "actual": receipt.get("run_kind")})
    if expected.claims_identity != receipt.get("claims_identity"):
        diffs.append({"field": "claims_identity",
                      "expected": expected.claims_identity,
                      "actual": receipt.get("claims_identity"),
                      "note": "the account changed (function replaced / name changed / order "
                              "changed); the expectation has expired"})
    if expected.domain_digest != receipt.get("domain_digest"):
        diffs.append({"field": "domain_digest",
                      "expected": expected.domain_digest,
                      "actual": receipt.get("domain_digest"),
                      "note": "the comparison domain changed, the expectation has expired"})
    ec, ac = expected.expected_counters, receipt.get("counters") or {}
    for k in sorted(set(ec) | set(ac)):
        ev, av = ec.get(k), ac.get(k)
        if isinstance(ev, dict) or isinstance(av, dict):
            e2, a2 = ev or {}, av or {}
            for kk in sorted(set(e2) | set(a2)):
                if e2.get(kk, 0) != a2.get(kk, 0):
                    diffs.append({"field": f"counters.{k}.{kk}",
                                  "expected": e2.get(kk, 0),
                                  "actual": a2.get(kk, 0)})
        elif ev != av:
            diffs.append({"field": f"counters.{k}",
                          "expected": ev, "actual": av})
    return diffs


def _witness_notes(expected: Expectation,
                   receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Witness soft reconciliation: notes only, never enters the gate (subject to max_witness
    truncation and order)."""
    if not expected.expected_witnesses:
        return []
    notes: List[Dict[str, Any]] = []
    rw = receipt.get("witnesses") or {}
    for k in sorted(set(expected.expected_witnesses) | set(rw)):
        ev = sorted(expected.expected_witnesses.get(k) or [])
        av = sorted(rw.get(k) or [])
        if ev != av:
            notes.append({"kind": k, "expected": ev, "actual": av,
                          "note": "the witness list is subject to max_witness truncation and "
                                  "discovery order; reference only, not counted in the gate"})
    return notes


def reconcile(expected: Expectation, receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Gate reconciliation (in-process protocol). The call order must be write_expected →
    compare → this function; the result block is assigned directly to receipt["expected"], and
    gate_exit_code takes effect.

    Token check: accepts only the handle from this process's write_expected (in_process=True) —
    no json on disk can prove the "write first, then run" call order; this guards against "forgot
    to write first", not against forgery (honest boundary in the module docstring).
    """
    if not expected.in_process:
        raise ReceiptError(
            "reconcile accepts only an expectation produced by this process's write_expected "
            "(token check, guarding against \"forgot to write first\"); an expectation loaded from "
            "disk has no in-process call order to prove, so use audit() for pure comparison")
    hard = _diff(expected, receipt)
    # Re-check the expected file's current state: touched (or gone) after the blind write →
    # no longer the expectation that was blind-written
    try:
        data = read_receipt(expected.path)
        current = _marker_of({k: v for k, v in data.items()
                              if k != "written_marker"})
    except (OSError, ReceiptError, KeyError):
        current = None
    if current != expected.written_marker:
        hard.append({"field": "written_marker",
                     "expected": expected.written_marker, "actual": current,
                     "note": "the expected file was modified (or has disappeared) after the "
                             "blind write; it is no longer the one that was blind-written"})
    return {
        "expected_counters": expected.expected_counters,
        "written_marker": expected.written_marker,
        "expected_file_mtime": expected.mtime_epoch,   # reference value: forgeable, reset by clone
        "call_order": "in-process",
        "surprise": bool(hard),
        "diffs": hard,
        "witness_notes": _witness_notes(expected, receipt),
    }


def audit(expected: Expectation, receipt_path: str) -> Dict[str, Any]:
    """Third-party audit: disk expectation × disk receipt, a pure comparison that produces a
    report; it does not modify files and carries no gate semantics.
    The auditor has no in-process token, so the only criterion is content comparison — including
    reconciling the written_marker recorded in the receipt against the current hash of the
    expected file (a mismatch = the expectation was touched after reconciliation)."""
    receipt = read_receipt(receipt_path)
    hard = _diff(expected, receipt)
    exp_block = receipt.get("expected") or {}
    if exp_block.get("written_marker") not in (None, expected.written_marker):
        hard.append({"field": "written_marker (receipt record vs current expected-file hash)",
                     "expected": exp_block["written_marker"],
                     "actual": expected.written_marker,
                     "note": "the expected file was modified after reconciliation — expectation "
                             "and receipt are no longer same-source"})
    return {
        "expected_counters": expected.expected_counters,
        "written_marker": expected.written_marker,
        "expected_file_mtime": expected.mtime_epoch,
        "call_order": "external-load",
        "surprise": bool(hard),
        "diffs": hard,
        "witness_notes": _witness_notes(expected, receipt),
    }


def gate_exit_code(receipt: Dict[str, Any]) -> int:
    """0=pass / 1=gate failure. The only source of gate failure is a blind-write reconciliation
    surprise; expected null means never reconciled, which counts as neither pass nor fail → 0
    (no gate to violate)."""
    exp = receipt.get("expected")
    if isinstance(exp, dict) and exp.get("surprise"):
        return EXIT_GATE_FAIL
    return EXIT_PASS


def main() -> int:
    if "--self-check" in sys.argv:
        import receipt_test
        return receipt_test.main()
    print(__doc__)
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())

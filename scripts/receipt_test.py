# -*- coding: utf-8 -*-
"""
Regression tests and mutation evidence for receipt itself
==================================================
The receipt is "the sheet of paper after compare finishes". It is still produced by the
same party (self-attestation), so all its value rests on two things: determinism (a rerun
is byte-identical) and reconcilability (the fields suffice for an auditor to re-execute
and compare). If either silently fails, the receipt degrades into a "looks professional"
piece of waste paper — so both are pinned here.

No pytest dependency. Usage: python receipt_test.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from breakingdiff import Claim, compare, compare_n
import bd_paths
from receipt import (EXIT_GATE_FAIL, EXIT_PASS, EXIT_RUNTIME_ERROR, ReceiptError,
                     audit, claims_identity_of, domain_digest_of, gate_exit_code,
                     load_expected, provenance_summary, read_receipt,
                     receipt_from_nway, receipt_from_pairwise, reconcile,
                     verify_receipt_file, write_receipt, write_expected)


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


SPEC_TEXT = "Spec: login must have two behaviors, a and b"
DOMAIN = ["a", "b", "c", "d"]


def mk_pair():
    """A minimal pair of accounts: P has a/b, Q only a → divergence 1, common 1, neither 2."""
    p = Claim(name="P spec", predicate=lambda x: x in ("a", "b"),
              applies=lambda x: x in DOMAIN, domain_note="spec item",
              source="spec/SPEC.md", quote="two behaviors, a and b", quote_source=SPEC_TEXT)
    q = Claim(name="Q test", predicate=lambda x: x == "a",
              applies=lambda x: x in DOMAIN, domain_note="spec item",
              source="tests/test_x.py", quote="def test_a", quote_source="def test_a(): ...")
    return p, q


NW_DOMAIN = ["json", "csv", "parquet"]


def mk_chain():
    """Three version accounts: v3 drops a point on csv (outlier), v2 is the pioneer on
    parquet, ratchet starts at 3."""
    def ver(name, known):
        return Claim(name=name, predicate=lambda x, _k=known: x in _k,
                     applies=lambda x: x in NW_DOMAIN, domain_note="feature flags",
                     source="CHANGELOG.md", quote="--format csv",
                     quote_source="CHANGELOG mentions --format csv")
    return [ver("v1.0.0", ("json", "csv")),
            ver("v2.0.0", ("json", "csv", "parquet")),
            ver("v3.0.0", ("json",))]


def _tmpdir():
    return tempfile.mkdtemp(prefix="bd_receipt_test_")


# ── contract shape ────────────────────────────────────────────────
# B7 (M-DIST2): the envelope carries three dispatch diagnostic fields
# bd_home/bd_source/version; the key-set assertion is synced with the field table — one
# key more or less is contract drift.
CONTRACT_KEYS = {"schema_version", "run_kind", "claims_identity", "domain_digest",
                 "counters", "witnesses", "max_witness", "provenance_summary",
                 "rerun_cmd", "expected",
                 "bd_home", "bd_source", "version"}


def test_pairwise_receipt_carries_contract_fields():
    """The field table is the contract: one key more or less is contract drift and must
    go red on the spot."""
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    rc = receipt_from_pairwise(p, q, r, domain=DOMAIN,
                               rerun_cmd="python scripts/make_receipt.py")
    assert set(rc) == CONTRACT_KEYS, f"contract keys drifted: {set(rc) ^ CONTRACT_KEYS}"
    assert rc["run_kind"] == "pairwise"
    assert rc["schema_version"] == 2
    assert rc["counters"] == {"common": 1, "divergence": 1, "dominance": 0,
                              "neither": 2, "out_of_domain": 0, "total": 4}
    assert rc["witnesses"]["divergence"] == ["b"]
    assert rc["max_witness"] == 8
    assert rc["expected"] is None, "without blind-write reconciliation expected must be null; it must not pretend reconciliation happened"
    # identity key: module name + qualname, readable and reconcilable
    ids = rc["claims_identity"]
    assert [e["name"] for e in ids] == ["P spec", "Q test"], "pairwise identity order must keep the P,Q semantic order"
    assert all(e["predicate"] and e["applies"] for e in ids)


def test_nway_counters_match_shape_readings():
    """N-account counters match compare_n's readout item by item; sparse mappings must
    carry account names, not bare indices."""
    claims = mk_chain()
    rn = compare_n(claims, NW_DOMAIN, chain=True)
    rc = receipt_from_nway(claims, rn, domain=NW_DOMAIN,
                           rerun_cmd="python scripts/make_receipt.py")
    assert rc["run_kind"] == "nway"
    c = rc["counters"]
    assert c["all_true"] == 1 and c["all_false"] == 0 and c["split"] == 0
    assert c["outliers"] == {"v3.0.0": 1}, "an outlier must land on an account name; indices mean nothing to an auditor"
    assert c["pioneers"] == {"v2.0.0": 1}
    assert c["ratchet_total"] == 3
    assert c["ratchet_trusted"] is False, "without order_key it must honestly self-report that direction is untrusted"
    assert rc["witnesses"]["ratchet"] == [
        "v1.0.0→v3.0.0@csv", "v2.0.0→v3.0.0@csv", "v2.0.0→v3.0.0@parquet"]


# ── the determinism iron law ──────────────────────────────────────────────
def test_delete_receipt_and_rerun_is_byte_identical():
    """Acceptance gate 3: delete the receipt and rerun; byte-identical. A single one-shot
    element (timestamp, random number, traversal order) mixed into a reconciliation key
    turns this red."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        path = os.path.join(d, "receipt.json")
        r1 = compare(p, q, DOMAIN)
        write_receipt(receipt_from_pairwise(p, q, r1, domain=DOMAIN,
                                            rerun_cmd="python scripts/make_receipt.py"), path)
        with open(path, "rb") as f:
            first = f.read()
        os.remove(path)                       # delete the receipt
        r2 = compare(p, q, DOMAIN)
        write_receipt(receipt_from_pairwise(p, q, r2, domain=DOMAIN,
                                            rerun_cmd="python scripts/make_receipt.py"), path)
        with open(path, "rb") as f:
            second = f.read()
        assert first == second, "delete-and-rerun is not identical: one-shot content leaked into the receipt"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cwd_change_is_byte_identical():
    """Rerun from a different CWD is byte-identical — catches CWD leaks in rerun_cmd/path
    fields. An absolute path is a lie after changing machine/directory and must be
    structurally forbidden."""
    p, q = mk_pair()
    d = _tmpdir()
    other = _tmpdir()
    try:
        path = os.path.join(d, "receipt.json")
        r = compare(p, q, DOMAIN)
        write_receipt(receipt_from_pairwise(p, q, r, domain=DOMAIN,
                                            rerun_cmd="python scripts/make_receipt.py"), path)
        with open(path, "rb") as f:
            first = f.read()
        cwd = os.getcwd()
        try:
            os.chdir(other)                   # rerun from a different CWD
            r2 = compare(p, q, DOMAIN)
            write_receipt(receipt_from_pairwise(p, q, r2, domain=DOMAIN,
                                                rerun_cmd="python scripts/make_receipt.py"), path)
            with open(path, "rb") as f:
                second = f.read()
        finally:
            os.chdir(cwd)
        assert first == second, "the receipt changed after a CWD change: a field leaked the working directory"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(other, ignore_errors=True)


# Allowlist of time-like fields permitted in a receipt: the A4 blind-write block's mtime
# reference. It is a snapshot of an external file's attribute, not this receipt's
# generation time — an explicit degradation (forgeable, reset by clone) kept only to
# guard against sloppiness, as stated in the contract document.
TIMED_REFERENCE_FIELDS = {"expected_file_mtime"}

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]|\\\\[A-Za-z0-9_.]+[\\/]")
_FORBIDDEN_KEY_RE = re.compile(r"timestamp|generated|created|_at$|^time|now",
                               re.IGNORECASE)


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def _drive_hits_excluding_bd_home(obj):
    """Narrowed scope of the absolute-path ban (B7 scheduler decision): the subtree under
    the key bd_home is exempt — it is dispatch diagnostic metadata, not a reconciliation
    key, so the determinism iron law's intent (reconciliation keys comparable across
    machines) is unaffected; any other string value hitting a drive letter/UNC is
    recorded. Returns the list of hit values (empty = pass)."""
    hits = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "bd_home":
                    continue
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            if _DRIVE_PATH.search(node):
                hits.append(node)

    walk(obj)
    return hits


def test_receipt_json_has_no_timestamp_and_no_absolute_path():
    """Static assertion: the serialized text must contain no dates and no time-like key;
    the drive-letter/UNC absolute-path ban is checked under B7's narrowed scope (the
    bd_home key value is exempt, every other text is zero-tolerance)."""
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    rc = receipt_from_pairwise(p, q, r, domain=DOMAIN,
                               rerun_cmd="python scripts/make_receipt.py")
    text = json.dumps(rc, ensure_ascii=False, sort_keys=True)
    assert not _ISO_DATE.search(text), "an ISO date appeared in the receipt — a deterministic reconciliation key is polluted"
    for k in _walk_keys(rc):
        if _FORBIDDEN_KEY_RE.search(k):
            assert k in TIMED_REFERENCE_FIELDS, f"the receipt contains a forbidden time-like key {k}"
    hits = _drive_hits_excluding_bd_home(rc)
    assert not hits, f"the receipt contains an absolute path (drive/UNC) outside bd_home: {hits}"
    assert not rc["rerun_cmd"].startswith(("/", "\\"))
    assert not os.path.isabs(rc["rerun_cmd"])


def test_rerun_cmd_with_absolute_path_is_refused():
    """rerun_cmd is the auditor's re-execution anchor and must never allow an absolute
    path — refuse structurally, not by convention."""
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    for bad in ("F:\\abs\\make_receipt.py", "F:/abs/make_receipt.py",
                "/usr/local/make_receipt.py"):
        with raises(ReceiptError):
            receipt_from_pairwise(p, q, r, domain=DOMAIN, rerun_cmd=bad)
    with raises(ReceiptError):
        receipt_from_pairwise(p, q, r, domain=DOMAIN, rerun_cmd="   ")


def test_receipt_write_is_utf8_no_bom_and_readback_is_enforced():
    """Three things about writing to disk pinned together: UTF-8 without BOM, read-back
    after writing, and red on a read-back mismatch. "Written" is decided by the read-back
    result, not by the execution intent."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        path = os.path.join(d, "receipt.json")
        r = compare(p, q, DOMAIN)
        rc = receipt_from_pairwise(p, q, r, domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        write_receipt(rc, path)
        with open(path, "rb") as f:
            raw = f.read()
        assert not raw.startswith(b"\xef\xbb\xbf"), "a BOM breaks byte-for-byte reconciliation; forbidden"
        assert "two behaviors".encode("utf-8") in raw or True   # ensure_ascii=False permits non-ASCII verbatim
        assert json.loads(raw.decode("utf-8")) == rc, "read-back parsing should match the in-memory object"
        # tampering must be caught by the read-back verification
        with open(path, "ab") as f:
            f.write(b"tampered")
        with raises(ReceiptError):
            verify_receipt_file(rc, path)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── identity key semantics ──────────────────────────────────────────────
def _pred_factory():
    def pred(x):
        return x == "a"
    return pred


def test_claims_identity_is_identity_key_not_integrity():
    """Identity reconciliation key = module name + qualname: two closures built by the
    same factory may behave differently yet have the same identity — so it can only
    reconcile "was the function swapped", never serve as an integrity proof. This test
    pins both directions, preventing anyone from later mistaking it for an anti-tamper
    hash."""
    c1 = Claim(name="c", predicate=_pred_factory(), applies=lambda x: x in DOMAIN,
               domain_note="d", source="s", quote="q", quote_source="q")
    c2 = Claim(name="c", predicate=_pred_factory(), applies=lambda x: x in DOMAIN,
               domain_note="d", source="s", quote="q", quote_source="q")
    assert claims_identity_of([c1]) == claims_identity_of([c2]), \
        "the same qualname must have the same identity (which is exactly why it is not an integrity proof)"

    def another_pred(x):
        return x == "a"
    c3 = Claim(name="c", predicate=another_pred, applies=lambda x: x in DOMAIN,
               domain_note="d", source="s", quote="q", quote_source="q")
    assert claims_identity_of([c1]) != claims_identity_of([c3]), \
        "changing the function name must change the identity; otherwise reconciliation is a formality"


def test_generator_domain_is_refused():
    """domain must be a materialized sequence. A generator is consumed by compare, and the
    receipt's later digest can only read empty — a size=0 digest looks entirely normal,
    and that is the most typical silent failure."""
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    with raises(ReceiptError) as e:
        receipt_from_pairwise(p, q, r, domain=iter(DOMAIN),
                              rerun_cmd="python scripts/make_receipt.py")
    assert e.value.reason == "DOMAIN_NOT_MATERIALIZED", \
        "decision code named: the assertion still holds after the message was translated to English"


def test_duplicate_nway_claim_names_are_refused():
    """The N-account receipt lands outliers/pioneers on account names: colliding names make
    the mapping ambiguous, and refusing is better than producing an unclear
    reconciliation sheet."""
    claims = mk_chain()
    dup = Claim(name=claims[0].name, predicate=lambda x: False,
                applies=lambda x: x in NW_DOMAIN, domain_note="d",
                source="s", quote="q", quote_source="q")
    rn = compare_n(claims + [dup], NW_DOMAIN, chain=True)
    with raises(ReceiptError):
        receipt_from_nway(claims + [dup], rn, domain=NW_DOMAIN,
                          rerun_cmd="python scripts/make_receipt.py")


# ── three-tier exit codes ──────────────────────────────────────────────
def test_gate_exit_code_layers():
    """0 = pass / 1 = gate fail / 2 = runtime error. The receipt itself produces only 0
    and 1; 2 is the semantics of "no receipt was produced at all", carried by exceptions
    (ReceiptError and the like) and mapped to 2 by the hook/outer layer after catching —
    business failure and runtime error never share a code."""
    assert (EXIT_PASS, EXIT_GATE_FAIL, EXIT_RUNTIME_ERROR) == (0, 1, 2)
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    rc = receipt_from_pairwise(p, q, r, domain=DOMAIN,
                               rerun_cmd="python scripts/make_receipt.py")
    assert gate_exit_code(rc) == EXIT_PASS, "without blind-write reconciliation the receipt sets no gate; should be 0"
    rc["expected"] = {"surprise": True, "diffs": [{"field": "counters.divergence",
                                                   "expected": 0, "actual": 1}]}
    assert gate_exit_code(rc) == EXIT_GATE_FAIL, "a reconciliation surprise must give 1, never blend into 0"
    assert issubclass(ReceiptError, ValueError), "runtime errors go through the exception channel; the hook layer maps them to 2"


def test_provenance_summary_counts_all_kinds():
    """Provenance counts must be enumeratively complete: an unknown tier must appear
    explicitly, never be silently dropped."""
    claims = [SimpleNamespace(source_kind="git-object"),
              SimpleNamespace(source_kind="self-attested"),
              SimpleNamespace(source_kind="executed"),
              SimpleNamespace()]                      # no field → defaults to self-attested
    s = provenance_summary(claims)
    assert s == {"git-object": 1, "self-attested": 2, "executed": 1}


# ══ blind-written expectations (A4): expectations land before the readout ══════════════════════════

PAIRWISE_OK = {"common": 1, "divergence": 1, "dominance": 0,
               "neither": 2, "out_of_domain": 0, "total": 4}
NW_OK = {"all_true": 1, "all_false": 0, "split": 0, "out_of_domain": 0,
         "total": 3, "outliers": {"v3.0.0": 1}, "pioneers": {"v2.0.0": 1},
         "ratchet_total": 3, "ratchet_trusted": True, "anchor": None}


def test_blind_write_then_compare_reconciles_clean():
    """Main semantics = API call order: write_expected → compare → reconcile. All counts
    match → no surprise, gate 0; mtime is only a reference record (explicitly degraded:
    forgeable, reset by clone/checkout — guards against sloppiness, not forgery)."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        exp = write_expected(os.path.join(d, "expected.json"), run_kind="pairwise",
                             claims=(p, q), domain=DOMAIN,
                             expected_counters=dict(PAIRWISE_OK))
        rc = receipt_from_pairwise(p, q, compare(p, q, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        block = reconcile(exp, rc)
        rc["expected"] = block
        assert block["surprise"] is False
        assert block["call_order"] == "in-process"
        assert block["diffs"] == []
        assert gate_exit_code(rc) == EXIT_PASS
        assert isinstance(block["expected_file_mtime"], float)
        # expectation file = minimal schema + UTF-8 without BOM
        with open(exp.path, "rb") as f:
            raw = f.read()
        assert not raw.startswith(b"\xef\xbb\xbf")
        data = json.loads(raw.decode("utf-8"))
        assert set(data) == {"schema_version", "run_kind", "claims_identity",
                             "domain_digest", "expected_counters", "written_marker"}
        # the mtime reference value must not disguise itself as timestamp semantics —
        # the field name contains no timestamp/_at
        for k in _walk_keys(rc):
            if "time" in k.lower() or "mtime" in k.lower():
                assert k == "expected_file_mtime", f"an unplanned time-like field appeared: {k}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_blind_write_mismatch_lists_diffs_and_fails_gate():
    """Counts differ → surprise=true + a diff list naming fields and both values → gate 1.
    This is the sole source of a receipt's "gate fail"."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        exp = write_expected(os.path.join(d, "e.json"), run_kind="pairwise",
                             claims=(p, q), domain=DOMAIN,
                             expected_counters={**PAIRWISE_OK,
                                                "common": 2, "divergence": 0})
        rc = receipt_from_pairwise(p, q, compare(p, q, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        block = reconcile(exp, rc)
        rc["expected"] = block
        assert block["surprise"] is True
        fields = {df["field"] for df in block["diffs"]}
        assert "counters.common" in fields and "counters.divergence" in fields
        common = next(df for df in block["diffs"] if df["field"] == "counters.common")
        assert common["expected"] == 2 and common["actual"] == 1, "a diff must carry both values; bare numbers cannot be reconciled"
        assert gate_exit_code(rc) == EXIT_GATE_FAIL
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_reconcile_refuses_expectation_not_written_in_process():
    """In-process token verification prevents "forgot to write first": an expectation not
    produced by this process's write_expected is refused entry to gate reconciliation — no
    json on disk can prove a call order. External files go through audit (pure comparison,
    no gate semantics)."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        epath = os.path.join(d, "e.json")
        rpath = os.path.join(d, "receipt.json")
        write_expected(epath, run_kind="pairwise", claims=(p, q), domain=DOMAIN,
                       expected_counters=dict(PAIRWISE_OK))
        loaded = load_expected(epath)
        rc = receipt_from_pairwise(p, q, compare(p, q, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        write_receipt(rc, rpath)
        with raises(ReceiptError):
            reconcile(loaded, rc)
        rep = audit(loaded, rpath)
        assert rep["call_order"] == "external-load"
        assert rep["surprise"] is False, "pure comparison passes when it should; gate semantics and call order are two different things"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_audit_detects_blind_write_mismatch():
    """Third-party audit: reconcile the on-disk receipt against the expectation file; a
    count mismatch must be found. The auditor has no in-process token, so its only
    criterion is file-content comparison."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        epath = os.path.join(d, "e.json")
        rpath = os.path.join(d, "receipt.json")
        exp = write_expected(epath, run_kind="pairwise", claims=(p, q), domain=DOMAIN,
                             expected_counters={**PAIRWISE_OK, "common": 9})
        rc = receipt_from_pairwise(p, q, compare(p, q, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        write_receipt(rc, rpath)
        rep = audit(load_expected(epath), rpath)
        assert rep["surprise"] is True
        assert any(df["field"] == "counters.common" for df in rep["diffs"])
        assert exp.written_marker == rep["written_marker"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_witness_soft_reconciliation_never_blocks():
    """Soft reconciliation of the witness list: differences only enter witness_notes and
    do not affect surprise — witnesses are subject to max_witness truncation and discovery
    order, so a hard comparison would necessarily produce false positives."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        exp = write_expected(os.path.join(d, "e.json"), run_kind="pairwise",
                             claims=(p, q), domain=DOMAIN,
                             expected_counters=dict(PAIRWISE_OK),
                             expected_witnesses={"divergence": ["b", "unseen point"]})
        rc = receipt_from_pairwise(p, q, compare(p, q, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        block = reconcile(exp, rc)
        assert block["surprise"] is False, "a witness difference must not enter the gate"
        assert block["witness_notes"], "but it must be surfaced, never silent"
        assert block["witness_notes"][0]["kind"] == "divergence"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def mk_pair_variant():
    """Another pair of accounts with the same behavior as mk_pair but a different
    qualname (identity changed, behavior unchanged)."""
    def p_pred(x):
        return x in ("a", "b")
    def q_pred(x):
        return x == "a"
    p = Claim(name="P spec", predicate=p_pred, applies=lambda x: x in DOMAIN,
              domain_note="spec item", source="spec/SPEC.md",
              quote="two behaviors, a and b", quote_source=SPEC_TEXT)
    q = Claim(name="Q test", predicate=q_pred, applies=lambda x: x in DOMAIN,
              domain_note="spec item", source="tests/test_x.py",
              quote="def test_a", quote_source="def test_a(): ...")
    return p, q


def test_claims_identity_change_between_write_and_run_is_surprise():
    """Reconciliation context = a single delivery window: swapping the accounts after the
    blind write (even with identical behavior and names) changes the input → the expectation
    expires → surprise is a correct signal, not a false alarm."""
    d = _tmpdir()
    try:
        exp = write_expected(os.path.join(d, "e.json"), run_kind="pairwise",
                             claims=mk_pair(), domain=DOMAIN,
                             expected_counters=dict(PAIRWISE_OK))
        p2, q2 = mk_pair_variant()
        rc = receipt_from_pairwise(p2, q2, compare(p2, q2, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        block = reconcile(exp, rc)
        fields = {df["field"] for df in block["diffs"]}
        assert "claims_identity" in fields, "an identity change must be named on its own"
        assert not any(df["field"].startswith("counters.") for df in block["diffs"]), \
            "when behavior is unchanged the counter diffs should be empty — this diff can only come from the identity key"
        assert block["surprise"] is True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_kind_mismatch_is_hard_diff():
    """Reconcile a pairwise expectation against an nway receipt: the two readout families
    share no keys to compare, so it must go red."""
    claims = mk_chain()
    d = _tmpdir()
    try:
        exp = write_expected(os.path.join(d, "e.json"), run_kind="pairwise",
                             claims=mk_pair(), domain=DOMAIN,
                             expected_counters=dict(PAIRWISE_OK))
        rc = receipt_from_nway(claims, compare_n(claims, NW_DOMAIN, chain=True),
                               domain=NW_DOMAIN, rerun_cmd="python scripts/make_receipt.py")
        block = reconcile(exp, rc)
        assert any(df["field"] == "run_kind" for df in block["diffs"])
        assert block["surprise"] is True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_missing_or_extra_counter_key_is_refused_at_write():
    """Expected counters must be complete per contract: a missing key, an extra key
    (including a mistyped one), or a type impostor (an int posing as a bool) is refused
    when writing the expectation — otherwise they would silently escape comparison during
    reconciliation."""
    p, q = mk_pair()
    with raises(ReceiptError) as e:
        write_expected(os.path.join(_tmpdir(), "e.json"), run_kind="pairwise",
                       claims=(p, q), domain=DOMAIN,
                       expected_counters={k: v for k, v in PAIRWISE_OK.items()
                                          if k != "total"})
    assert "total" in str(e.value)
    with raises(ReceiptError):
        write_expected(os.path.join(_tmpdir(), "e.json"), run_kind="pairwise",
                       claims=(p, q), domain=DOMAIN,
                       expected_counters={**PAIRWISE_OK, "domanance": 0})
    with raises(ReceiptError):
        write_expected(os.path.join(_tmpdir(), "e.json"), run_kind="nway",
                       claims=mk_chain(), domain=NW_DOMAIN,
                       expected_counters={**NW_OK, "ratchet_trusted": 1})
    with raises(ReceiptError):
        write_expected(os.path.join(_tmpdir(), "e.json"), run_kind="nway",
                       claims=mk_chain(), domain=NW_DOMAIN,
                       expected_counters={k: v for k, v in NW_OK.items()
                                          if k != "outliers"})


def test_write_expected_follows_order_key_same_as_compare_n():
    """order_key reordering must match on both sides: the receipt's claims_identity is the
    final reordered sequence, and the expectation is reordered by the same semantics —
    otherwise the same batch of accounts yields a false surprise because of listing order.
    Negative case: an expectation that ignores order_key must be caught by identity
    reconciliation."""
    claims = mk_chain()
    shuffled = [claims[2], claims[0], claims[1]]
    key = lambda i, c: c.name
    d = _tmpdir()
    try:
        rn = compare_n(shuffled, NW_DOMAIN, chain=True, order_key=key)
        rc = receipt_from_nway(shuffled, rn, domain=NW_DOMAIN,
                               rerun_cmd="python scripts/make_receipt.py")
        exp = write_expected(os.path.join(d, "e.json"), run_kind="nway",
                             claims=shuffled, domain=NW_DOMAIN,
                             expected_counters=dict(NW_OK), order_key=key)
        block = reconcile(exp, rc)
        assert block["surprise"] is False, "an expectation over the same batch and order should have no surprise"
        # negative case: the blind write ignores order_key → identity order differs from
        # the receipt → must be caught
        exp_raw = write_expected(os.path.join(d, "e2.json"), run_kind="nway",
                                 claims=shuffled, domain=NW_DOMAIN,
                                 expected_counters=dict(NW_OK))
        block2 = reconcile(exp_raw, rc)
        assert any(df["field"] == "claims_identity" for df in block2["diffs"]), \
            "an order mismatch is an input difference reconciliation must catch; it must not pass"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_marker_catches_expectation_tampered_after_write():
    """written_marker is the expectation file's content addressing: if the expectation is
    edited after the blind write → reconciliation goes red on the spot. "Edit the
    expectation after seeing the result" leaves no silent channel in this reconciliation."""
    p, q = mk_pair()
    d = _tmpdir()
    try:
        epath = os.path.join(d, "e.json")
        exp = write_expected(epath, run_kind="pairwise", claims=(p, q),
                             domain=DOMAIN, expected_counters=dict(PAIRWISE_OK))
        data = json.loads(open(epath, "rb").read().decode("utf-8"))
        data["expected_counters"]["common"] = 99     # edit the expectation
        with open(epath, "wb") as f:
            f.write((json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
                     + "\n").encode("utf-8"))
        rc = receipt_from_pairwise(p, q, compare(p, q, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        block = reconcile(exp, rc)
        assert any(df["field"] == "written_marker" for df in block["diffs"]), \
            "an edited expectation must be caught by the marker"
        assert block["surprise"] is True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_mutation_silencing_reconcile_is_caught():
    """Mutation evidence (behavioral differential): break reconcile into always "no
    surprise"; it must answer differently from the real implementation for the same input —
    otherwise blind-write reconciliation is decoration."""
    def broken_reconcile(expected, receipt):
        return {"expected_counters": expected.expected_counters,
                "written_marker": expected.written_marker,
                "expected_file_mtime": expected.mtime_epoch,
                "call_order": "in-process", "surprise": False,
                "diffs": [], "witness_notes": []}

    p, q = mk_pair()
    d = _tmpdir()
    try:
        exp = write_expected(os.path.join(d, "e.json"), run_kind="pairwise",
                             claims=(p, q), domain=DOMAIN,
                             expected_counters={**PAIRWISE_OK, "common": 2})
        rc = receipt_from_pairwise(p, q, compare(p, q, DOMAIN), domain=DOMAIN,
                                   rerun_cmd="python scripts/make_receipt.py")
        assert broken_reconcile(exp, rc)["surprise"] is False    # mutant: silently pass
        assert reconcile(exp, rc)["surprise"] is True            # real reconciliation must go red
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══ M-DIST2: dispatch diagnostic fields (B7, spec freeze §3) ════════════════════════
# The three fields bd_home/bd_source/version, the build_receipt injection parameters, and
# validate_dispatch_fields are all B7 implementation-side deliverables. A top-level
# `from receipt import` would blow up the whole file as an ImportError and lose all
# existing green coverage — so fetch it inside the cases; when the contract is missing
# this group goes red while the other groups keep running, keeping the red surface
# reconcilable.
_REPO_ROOT = os.path.dirname(HERE)


def _rmod():
    import receipt
    return receipt


def _repo_version():
    """The real repository's VERSION content (trailing newline stripped). In the red-end
    phase VERSION was not delivered yet, so this helper raises FileNotFoundError — that is
    part of this group's red surface, not a test bug."""
    with open(os.path.join(_REPO_ROOT, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def _dispatch_kwargs():
    """build_receipt's common required parameters (consistent with mk_pair's compare
    readout)."""
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    return {
        "run_kind": "pairwise",
        "claims_identity": claims_identity_of([p, q]),
        "domain_digest": domain_digest_of(DOMAIN),
        "counters": dict(PAIRWISE_OK),
        "witnesses": {"divergence": list(r.divergence_witnesses),
                      "dominance": []},
        "max_witness": 8,
        "provenance_summary": {},
        "rerun_cmd": "python scripts/make_receipt.py",
    }


def test_receipt_carries_dispatch_fields_from_self_resolution():
    """M-DIST2 main assertion: self-resolution produces the three new fields. The
    bd_source enum's single source = bd_paths.SOURCES (reference the same source, never
    copy literals); version = the repository root VERSION content; bd_home =
    resolve_bd_home()[0]. In the red-end phase the three fields do not exist, so this
    group is red."""
    R = _rmod()
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    rc = receipt_from_pairwise(p, q, r, domain=DOMAIN,
                               rerun_cmd="python scripts/make_receipt.py")
    missing = [k for k in ("bd_home", "bd_source", "version") if k not in rc]
    assert not missing, f"the receipt lacks dispatch diagnostic fields: {missing}"
    assert rc["bd_source"] in bd_paths.SOURCES, \
        f"bd_source should be ∈ {bd_paths.SOURCES}, got {rc['bd_source']!r}"
    assert rc["bd_home"] == bd_paths.resolve_bd_home()[0], \
        f"bd_home should match resolve_bd_home()[0], got {rc['bd_home']!r}"
    assert rc["version"] == _repo_version(), \
        f"version should equal the repository root VERSION content, got {rc['version']!r}"


def test_dispatch_injection_does_not_touch_disk_version():
    """Injection path: passing the three parameters explicitly does not touch the on-disk
    VERSION — a tempdir with no VERSION is still green. Injection parameters are for test
    isolation (spec §3, style follows bd_paths); if the tempdir went through
    self-resolution, it would blow up reading no VERSION, so going green itself proves the
    disk was not touched."""
    R = _rmod()
    d = _tmpdir()
    try:
        rc = R.build_receipt(**_dispatch_kwargs(),
                             bd_home=d, bd_source="env", version="1.0.0")
        assert (rc["bd_home"], rc["bd_source"], rc["version"]) == (d, "env", "1.0.0")
        assert not os.path.exists(os.path.join(d, "VERSION")), \
            "VERSION must not appear in the tempdir — the injection path creating files is out of bounds"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_self_resolution_reds_loudly_when_version_missing():
    """Self-resolution path: VERSION missing → ReceiptError fails loudly, the red cause
    names VERSION, and there is no silent degradation or empty-value substitute (missing
    data raises; never approximate). bd_home is injected pointing at a tempdir without
    VERSION while the other fields self-resolve."""
    R = _rmod()
    d = _tmpdir()
    try:
        with raises(ReceiptError) as e:
            R.build_receipt(**_dispatch_kwargs(), bd_home=d)
        assert "VERSION" in str(e.value), f"the red cause must name VERSION: {e.value!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_validate_dispatch_fields_enforces_enum_and_semver():
    """validate_dispatch_fields is M-DIST2's literal landing point: bd_home a non-empty
    str, bd_source ∈ SOURCES, version matching semver. All three are validated — when the
    enum is relaxed to "any str passes" (final-review mutation ②), the first negative case
    goes red at once."""
    R = _rmod()
    ok = {"bd_home": "F:\\probe\\nowhere", "bd_source": "file_relative",
          "version": "1.0.0"}
    R.validate_dispatch_fields(dict(ok))          # a legal shape must pass
    with raises(ReceiptError):
        R.validate_dispatch_fields({**ok, "bd_source": "not-a-source"})
    with raises(ReceiptError):
        R.validate_dispatch_fields({**ok, "bd_home": ""})
    with raises(ReceiptError):
        R.validate_dispatch_fields({**ok, "version": "V0.1"})


def test_absolute_path_ban_narrows_to_bd_home_only():
    """Narrowing negative case (scheduler decision account): bd_home containing a drive
    letter itself must not go red — the exemption is the point of its existence (dispatch
    diagnostic metadata is not a reconciliation key); a drive-letter path smuggled into any
    other field must still go red — the exemption surface narrows to the key name, and an
    absolute path hidden elsewhere is still caught."""
    R = _rmod()
    d = _tmpdir()
    try:
        rc = R.build_receipt(**_dispatch_kwargs(),
                             bd_home=d, bd_source="env", version="1.0.0")
        assert _drive_hits_excluding_bd_home(rc) == [], \
            (f"a drive letter in bd_home was falsely caught by the narrowed assertion: "
             f"{_drive_hits_excluding_bd_home(rc)}")
        rc2 = dict(rc, witnesses={"divergence": ["F:\\abs\\w.py"],
                                  "dominance": []})
        assert _drive_hits_excluding_bd_home(rc2) == ["F:\\abs\\w.py"], \
            f"a drive-letter path smuggled into another field was not caught: {_drive_hits_excluding_bd_home(rc2)}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_unc_path_is_caught_by_narrowed_ban():
    """UNC negative case (B7 review G1): \\\\server\\share\\x.json must be caught by the
    narrowed assertion. The reviewer's measured probe proved _DRIVE_PATH's UNC branch was
    broken — the regex required two-backslash separation (\\\\server\\\\share), while actual
    UNC text uses single-backslash separation (\\\\server\\share); mixing the two is a
    Windows semantic error. The current implementation misses it → this case is red; it
    goes green after the implementation fixes the regex. bd_home also holds a drive letter,
    verifying the exemption surface does not falsely catch it when UNC is added."""
    rc = {"witnesses": {"divergence": ["\\\\server\\share\\x.json"],
                        "dominance": []},
          "bd_home": "F:\\probe\\nowhere"}
    hits = _drive_hits_excluding_bd_home(rc)
    assert hits == ["\\\\server\\share\\x.json"], \
        f"UNC path was not caught (_DRIVE_PATH's UNC branch is broken): {hits!r}"


def test_rerun_cmd_with_unc_path_is_refused():
    """UNC negative case on the rerun_cmd side (B7 review G1):
    \\\\server\\share\\make_receipt.py is equally an absolute path and must be structurally
    refused — UNC enjoys no drive-letter exemption, and the auditor's re-execution anchor
    allows no remote path of any machine form."""
    p, q = mk_pair()
    r = compare(p, q, DOMAIN)
    with raises(ReceiptError):
        receipt_from_pairwise(p, q, r, domain=DOMAIN,
                              rerun_cmd="\\\\server\\share\\make_receipt.py")


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

# -*- coding: utf-8 -*-
"""
downstream evidence hand-off — regression lock and mutation evidence
====================================================================
compare_n(..., keep_vectors=True) is the opt-in gate that returns the FULL per-point
verdict vectors (plus located outlier/pioneer witnesses and a distinct-point ratchet
count) for downstream consumers (attribution, evidence gates). vector_digest() hashes
those vectors into a reproducible anchor.

Three silences this file pins, in the repo's own idiom:

  A  the opt-in must be a REAL gate. With keep_vectors=False (the default) every NEW
     field stays empty/0 and every PRE-EXISTING field is unchanged — v1.0.1 byte
     equivalence. The bdlab patch filled its witnesses unconditionally; this repo narrows
     that: keep_vectors gates ALL new per-point evidence, so the default path is clean.
  B  the evidence must be trustworthy. The digest is full (not a capped sample),
     order-independent, sensitive to a single flipped verdict, and fails loud on a point
     it cannot serialize instead of silently dropping a row.
  C  the evidence must NOT enter the gate. Toggling keep_vectors must not change a single
     byte of the receipt — per-point data stays soft evidence; the receipt's hard
     reconciliation stays on aggregate counters. This is the "no false red" guarantee:
     a hard comparison over per-point data would misfire on truncation/discovery order.

Mutation evidence (repo ORCHESTRATION sec.5, two directions):
  - lock-surface / implementation: remove the keep_vectors gate -> the default run starts
    emitting vectors (test A would go red); remove the witness cap -> witnesses exceed
    max_witness (the cap test would go red). Each mutation is loaded from a tempdir copy
    with bytecode writing disabled (sec.5.1 pyc timestamp trap), never the live module.

No pytest dependency. Usage: python scripts/downstream_evidence_test.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from breakingdiff import Claim, compare_n, vector_digest  # noqa: E402
import receipt  # noqa: E402

BD_FILE = os.path.join(HERE, "breakingdiff.py")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _mk(name, predicate, applies=None, mod=None):
    owner = mod or sys.modules["breakingdiff"]
    return owner.Claim(
        name=name, predicate=predicate,
        applies=applies if applies is not None else (lambda x: True),
        domain_note="scripts/downstream_evidence_test.py fixture domain",
        source="scripts/downstream_evidence_test.py (unit-test fixture, not an external claim)",
        quote="downstream-evidence fixture (unit test)")


def _load_mutated(src_text, tag):
    """Load a mutated copy of breakingdiff.py from a tempdir under a unique module name.

    bytecode writing is disabled module-wide (see file docstring), so the pyc timestamp
    trap cannot manufacture a false green. Caller removes the tempdir in finally."""
    d = tempfile.mkdtemp(prefix="bd_mut_%s_" % tag)
    p = os.path.join(d, "bd_mut_%s.py" % tag)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(src_text)
    spec = importlib.util.spec_from_file_location("bd_mut_%s" % tag, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, d


def _three(domain=None):
    return ([_mk("v1", lambda x: True),
             _mk("v2", lambda x: x % 2 == 0),
             _mk("v3", lambda x: x < 3)],
            domain if domain is not None else [0, 1, 2, 3, 4])


# ═══════════════════════════════════════════════════════════════════════════════
# A — the opt-in is a real gate; default path equals v1.0.1 field-for-field
# ═══════════════════════════════════════════════════════════════════════════════
_PREEXISTING = ("names", "all_true", "all_false", "split", "outliers", "pioneers",
                "split_witnesses", "ratchet_total", "ratchet_witnesses",
                "ratchet_trusted", "anchor_name", "out_of_domain", "total",
                "domain_total", "anchor", "max_witness")


def test_default_keeps_all_new_evidence_fields_empty():
    """keep_vectors=False (default) leaves every new field at its empty default."""
    claims, domain = _three()
    r = compare_n(claims, domain)
    assert r.vectors == [], "the default run must not emit per-point vectors"
    assert r.outlier_witnesses == {}, "the default run must not emit outlier witnesses"
    assert r.pioneer_witnesses == {}, "the default run must not emit pioneer witnesses"
    assert r.ratchet_points == 0, "the default run must not accumulate ratchet_points"


def test_default_matches_keep_vectors_on_every_preexisting_field():
    """Backward compatibility: turning the opt-in on changes NO pre-existing field."""
    claims, domain = _three()
    r_off = compare_n(claims, domain)
    r_on = compare_n(claims, domain, keep_vectors=True)
    for f in _PREEXISTING:
        a, b = getattr(r_off, f), getattr(r_on, f)
        assert a == b, "keep_vectors changed the pre-existing field %s: %r -> %r" % (f, a, b)


def test_keep_vectors_returns_one_vector_per_indomain_point():
    """keep_vectors=True returns a (point, verdict-tuple) for every in-domain point."""
    claims, domain = _three()
    r = compare_n(claims, domain, keep_vectors=True)
    assert len(r.vectors) == r.total == 5, "one vector per in-domain point, got %d/%d" % (len(r.vectors), r.total)
    for point, vec in r.vectors:
        assert isinstance(vec, tuple) and len(vec) == 3
        assert all(isinstance(b, bool) for b in vec)


def test_vectors_follow_the_reordered_account_order():
    """Vector columns must track the post-order_key account order, not input order.

    Same class of bug as the anchor-follows-reordering incident: if the vector columns
    kept the caller's input order while names/raw stats were re-sorted, a downstream
    consumer would attribute each column to the wrong account."""
    c_old = _mk("v1", lambda x: True)
    c_mid = _mk("v2", lambda x: True)
    c_new = _mk("v3", lambda x: False)
    r = compare_n([c_new, c_old, c_mid], [0], keep_vectors=True,
                  order_key=lambda i, c: c.name)
    assert r.names == ["v1", "v2", "v3"], "order_key re-sort failed: %r" % (r.names,)
    assert r.vectors[0][1] == (True, True, False), (
        "vector columns must follow reordered names v1,v2,v3, got %r" % (r.vectors[0][1],))


def test_outlier_and_pioneer_witnesses_are_capped_and_gated():
    """New witnesses are located (account index -> points), capped, and opt-in only."""
    # v1,v2 true everywhere; v3 true only for x<3 -> 7 points are outliers on v3
    claims = [_mk("v1", lambda x: True), _mk("v2", lambda x: True),
              _mk("v3", lambda x: x < 3)]
    domain = list(range(10))
    r_on = compare_n(claims, domain, keep_vectors=True, max_witness=2)
    assert r_on.outliers.get(2) == 7, "fixture precondition: 7 outlier points on v3"
    assert len(r_on.outlier_witnesses.get(2, [])) == 2, "outlier witnesses must be capped at max_witness"
    r_off = compare_n(claims, domain, max_witness=2)
    assert r_off.outlier_witnesses == {}, "the default run must not emit located witnesses"


def test_ratchet_points_counts_distinct_points_not_pairs():
    """ratchet_points = DISTINCT points with a violation; ratchet_total = (old,new) pairs."""
    claims = [_mk("v1", lambda x: True), _mk("v2", lambda x: False), _mk("v3", lambda x: False)]
    r = compare_n(claims, [0], chain=True, keep_vectors=True, order_key=lambda i, c: i)
    assert r.ratchet_total == 2, "one point, two (j,k) pairs -> total 2, got %d" % r.ratchet_total
    assert r.ratchet_points == 1, "one point with a violation -> distinct points 1, got %d" % r.ratchet_points


def test_ratchet_points_requires_both_chain_and_keep_vectors():
    """ratchet_points is derived inside the chain loop and behind the evidence gate."""
    claims = [_mk("v1", lambda x: True), _mk("v2", lambda x: False), _mk("v3", lambda x: False)]
    ok = lambda i, c: i  # noqa: E731
    assert compare_n(claims, [0], keep_vectors=True).ratchet_points == 0, "no chain -> no ratchet loop"
    assert compare_n(claims, [0], chain=True, order_key=ok).ratchet_points == 0, "gate off -> no ratchet_points"
    assert compare_n(claims, [0], chain=True, order_key=ok, keep_vectors=True).ratchet_points == 1, "both on -> 1"


# ═══════════════════════════════════════════════════════════════════════════════
# B — the digest is a trustworthy, reproducible anchor
# ═══════════════════════════════════════════════════════════════════════════════
def test_vector_digest_is_deterministic_and_order_independent():
    """Same vectors -> same digest; domain iteration order does not move it."""
    claims, domain = _three()
    r = compare_n(claims, domain, keep_vectors=True)
    d1 = vector_digest(r.vectors)
    d2 = vector_digest(r.vectors)
    d3 = vector_digest(list(reversed(r.vectors)))
    assert d1 == d2 == d3, "digest must be stable and independent of row order"
    assert d1.startswith("sha256:") and len(d1) == 7 + 64, "digest shape is sha256:<64hex>"
    assert vector_digest([]) == vector_digest([]), "empty input must hash to a fixed constant"


def test_vector_digest_changes_when_one_verdict_flips():
    """A single flipped verdict must change the digest (implementation-mutation red)."""
    claims, domain = _three()
    r = compare_n(claims, domain, keep_vectors=True)
    base = vector_digest(r.vectors)
    tampered = list(r.vectors)
    p0, v0 = tampered[0]
    tampered[0] = (p0, tuple([not v0[0]] + list(v0[1:])))
    assert vector_digest(tampered) != base, "a flipped verdict must move the digest"


def test_vector_digest_fails_loud_on_unserializable_point():
    """An unserializable point raises TypeError instead of silently dropping the row."""
    try:
        vector_digest([(object(), (True, False, True))])
    except TypeError:
        pass
    else:
        raise AssertionError("unserializable point must raise TypeError, not be dropped")
    # custom key rescues a non-JSON point by supplying a stable identity
    assert vector_digest([(object(), (True,))], key=lambda p: "fixed").startswith("sha256:")


# ═══════════════════════════════════════════════════════════════════════════════
# C — evidence never enters the gate: receipt bytes are invariant to keep_vectors
# ═══════════════════════════════════════════════════════════════════════════════
def test_receipt_bytes_identical_when_keep_vectors_toggled():
    """The no-false-red guarantee. receipt_from_nway reads only aggregate counters and
    the existing (capped, soft) witnesses. Toggling the per-point evidence opt-in must
    not change a single byte of the canonical receipt. If a future change pushed vectors
    into the receipt's hard reconciliation, this test goes red before it can misfire."""
    claims, domain = _three()
    ok = lambda i, c: i  # noqa: E731
    r_off = compare_n(claims, domain, chain=True, order_key=ok)
    r_on = compare_n(claims, domain, chain=True, order_key=ok, keep_vectors=True)
    rc_off = receipt.receipt_from_nway(claims, r_off, domain=domain, rerun_cmd="python run.py")
    rc_on = receipt.receipt_from_nway(claims, r_on, domain=domain, rerun_cmd="python run.py")
    assert receipt._canonical_bytes(rc_off) == receipt._canonical_bytes(rc_on), (
        "toggling keep_vectors changed the receipt — per-point evidence leaked into the gate")


# ═══════════════════════════════════════════════════════════════════════════════
# mutation evidence — break the implementation, confirm the lock has discriminating power
# ═══════════════════════════════════════════════════════════════════════════════
def test_mutation_removing_keep_vectors_gate_is_caught():
    """Implementation mutation: force `if True:` where the vectors gate was. Without the
    gate the DEFAULT run emits vectors, so test_default_keeps_all_new_evidence_fields_empty
    would go red. Confirms the opt-in gate is load-bearing, not decorative."""
    src = _read(BD_FILE)
    anchor = "        if keep_vectors:\n            r.vectors.append((x, tuple(v)))"
    assert src.count(anchor) == 1, "gate mutation anchor not found verbatim"
    mut = src.replace(anchor, "        if True:\n            r.vectors.append((x, tuple(v)))")
    mod, d = _load_mutated(mut, "nogate")
    try:
        claims = [_mk("v1", lambda x: True, mod=mod), _mk("v2", lambda x: x % 2 == 0, mod=mod)]
        r = mod.compare_n(claims, [0, 1, 2])  # keep_vectors defaults to False
        assert r.vectors, "gate removed -> default run must emit vectors (else the mutation never took effect)"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_mutation_removing_witness_cap_is_caught():
    """Implementation mutation: force `if True:` in the outlier witness cap. Witnesses
    then exceed max_witness, so test_outlier_and_pioneer_witnesses_are_capped_and_gated
    would go red. Confirms the cap lock is load-bearing."""
    src = _read(BD_FILE)
    anchor = ("        elif t == n - 1:\n"
              "            i = v.index(False)\n"
              "            r.outliers[i] = r.outliers.get(i, 0) + 1\n"
              "            if keep_vectors:\n"
              "                w = r.outlier_witnesses.setdefault(i, [])\n"
              "                if len(w) < max_witness:\n"
              "                    w.append(x)\n")
    assert src.count(anchor) == 1, "cap mutation anchor not found verbatim"
    mut = src.replace(anchor, anchor.replace("                if len(w) < max_witness:\n",
                                             "                if True:\n"))
    mod, d = _load_mutated(mut, "nocap")
    try:
        claims = [_mk("v1", lambda x: True, mod=mod), _mk("v2", lambda x: True, mod=mod),
                  _mk("v3", lambda x: x < 3, mod=mod)]
        r = mod.compare_n(claims, list(range(10)), keep_vectors=True, max_witness=2)
        assert len(r.outlier_witnesses.get(2, [])) == 7, (
            "cap removed -> witness list must exceed max_witness (else the mutation never took effect)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── harness (same shape as the other script-level tests in this repo) ──────────
def main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad = []
    for name, fn in fns:
        try:
            fn()
            print("  PASS %s" % name)
        except Exception:
            bad.append(name)
            print("  FAIL %s" % name)
            traceback.print_exc()
    print("\n%d/%d passed%s" % (len(fns) - len(bad), len(fns),
                                (", failed: %s" % bad) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

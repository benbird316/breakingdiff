# -*- coding: utf-8 -*-
"""Misaligned accounts · the three readouts that look fine and are not.

`aligned.py` shows the correct readout. This file shows three ways to produce a
readout that is well-formed, correctly formatted, and wrong — all of them are
things you can do by accident, and none of them raises.

M1  The baseline is a choice, and the product column follows it
    The same 2,049 dimensions produce the same 193 removals whether you call the
    old spec P or Q. What changes is which column they land in: `divergence`
    when P is old, `dominance` when P is new. A tool that reports only the
    dominance column as "the product" gets the direction backwards on every
    removal — and removals are the only reason anyone runs a breaking-change
    audit.

M2  Scoping to one API group manufactures a clean readout
    Restricted to `resource.k8s.io`, the comparison domain collapses to 218
    points of which **exactly 1 is common**. A reviewer who scopes to one group
    and then only inspects the common set sees "1 point, zero differences" —
    a textbook false green, covering 217 dimensions it never looked at. This is
    level-2 silence (incomplete extraction producing a false zero) and the
    readout gives no hint that anything is missing.

M3  Not dereferencing `$ref` shrinks the surface by 72%
    In release-1.28, 2,089 of 2,916 declared parameters are `$ref`; only 827 are
    inline. An extractor that reads `type` directly sees 827 of them and reports
    on a surface one third the size. The counts differ between the two versions
    too (827 vs 912), so a `$ref`-blind extractor produces a *non-zero* drift
    count — a drift it invented by failing to resolve references.

Run: python misaligned.py
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(HERE))), "scripts"))

import aligned as A  # noqa: E402
from breakingdiff import compare  # noqa: E402


def _spec(fn):
    with open(os.path.join(HERE, fn), encoding="utf-8") as f:
        return json.load(f)


def m1_baseline_flip():
    print("#" * 74)
    print("# M1  swapping the baseline moves the product column — same data")
    print("#" * 74)
    old_as_p = compare(A.make_existence_claim(), A.make_existence_claim_new(),
                       A.UNION, max_witness=2)
    new_as_p = compare(A.make_existence_claim_new(), A.make_existence_claim(),
                       A.UNION, max_witness=2)
    print(f"  P = old spec   divergence(only 1.28) = {old_as_p.divergence:>4}"
          f"   dominance(only 1.31) = {old_as_p.dominance:>4}")
    print(f"  P = new spec   divergence(only 1.31) = {new_as_p.divergence:>4}"
          f"   dominance(only 1.28) = {new_as_p.dominance:>4}")
    print()
    print(f"  same total {old_as_p.total}; the removal count is invariant at "
          f"{min(old_as_p.dominance, new_as_p.dominance)} —")
    print("  only its column moved. **The product column is a function of the")
    print("  baseline, not of the data.**")
    return old_as_p, new_as_p


def m2_single_group_scope():
    print()
    print("#" * 74)
    print("# M2  scoping to one API group manufactures a false green")
    print("#" * 74)
    group = "resource.k8s.io"
    scoped = [p for p in A.UNION if A.api_group(p[0]) == group]
    a = {p for p in A.OLD if A.api_group(p[0]) == group}
    b = {p for p in A.NEW if A.api_group(p[0]) == group}
    common = a & b
    print(f"  scope = {group}")
    print(f"    comparison domain      {len(scoped):>5}")
    print(f"    common to both         {len(common):>5}")
    print(f"    removed in 1.31        {len(a - b):>5}")
    print(f"    added in 1.31          {len(b - a):>5}")
    print()
    print(f"  ★ The common set is {len(common)} point. A reviewer who scopes here and")
    print("    then reads only the common set sees one dimension and zero differences,")
    print(f"    while {len(scoped) - len(common)} dimensions in the very scope they")
    print("    chose go unread. The readout is complete, correctly formatted, and")
    print("    silent. Nothing in the four-quadrant table flags it — only the")
    print("    coverage guard in front of `compare` can, by asking whether the")
    print("    change left a footprint outside the surface under test.")
    return len(scoped), len(common)


def m3_ref_blind():
    print()
    print("#" * 74)
    print("# M3  an extractor that does not resolve $ref loses 72% of the surface")
    print("#" * 74)
    methods = A.METHODS
    rows = []
    for fn in (A.OLD_FILE, A.NEW_FILE):
        paths = _spec(fn).get("paths", {})
        total = ref = 0
        for path, ops in paths.items():
            if not isinstance(ops, dict):
                continue
            for m, op in ops.items():
                if m.lower() not in methods or not isinstance(op, dict):
                    continue
                for prm in op.get("parameters") or []:
                    if not isinstance(prm, dict):
                        continue
                    total += 1
                    if "$ref" in prm:
                        ref += 1
        rows.append((fn, total, ref, total - ref))
        print(f"  {fn:<16} declared {total:>5}   $ref {ref:>5}   inline {total - ref:>5}")
    _, t28, _, inl28 = rows[0]
    _, t31, _, inl31 = rows[1]
    print()
    print(f"  A $ref-blind extractor sees {inl28} parameters in 1.28 and {inl31} in 1.31 —")
    print(f"  a difference of {inl31 - inl28}. That difference is not a change in the API.")
    print("  It is the extractor failing to resolve references, and it is reported")
    print("  in the same column as real drift.")
    print()
    print("  Diagnosis before believing any zero: print the empty-scalar rate, the")
    print("  number of distinct values, and the most common values — three lines.")
    print("  A real green and a fake green separate at a glance (this is the coverage")
    print("  diagnosis prescribed in references/writing-claims.md).")
    return rows


def main():
    m1_baseline_flip()
    m2_single_group_scope()
    m3_ref_blind()
    print()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Iteration-chain instance: the "export capability" account differential across
three versions of the same tool.
====================================================
v1.0.0  json + csv
v2.0.0  json + csv + parquet
v3.0.0  json + xlsx        ← csv and parquet are both gone

A pairwise diff reports only "divergence", never a "regression direction" —
inside the divergence region of compare(v2, v3), csv (a regression) and parquet
(also dropped) sit next to every point that merely "changed differently", with
no attribution.
compare_n(chain=True) singles out "the old version had it, the new version
dropped it" as a ratchet violation and carries an (old, new, point) triple.

Run this file to print the two reports side by side.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from breakingdiff import Claim, compare, compare_n, render_n

# Corpus: the original changelog text of the three versions (quote_source;
# the quote is checked verbatim at construction time)
CHANGELOG_V1 = """# changelog v1.0.0
- export: --format json, --format csv
"""
CHANGELOG_V2 = """# changelog v2.0.0
- export: --format json, --format csv, --format parquet
"""
CHANGELOG_V3 = """# changelog v3.0.0
- export: --format json, --format xlsx
"""

# Parameter space: the export-capability points to enumerate
DOMAIN = ("json", "csv", "parquet", "xlsx")

SPECS = (
    ("v1.0.0", CHANGELOG_V1, "--format json, --format csv"),
    ("v2.0.0", CHANGELOG_V2, "--format json, --format csv, --format parquet"),
    ("v3.0.0", CHANGELOG_V3, "--format json, --format xlsx"),
)


def make_version_claim(version, changelog, quote):
    """Predicate factory: does capability point cap appear on this version's
    export line? Two independent corpus excerpts drive the source self-test —
    json is in every version, csv is in v1/v2 but not in v3."""
    def predicate(cap):
        return f"--format {cap}" in changelog

    tests = (("json", True),)
    if version != "v3.0.0":
        tests += (("csv", True),)
    else:
        tests += (("csv", False),)

    return Claim(
        name=version,
        predicate=predicate,
        applies=lambda cap: cap in DOMAIN,
        domain_note="export capability points enumerated (json/csv/parquet/xlsx)",
        source=f"demo-repo@{version}:CHANGELOG.md",
        quote=quote,
        quote_source=changelog,
        source_tests=tests,
    )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    claims = [make_version_claim(*spec) for spec in SPECS]
    v1, v2, v3 = claims

    # Track one: pairwise diff on adjacent versions. Note that neither report
    # ever says "regression".
    for P, Q in ((v1, v2), (v2, v3)):
        r = compare(P, Q, DOMAIN)
        print(f"--- pairwise compare({P.name}, {Q.name}): "
              f"common {r.common} / divergence {r.divergence} / dominance {r.dominance} / neither {r.neither}")

    # Track two: the chain check. A ratchet violation yields a directed
    # (old, new, point) triple.
    rn = compare_n(claims, DOMAIN, chain=True, anchor=0)
    print()
    print(render_n(claims, rn))

    # The pairwise readout drops the regression direction: csv and parquet both
    # land in the divergence region of compare(v2,v3); the report does not tell
    # which capability was dropped and which change was normal evolution.
    r23 = compare(v2, v3, DOMAIN)
    assert r23.divergence == 2, f"compare(v2,v3) should count csv+parquet in the divergence region, got {r23.divergence}"
    assert rn.ratchet_total == 3, f"expected 3 ratchet violations, got {rn.ratchet_total}"
    got = {(j, k, x) for j, k, x in rn.ratchet_witnesses}
    expect = {(0, 2, "csv"), (1, 2, "csv"), (1, 2, "parquet")}
    assert got == expect, f"ratchet witnesses do not match: {got}"
    assert rn.outliers == {2: 1}, f"csv should be recorded as one v3 outlier, got {rn.outliers}"
    assert rn.pioneers == {1: 1, 2: 1}, f"expected one pioneer each for parquet→v2 and xlsx→v3, got {rn.pioneers}"
    assert rn.all_true == 1 and rn.all_false == 0 and rn.split == 0
    print("All assertions pass: pairwise divergence has 2 points with no direction; the chain check finds 3 attributed ratchet violations.")
    return rn


if __name__ == "__main__":
    main()

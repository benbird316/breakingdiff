"""Fixture-integrity test for the docaudit promise-vs-behavior experiment (v1).

The fixture is a *detection target*, not a benchmark: it records what four blind testers
found when each only read a README, so a detector can be checked against real findings.
Run: python examples/docaudit/test_docaudit.py   (no pytest dependency)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "claims.json")

REQUIRED_FIELDS = ("id", "artifact", "class", "severity", "promise", "measured", "evidence")
CLASSES = {"doc-vs-behavior", "code-defect"}
SEVERITIES = {"high", "medium", "low"}


def load():
    with open(SPEC, encoding="utf-8") as f:
        return json.load(f)


def test_fixture_is_coherent():
    spec = load()
    defects = spec["defects"]
    ids = [d["id"] for d in defects]
    assert len(ids) == len(set(ids)), "duplicate defect id"
    for d in defects:
        for field in REQUIRED_FIELDS:
            assert d.get(field), f"{d.get('id')}: missing {field}"
        assert d["class"] in CLASSES, (d["id"], d["class"])
        assert d["severity"] in SEVERITIES, (d["id"], d["severity"])
        assert d["artifact"] in spec["artifacts"], (d["id"], d["artifact"])
        assert d["promise"] != d["measured"], f"{d['id']}: promise and measured are identical"
    assert spec["schema_version"] == 1


def test_summary_matches_the_findings():
    spec = load()
    defects = spec["defects"]
    summary = {
        "defects_total": len(defects),
        "doc_vs_behavior": sum(1 for d in defects if d["class"] == "doc-vs-behavior"),
        "code_defects": sum(1 for d in defects if d["class"] == "code-defect"),
        "high_severity": sum(1 for d in defects if d["severity"] == "high"),
        "silent_high_severity": sum(
            1 for d in defects if d["severity"] == "high" and d.get("silent")),
        "tier_counts": {tier: sum(1 for a in spec["artifacts"].values() if a["tier"] == tier)
                        for tier in ("A", "B", "C")},
    }
    assert summary == spec["expected_summary"], (summary, spec["expected_summary"])


def test_the_central_finding_holds_in_the_fixture():
    """The experiment's headline: almost every defect is a README promise the behavior
    does not uphold — not a missing feature, not an architecture problem."""
    spec = load()
    defects = spec["defects"]
    doc = [d for d in defects if d["class"] == "doc-vs-behavior"]
    assert len(doc) / len(defects) >= 0.8, f"promise-vs-behavior share dropped: {len(doc)}/{len(defects)}"
    silent_high = [d["id"] for d in defects if d["severity"] == "high" and d.get("silent")]
    assert len(silent_high) == 3, f"high-severity silent failures changed: {silent_high}"
    for artifact in spec["artifacts"]:
        assert any(d["artifact"] == artifact for d in defects), (
            f"artifact {artifact} has no recorded defect: a clean artifact in this fixture is suspicious")


def test_tiers_and_mechanical_metrics_are_recorded():
    spec = load()
    for name, art in spec["artifacts"].items():
        assert art["tier"] in {"A", "B", "C"}, (name, art["tier"])
        assert isinstance(art["required_params"], int) and art["required_params"] >= 0
        assert isinstance(art["explicit_unverified_statements"], int)
        assert art["explicit_unverified_statements"] >= 0


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
    print(f"{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

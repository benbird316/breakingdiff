"""Tests for strength_calibration: synthetic ladder logic + the malecns measured case.

No pytest dependency. Run: python strength_calibration_test.py
Exit code 0 = no failures (skips are reported and counted separately); 1 = at least one failure.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import strength_calibration as SC  # noqa: E402

PASS, SKIP, FAIL = [], [], []


class Skip(Exception):
    """A test that cannot run in this environment; counted separately from a pass."""


def skip(reason):
    raise Skip(reason)


def check(name, fn):
    """Run one test and record exactly one outcome: passed, skipped, or failed."""
    try:
        fn()
    except Skip as e:
        SKIP.append((name, str(e)))
    except Exception as e:  # noqa: BLE001 - a test runner reports, it does not crash
        FAIL.append((name, e))
    else:
        PASS.append(name)


# ---------------------------------------------------------------- synthetic cases
def synthetic_points():
    # 6 points; right is fixed at 10, left varies -- each shape fails a different subset.
    return [{"id": i, "left": left, "right": 10} for i, left in enumerate((7, 8, 9, 10, 11, 12))]


def test_ladder_orders_shapes_by_failures():
    pts = synthetic_points()
    shapes = (
        SC.Shape("hard equality L==R", lambda p: p["left"] == p["right"], rank=3),
        SC.Shape("point value", lambda p: p["left"] == 10, rank=2),
        SC.Shape("bounded ±2", lambda p: abs(p["left"] - p["right"]) <= 2, rank=1),
    )
    rows = SC.ladder(pts, shapes)
    assert [r.name for r in rows] == ["bounded ±2", "point value", "hard equality L==R"], rows
    assert [r.failures for r in rows] == [1, 5, 5], [r.failures for r in rows]


def test_recommend_picks_tightest_within_noise_budget():
    pts = synthetic_points()
    shapes = (
        SC.Shape("never fails", lambda p: True, rank=0),
        SC.Shape("bounded ±2", lambda p: abs(p["left"] - p["right"]) <= 2, rank=1),
        SC.Shape("point value", lambda p: p["left"] == 10, rank=3),
    )
    report = SC.calibrate(pts, shapes, baseline=lambda p: True, max_noise=0.2)
    assert report["recommended"].name == "bounded ±2"
    assert report["decorative"] == ["never fails"]
    assert "point value" in report["over_noise"]


def test_recommend_skips_decorative_when_a_real_candidate_fits():
    """A high-rank decorative shape must lose to a lower-rank shape that actually fails."""
    rows = [
        SC.Row("always true", 0, 0.0, rank=9),
        SC.Row("bounded", 2, 0.02, rank=2),
        SC.Row("too noisy", 50, 0.50, rank=5),
    ]
    chosen = SC.recommend(rows, max_noise=0.05)
    assert chosen is not None and chosen.name == "bounded", chosen
    assert chosen.warning == ""


def test_recommend_tie_break_is_deterministic():
    """Equal rank: fewer failures wins, then the lexicographically smaller name."""
    rows = [
        SC.Row("zeta", 2, 0.02, rank=2),
        SC.Row("alpha", 2, 0.02, rank=2),
        SC.Row("fewer", 1, 0.01, rank=2),
    ]
    assert SC.recommend(rows, max_noise=0.05).name == "fewer"
    tied = [r for r in rows if r.failures == 2]
    assert SC.recommend(tied, max_noise=0.05).name == "alpha"
    assert SC.recommend(list(reversed(tied)), max_noise=0.05).name == "alpha"


def test_all_decorative_budget_yields_a_warned_recommendation():
    report = SC.calibrate(
        [1, 2, 3], (SC.Shape("always true", lambda p: True, rank=1),),
        baseline=lambda p: True)
    assert report["recommended"] is not None
    assert report["recommended"].failures == 0
    assert report["recommended"].warning.startswith("[SC:DECORATIVE")
    assert report["recommendation_decorative"] is True
    assert report["recommendation_warning"].startswith("[SC:DECORATIVE")


def test_ladder_ratio_is_failures_over_baseline_valid_points():
    points = [0, 1, 2, 3, 4]                      # baseline-true: 2, 3, 4 (3 valid points)
    rows = SC.ladder(
        points, (SC.Shape("odd", lambda p: p % 2, rank=1),), baseline=lambda p: p >= 2)
    assert rows[0].failures == 2                  # 2 and 4 fail, 3 passes
    assert abs(rows[0].ratio - 2 / 3) < 1e-12     # over 3 valid points, not over 5


def test_decorative_shape_is_reported_not_hidden():
    rows = SC.ladder([{"x": 1}], (SC.Shape("always true", lambda p: True),))
    assert SC.decorative(rows) == ["always true"]


def test_provenance_rejects_unknown_kind_and_warns_on_same_data():
    try:
        SC.provenance("vibes")
    except ValueError as e:
        assert "[SC:UNKNOWN_PROVENANCE]" in str(e)
    else:
        raise AssertionError("unknown provenance must raise")
    rec = SC.provenance("same-data", "width from this dataset's own spread")
    assert rec["warning"].startswith("band width derived from the same data")


def test_preregistration_record_shape():
    row = SC.Row("bounded ±3", 1, 0.1, rank=1)
    rec = SC.preregistration(
        ["C1", "C2"], row, band={"rel": 0.3, "floor": 1},
        allowed_flips=[{"point": "KCab-s", "why": "measured asymmetry"}], reviewer="R")
    assert rec["shape"] == "bounded ±3"
    assert rec["allowed_flips"][0]["point"] == "KCab-s"
    assert rec["band"]["rel"] == 0.3
    assert rec["ladder"] == []                    # legacy call freezes only the shape
    assert rec["band_provenance"] == {}


def test_preregistration_freezes_full_ladder_and_provenance():
    rows = [
        SC.Row("hard equality", 9, 0.90, rank=3),
        SC.Row("bounded ±2", 1, 0.01, rank=1),
    ]
    chosen = SC.recommend(rows)
    assert chosen is not None and chosen.name == "bounded ±2"
    prov = SC.provenance("same-data", "width from this dataset's own spread")
    rec = SC.preregistration(
        ["C2", "C1"], chosen, band={"rel": 0.3}, reviewer="R",
        ladder_rows=reversed(rows), band_provenance=prov)
    assert rec["claims"] == ["C1", "C2"]
    assert rec["ladder"] == [
        {"name": "bounded ±2", "failures": 1},
        {"name": "hard equality", "failures": 9},
    ]
    assert rec["band_provenance"] == prov
    assert rec["band_provenance"]["warning"].startswith("band width derived from the same data")


# ---------------------------------------------------------------- malecns measured case
def _malecns():
    case = os.path.join(ROOT, "casestudy", "malecns")
    if not all(os.path.isfile(os.path.join(case, f)) for f in (
            "body-annotations-male-cns-v0.9-minconf-0.5.feather",
            "body-neurotransmitters-male-cns-v0.9.feather")):
        skip("malecns ladder: corpus absent (run fetch_corpus.py in casestudy/malecns)")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'malecns_aligned', os.path.join(case, 'aligned.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['malecns_aligned'] = mod
    spec.loader.exec_module(mod)
    return mod


def test_malecns_false_red_ladder_matches_teaching_values():
    aligned = _malecns()
    counts = aligned.load_counts()
    totals = aligned.load_type_totals()
    fr = aligned.load_nt_fractions()
    if not counts:
        skip("malecns ladder: corpus present but load_counts() returned no points")

    def nt_top1(p):
        v = fr.get(p[0])
        return True if v is None else v[0] == v[2]

    shapes = (
        SC.Shape("bounded band (P1, ±30%)", aligned.build_p1_claim().predicate, rank=1),
        SC.Shape("point value (total // 2)", lambda p: counts[p] == totals[p[0]] // 2, rank=3),
        SC.Shape("hard equality (nL == nR)",
                 lambda p: counts.get((p[0], "L"), 0) == counts.get((p[0], "R"), 0), rank=3),
        SC.Shape("granularity confusion (voted top-1 as type label)", nt_top1, rank=0),
    )
    report = SC.calibrate(
        aligned.domain_points(), shapes,
        baseline=aligned.build_q_claim().predicate)
    got = {r.name: r.failures for r in report["ladder"]}
    expected = {
        "bounded band (P1, ±30%)": 12,
        "point value (total // 2)": 2720,
        "hard equality (nL == nR)": 4354,
        "granularity confusion (voted top-1 as type label)": 241,
    }
    for name, want in expected.items():
        assert got[name] == want, f"{name}: got {got[name]}, expected {want} (ladder {got})"
    assert report["recommended"].name == "bounded band (P1, ±30%)", report["recommended"]
    assert set(report["over_noise"]) == {
        "point value (total // 2)", "hard equality (nL == nR)"}



# ---------------------------------------------------------------- E2E: other case studies
def _port_claims():
    import json
    with open(os.path.join(ROOT, "casestudy", "port", "claims.json"), encoding="utf-8") as f:
        spec = json.load(f)
    return spec


def _eval_port_predicate(pred, point):
    op = pred["op"]
    if op == "always":
        return True
    value = point.get(pred.get("field", "n"))
    if op == "ge":
        return value >= pred["value"]
    if op == "gt":
        return value > pred["value"]
    if op == "band":
        return pred["lo"] <= value < pred["hi"]
    raise ValueError(f"unknown op {op!r}")


def test_e2e_port_deterministic_spec_has_no_calibratable_strength():
    """port is a claim *spec* over 0..24, not noisy measurements: every predicate is
    deterministic. The ladder is a map of the spec, and no shape fits a 5% noise budget —
    the tool must refuse to recommend a strength instead of inventing one."""
    spec = _port_claims()
    points = [pt["n"] for pt in spec["domain"]]
    shapes = []
    for pair in spec["pairs"]:
        for side in ("P", "Q"):
            claim = pair[side]
            shapes.append(SC.Shape(claim["name"],
                                   lambda p, c=claim: _eval_port_predicate(c["predicate"], {"n": p})))
    first = SC.calibrate(points, shapes, baseline=None)
    second = SC.calibrate(points, shapes, baseline=None)
    first_signature = [(r.name, r.failures) for r in first["ladder"]]
    second_signature = [(r.name, r.failures) for r in second["ladder"]]
    assert first_signature == second_signature, "ladder must be deterministic"
    assert first["recommended"] is None, first["recommended"]
    assert first["over_noise"], "every port claim is over the noise budget (it is a spec)"


def _pdg_aligned():
    case = os.path.join(ROOT, "casestudy", "pdg")
    db = os.path.join(case, "pdg.sqlite")
    if not os.path.isfile(db) or os.path.getsize(db) == 0:
        skip("pdg ladder: pdg.sqlite absent (run casestudy/pdg/fetch_data.py)")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'pdg_aligned', os.path.join(case, 'aligned.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['pdg_aligned'] = mod
    spec.loader.exec_module(mod)
    return mod


def test_e2e_pdg_criteria_ladder_has_no_clean_strength():
    """PDG's 17 independent measurements of one quantity stay in tension at every sigma
    criterion (16/16/16/14/14 flagged of 17). The honest readout: no criterion fits a 5%
    noise budget — PDG's problem is account caliber, not assertion strength."""
    aligned = _pdg_aligned()
    rows = aligned.load_measurements(aligned.TARGET_DESC)
    base = rows[0][1]
    shapes = tuple(
        SC.Shape(f"{label} criterion", lambda r, m=mult: abs(r[1] - base) <= max(r[2], r[3]) * m)
        for label, mult in aligned.CRITERIA)
    report = SC.calibrate(rows, shapes, baseline=None)
    got = sorted(r.failures for r in report["ladder"])
    assert got == [14, 14, 16, 16, 16], got
    assert report["recommended"] is None, report["recommended"]


def test_degenerate_all_false_readout_has_no_recommendation():
    """An all-false shape over three synthetic points is degenerate: it fails every point, so
    it is far over the 5% budget and no strength may be recommended.

    This is a unit check of the degenerate-readout rule, not a llama corpus test: the llama
    probes scan ~700 MB of binaries per build, which is not cheap enough for this suite."""
    report = SC.calibrate([1, 2, 3], (SC.Shape("all false", lambda p: False),))
    assert report["recommended"] is None, report["recommended"]
    assert report["recommendation_decorative"] is False
    assert report["over_noise"] == ["all false"]



def _port_implementations():
    """Build/run the three implementations through the port case's own harness."""
    case = os.path.join(ROOT, "casestudy", "port")
    sys.path.insert(0, case)
    import test_port as tp  # noqa: E402

    if not (tp.HAS_GO and tp.HAS_RUSTC):
        missing = [name for name, ok in (("go", tp.HAS_GO), ("rustc", tp.HAS_RUSTC)) if not ok]
        skip("port cross-implementation ladder: missing toolchain " + ", ".join(missing))
    spec = tp._load_spec()
    ref = tp._reference_results()
    code, go, err = tp._go_results()
    if code != 0:
        raise AssertionError(f"go implementation failed ({code}): {err[:300]}")
    code, rust, err = tp._rust_results()
    if code != 0:
        raise AssertionError(f"rust implementation failed ({code}): {err[:300]}")
    return spec, ref, go, rust


def test_e2e_port_three_implementations_share_the_same_ladder():
    """A deterministic claim spec has no noise to calibrate, so the correct E2E is
    invariance: all three implementations must produce byte-identical readouts per pair.
    Any strength ladder computed from that readout is then implementation-invariant too."""
    spec, ref, go, rust = _port_implementations()

    def fingerprint(results):
        return sorted(
            (r["id"], r["verdict"], r["common"], r["divergence"],
             r["dominance"], r["neither"], r.get("out_of_domain", 0))
            for r in results)

    f_ref, f_go, f_rust = fingerprint(ref), fingerprint(go["results"]), fingerprint(rust["results"])
    assert f_ref == f_go == f_rust, (
        "the three implementations disagree on the readout:\n"
        f"  python {f_ref}\n  go     {f_go}\n  rust   {f_rust}")
    assert len(f_ref) == len(spec["pairs"]), (len(f_ref), len(spec["pairs"]))


def main():
    tests = [
        ("test_ladder_orders_shapes_by_failures", test_ladder_orders_shapes_by_failures),
        ("test_recommend_picks_tightest_within_noise_budget", test_recommend_picks_tightest_within_noise_budget),
        ("test_recommend_skips_decorative_when_a_real_candidate_fits", test_recommend_skips_decorative_when_a_real_candidate_fits),
        ("test_recommend_tie_break_is_deterministic", test_recommend_tie_break_is_deterministic),
        ("test_all_decorative_budget_yields_a_warned_recommendation", test_all_decorative_budget_yields_a_warned_recommendation),
        ("test_ladder_ratio_is_failures_over_baseline_valid_points", test_ladder_ratio_is_failures_over_baseline_valid_points),
        ("test_decorative_shape_is_reported_not_hidden", test_decorative_shape_is_reported_not_hidden),
        ("test_provenance_rejects_unknown_kind_and_warns_on_same_data", test_provenance_rejects_unknown_kind_and_warns_on_same_data),
        ("test_preregistration_record_shape", test_preregistration_record_shape),
        ("test_preregistration_freezes_full_ladder_and_provenance", test_preregistration_freezes_full_ladder_and_provenance),
        ("test_malecns_false_red_ladder_matches_teaching_values", test_malecns_false_red_ladder_matches_teaching_values),
        ("test_e2e_port_deterministic_spec_has_no_calibratable_strength", test_e2e_port_deterministic_spec_has_no_calibratable_strength),
        ("test_e2e_pdg_criteria_ladder_has_no_clean_strength", test_e2e_pdg_criteria_ladder_has_no_clean_strength),
        ("test_degenerate_all_false_readout_has_no_recommendation", test_degenerate_all_false_readout_has_no_recommendation),
        ("test_e2e_port_three_implementations_share_the_same_ladder", test_e2e_port_three_implementations_share_the_same_ladder),
    ]
    for name, fn in tests:
        check(name, fn)
    for name, reason in SKIP:
        print(f"SKIP: {name} — {reason}")
    for name, err in FAIL:
        print(f"FAIL: {name}: {err}")
    assert len(PASS) + len(SKIP) + len(FAIL) == len(tests), (
        "runner accounting lost a test")
    print(f"{len(PASS)} passed, {len(SKIP)} skipped, {len(FAIL)} failed "
          f"(of {len(tests)})")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

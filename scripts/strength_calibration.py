"""strength_calibration — measure how strong a claim should be, before a gate depends on it.

The engine answers "what does this claim read at each parameter point". This module answers a
different question: given the data's own occurrence pattern, how many points does a *shape*
flag — and is that number a signal or noise?

Pure stdlib, no third-party dependencies. The module is intentionally domain-agnostic: a
`point` is any hashable object, a `shape` is a named predicate over one point, and a baseline
predicate marks "valid points" (for a claim differential that is usually the existence
baseline). Callers pass their own predicates; the case study supplies the data.

Measured case: casestudy/malecns — same data, same domain, only the shape changes:
bounded 12, point value 2,720, hard equality 4,354, granularity-confused vote 241.
"""

from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class Shape:
    """One candidate claim shape.

    `rank` orders shapes from loosest (low) to tightest (high); `recommend` uses it to pick
    the tightest shape that still meets the noise budget. `note` is for the report.
    """

    name: str
    predicate: Callable[[Any], bool]
    rank: int = 0
    note: str = ""


@dataclass(frozen=True)
class Row:
    """One measured row of the false-red ladder.

    `warning` is empty for a normal row. `recommend` sets it on the row it returns when every
    shape inside the noise budget is decorative: such a row is returned for visibility, but it
    must not be used as a gate without acknowledging that it can never fail.
    """

    name: str
    failures: int
    ratio: float
    rank: int = 0
    note: str = ""
    warning: str = ""


BAND_PROVENANCE = ("design-tolerance", "same-data", "external-anchor")

DECORATIVE_WARNING = (
    "[SC:DECORATIVE_RECOMMENDATION] every shape inside the noise budget never fails; "
    "the returned row cannot distinguish good data from bad, so it must not gate anything"
)


def ladder(
    points: Iterable[Any],
    shapes: Iterable[Shape],
    baseline: Callable[[Any], bool] | None = None,
) -> list[Row]:
    """Measure every shape against the same points; return rows sorted by failures ascending.

    A failure is a point where `baseline(point)` is true and `shape.predicate(point)` is false.
    Without a baseline every point is treated as valid — pass the existence baseline when the
    case has one, otherwise the ratio means "flagged share of all points", not "false red".

    `ratio` is always ``failures / number of valid points``, i.e. the false-red rate over the
    points the baseline marks as valid (baseline-true points), and **not** over all points.
    When there are no valid points every ratio is 0.0, because there is nothing to fail.

    Rows are ordered by ``(failures, rank, name)``, so the ladder order is deterministic even
    when two shapes fail the same number of points with the same rank.
    """
    pts = list(points)
    valid = [p for p in pts if baseline(p)] if baseline is not None else pts
    total = len(valid)
    rows = []
    for shape in shapes:
        fails = sum(1 for p in valid if not shape.predicate(p))
        rows.append(Row(shape.name, fails, (fails / total) if total else 0.0,
                        shape.rank, shape.note))
    return sorted(rows, key=lambda r: (r.failures, r.rank, r.name))


def recommend(rows: Iterable[Row], max_noise: float = 0.05) -> Row | None:
    """Pick the tightest *non-decorative* shape whose failure share is at most `max_noise`.

    Selection rule (deterministic):

    1. Keep only rows with ``ratio <= max_noise``.
    2. Prefer rows with ``failures > 0``. A decorative row (0 failures) is never chosen while a
       non-decorative row is inside the budget, even if the decorative row has a higher rank.
    3. Among the remaining rows the highest ``rank`` wins (the tightest shape); ties are broken
       by fewer ``failures`` and then by ascending ``name``.

    Returns `None` when no shape is inside the budget: the right move is then to add a looser
    shape or to fix the domain, not to accept a noisy gate.

    If every in-budget shape is decorative, the best decorative row is returned with
    ``Row.warning`` set to `DECORATIVE_WARNING` rather than silently pretending a strength was
    found. Callers should check ``row.warning`` (or ``report["recommendation_decorative"]``
    from `calibrate`) before using the row as a gate.
    """
    ok = [r for r in rows if r.ratio <= max_noise]
    if not ok:
        return None
    non_decorative = [r for r in ok if r.failures > 0]
    pool = non_decorative or ok
    best_rank = max(r.rank for r in pool)
    best = min((r for r in pool if r.rank == best_rank),
               key=lambda r: (r.failures, r.name))
    if not non_decorative:
        best = replace(best, warning=DECORATIVE_WARNING)
    return best


def decorative(rows: Iterable[Row]) -> list[str]:
    """Shapes that never fail: they cannot distinguish good data from bad — declared, not hidden."""
    return [r.name for r in rows if r.failures == 0]


def provenance(kind: str, detail: str = "") -> dict:
    """Declare where the band width came from; a same-data width is self-consistency only.

    `kind` is one of BAND_PROVENANCE. Raises on an unknown kind: an undeclared provenance is
    exactly the silent assumption this tool exists to surface.
    """
    if kind not in BAND_PROVENANCE:
        raise ValueError(
            f"[SC:UNKNOWN_PROVENANCE] kind={kind!r} is not one of {BAND_PROVENANCE}")
    record = {"kind": kind, "detail": detail}
    if kind == "same-data":
        record["warning"] = (
            "band width derived from the same data: a low false-red rate is self-consistency, "
            "not generalization")
    return record


def preregistration(
    claim_keys: Iterable[str],
    chosen: Row | None,
    band: Mapping[str, Any] | None = None,
    allowed_flips: Iterable[Mapping[str, str]] = (),
    reviewer: str = "",
    ladder_rows: Iterable[Row] | None = None,
    band_provenance: Mapping[str, Any] | None = None,
) -> dict:
    """Record the strength decision *before* looking at the readout.

    Fields mirror a case manifest: which claims, which shape, the full ladder signature, the
    band and its provenance, the points allowed to flip (with a reason each), and who reviewed
    it. Keeping the record next to the case is what makes an after-the-fact tuning session
    auditable.

    `ladder_rows` freezes the staircase itself, not just the chosen name: the record stores
    ``{"name", "failures"}`` for every row, sorted by ``(failures, name)`` so the signature is
    canonical regardless of the caller's row order. Omit it only for legacy callers; then
    ``"ladder"`` is empty and only the chosen shape is frozen.

    `band_provenance` accepts a record returned by `provenance()` and emits it unchanged (as a
    copy), so a same-data band keeps its warning next to the decision. Both new parameters are
    optional and the original five-argument call still works.
    """
    rows = [] if ladder_rows is None else [
        {"name": r.name, "failures": r.failures}
        for r in sorted(ladder_rows, key=lambda r: (r.failures, r.name))]
    return {
        "claims": sorted(claim_keys),
        "shape": chosen.name if chosen else None,
        "ladder": rows,
        "band": dict(band) if band else {},
        "band_provenance": dict(band_provenance) if band_provenance else {},
        "allowed_flips": [dict(f) for f in allowed_flips],
        "reviewer": reviewer,
    }


def calibrate(
    points: Iterable[Any],
    shapes: Iterable[Shape],
    baseline: Callable[[Any], bool] | None = None,
    max_noise: float = 0.05,
) -> dict:
    """Full report: the ladder, the recommendation, and the warnings worth acting on.

    ``recommendation_decorative`` is True when the returned recommendation is a decorative row
    (0 failures), which can only happen when every in-budget shape is decorative. In that case
    ``recommendation_warning`` carries the same text as the row's `Row.warning`.
    """
    pts = list(points)
    rows = ladder(pts, shapes, baseline)
    chosen = recommend(rows, max_noise)
    return {
        "points": len(pts),
        "ladder": rows,
        "recommended": chosen,
        "recommendation_decorative": bool(chosen is not None and chosen.failures == 0),
        "recommendation_warning": chosen.warning if chosen else "",
        "decorative": decorative(rows),
        "over_noise": [r.name for r in rows if r.ratio > max_noise],
        "max_noise": max_noise,
    }


def format_report(report: Mapping[str, Any]) -> str:
    """Human-readable rendering of a calibrate() report (used by the case adapter and tests)."""
    lines = [f"points {report['points']} | noise budget {report['max_noise']:.0%}"]
    lines.append(f"{'shape':44s} {'failures':>9s} {'share':>8s}  rank")
    for row in report["ladder"]:
        lines.append(f"{row.name:44s} {row.failures:9d} {row.ratio:8.2%}  {row.rank}")
    chosen = report["recommended"]
    lines.append(f"recommended: {chosen.name if chosen else 'none — every shape is over the noise budget'}")
    if chosen is not None and report.get("recommendation_decorative"):
        lines.append("WARNING: recommendation is decorative — " + report["recommendation_warning"])
    if report["decorative"]:
        lines.append("decorative (never fails): " + ", ".join(report["decorative"]))
    if report["over_noise"]:
        lines.append("over budget: " + ", ".join(report["over_noise"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import sys
    if argv and argv[0] == "--self-check":
        pts = list(range(100))
        shapes = (
            # The decorative shape has the highest rank on purpose: rank alone must not win.
            Shape("never fails", lambda p: p >= 0, rank=4),
            Shape("hard equality", lambda p: p == 0, rank=3),
            Shape("bounded", lambda p: p <= 96, rank=2),
        )
        report = calibrate(pts, shapes, baseline=lambda p: True)
        assert report["recommended"].name == "bounded"
        assert report["recommended"].warning == ""
        assert report["recommendation_decorative"] is False
        assert report["decorative"] == ["never fails"]
        only_decorative = calibrate(
            pts, (Shape("always true", lambda p: True, rank=1),), baseline=lambda p: True)
        assert only_decorative["recommended"] is not None
        assert only_decorative["recommendation_decorative"] is True
        assert only_decorative["recommendation_warning"].startswith("[SC:DECORATIVE")
        print("strength_calibration self-check OK")
        return 0
    print("usage: python strength_calibration.py --self-check")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))

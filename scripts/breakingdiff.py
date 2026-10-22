# -*- coding: utf-8 -*-
"""
breakingdiff — domain-agnostic claim differential core (V0.1)
=============================================================
Given two executable claims P, Q and one shared parameter space, mechanically compute:
    common      P ∧  Q     both hold
    divergence  P ∧ ¬Q     ← P is stronger
    dominance  ¬P ∧  Q     ← ⚠️ Q is stronger (this column is the product)
    neither    ¬P ∧ ¬Q     neither holds
    out of domain     one of them is undefined

Design principle: this module contains **no domain knowledge**. Domain semantics
(what risk "dominance" actually implies) is injected by the caller through
render(..., meaning_divergence=..., meaning_dominance=...).
"""
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


class ProvenanceError(ValueError):
    """A claim is missing provenance or a verbatim quote fragment.

    Structured field (i18n Phase 0): `reason` is a stable criterion code
    (MISSING_SOURCE / MISSING_QUOTE / QUOTE_NOT_LITERAL / SOURCE_KIND_INVALID /
    SOURCE_OBJ_FORMAT / BACKSLASH_PATH / KIND_CONTRADICTION / MISSING_SOURCE_OBJ /
    QUOTE_REF_FORMAT). The message text is translated; the code never changes.
    """

    def __init__(self, message: str, *, reason: str = "UNSPECIFIED"):
        super().__init__(message)
        self.reason = reason


class SourceTestError(ValueError):
    """The claim's formalization conflicts with the source example it cites itself."""

    def __init__(self, message: str, *, reason: str = "UNSPECIFIED"):
        super().__init__(message)
        self.reason = reason


# Provenance tiers (two; executed/AST is an interface left unimplemented) and the
# external-anchor format. Format constants live in this single core source of truth:
# provenance and the receipt both reference it, and format drift would break Claim
# construction and verification at the same time, so consumers must not copy it.
SOURCE_KINDS = ("self-attested", "git-object")
SOURCE_OBJ_RE = re.compile(r"([0-9a-f]{40}):(.+)")
SELF_ATTESTED_HINT = "self-attested, not verified against an external anchor; supply source_obj to promote to git-object"
QUOTE_SOURCE_REF_RE = re.compile(r"(.+)@([0-9a-f]{40}):L(\d+)-L(\d+)")   # line-range external anchor: "path-in-repo@full 40-char lowercase hex sha:Lstart-Lend" (2.2, same 40-char source as SOURCE_OBJ_RE)


@dataclass(frozen=True)
class Claim:
    name: str
    predicate: Callable[[Any], bool]      # parameter point -> bool
    applies: Callable[[Any], bool]        # whether the claim is defined at this parameter point
    domain_note: str
    source: str                           # provenance
    quote: str                            # verbatim source fragment (provenance binding)
    quote_source: str = ""                # full source text; when given, construction checks the quote is verbatim inside it
    source_tests: Tuple[Tuple[Any, bool], ...] = ()
    reading_variants: Tuple['Claim', ...] = ()   # other reasonable formalizations of the same source sentence (interpretations)
    # ── provenance-tier fields (appended for backward compatibility: defaults keep the old behavior) ──
    source_obj: str = ""                  # external anchor "full 40-char lowercase hex sha:path-in-repo" (forward slashes); the verification object for the git-object tier
    source_kind: str = "self-attested"    # two tiers: self-attested = declared, unverified; git-object = external anchor declared, verified via provenance.verify
    quote_source_ref: str = ""            # line-range external anchor "path-in-repo@full 40-char sha:Lstart-Lend"; verification compares the line range via provenance.verify

    def __post_init__(self):
        if not isinstance(self.source, str) or not self.source.strip():
            raise ProvenanceError(f"[BD:MISSING_SOURCE] [{self.name}] missing source",
                                  reason="MISSING_SOURCE")
        if not isinstance(self.quote, str) or not self.quote.strip():
            raise ProvenanceError(f"[BD:MISSING_QUOTE] [{self.name}] missing verbatim source fragment (provenance binding failed)",
                                  reason="MISSING_QUOTE")
        if self.quote_source and self.quote not in self.quote_source:
            raise ProvenanceError(f"[BD:QUOTE_NOT_LITERAL] [{self.name}] quote is not inside quote_source (verbatim check failed)",
                                  reason="QUOTE_NOT_LITERAL")
        if self.source_kind not in SOURCE_KINDS:
            raise ProvenanceError(
                f"[BD:SOURCE_KIND_INVALID] [{self.name}] source_kind must be {'|'.join(SOURCE_KINDS)}, "
                f"got {self.source_kind!r}. An unknown tier that can still be constructed is a false tier declaration",
                reason="SOURCE_KIND_INVALID")
        if self.source_obj:
            m = SOURCE_OBJ_RE.fullmatch(self.source_obj)
            if not m:
                raise ProvenanceError(
                    f"[BD:SOURCE_OBJ_FORMAT] [{self.name}] source_obj must be "
                    f"\"full 40-char lowercase hex sha:path-in-repo\", got {self.source_obj!r}. "
                    "A short sha is ambiguous (more than one object may share the prefix), so it is forbidden",
                    reason="SOURCE_OBJ_FORMAT")
            if "\\" in m.group(2):
                raise ProvenanceError(
                    f"[BD:BACKSLASH_PATH] [{self.name}] source_obj paths use forward slashes (git's internal convention), "
                    f"got backslashes: {self.source_obj!r}",
                    reason="BACKSLASH_PATH")
            if self.source_kind != "git-object":
                raise ProvenanceError(
                    f"[BD:KIND_CONTRADICTION] [{self.name}] source_obj is declared but source_kind is still self-attested; "
                    "the tiers contradict. Once an external anchor is supplied, promote to git-object",
                    reason="KIND_CONTRADICTION")
        elif self.source_kind == "git-object":
            raise ProvenanceError(
                f"[BD:MISSING_SOURCE_OBJ] [{self.name}] source_kind=git-object requires source_obj; "
                "without an object anchor there is nothing to verify — it is only self-attestation under another name",
                reason="MISSING_SOURCE_OBJ")

        if self.quote_source_ref:
            m = QUOTE_SOURCE_REF_RE.fullmatch(self.quote_source_ref)
            if not m:
                raise ProvenanceError(
                    f"[BD:QUOTE_REF_FORMAT] [{self.name}] quote_source_ref must be "
                    "\"path-in-repo@full 40-char lowercase hex sha:Lstart-Lend\" (line numbers must carry the L prefix, "
                    "the sha must be all 40 chars), "
                    f"got {self.quote_source_ref!r}",
                    reason="QUOTE_REF_FORMAT")
            if "\\" in m.group(1):
                raise ProvenanceError(
                    f"[BD:BACKSLASH_PATH] [{self.name}] quote_source_ref paths use forward slashes (git's internal convention), "
                    f"got backslashes: {self.quote_source_ref!r}",
                    reason="BACKSLASH_PATH")

    def run_source_tests(self) -> Tuple[int, int, List[str]]:
        ok, fails = 0, []
        for x, expected in self.source_tests:
            got = bool(self.predicate(x))
            if got == bool(expected):
                ok += 1
            else:
                fails.append(f"parameter point {x}: expected {expected}, got {got}")
        return ok, len(self.source_tests), fails

    def run_reading_discrimination(self) -> List[Any]:
        """Points in source_tests where this claim and any interpretation disagree.
        An empty list = the test set has zero discriminating power over
        "formalization drift" (= an invalid test)."""
        pts = []
        for x, _ in self.source_tests:
            mine = bool(self.predicate(x))
            if any(bool(v.predicate(x)) != mine for v in self.reading_variants):
                pts.append(x)
        return pts


@dataclass
class DiffResult:
    p_name: str
    q_name: str
    common: int = 0
    divergence: int = 0
    dominance: int = 0
    neither: int = 0
    out_of_domain: int = 0
    divergence_witnesses: List[Any] = field(default_factory=list)
    dominance_witnesses: List[Any] = field(default_factory=list)
    max_witness: int = 8

    @property
    def total(self) -> int:
        return self.common + self.divergence + self.dominance + self.neither

    def pct(self, n: int) -> float:
        return 100.0 * n / self.total if self.total else 0.0


def _guard(claim: Claim) -> None:
    ok, tot, fails = claim.run_source_tests()
    if tot and fails:
        raise SourceTestError(f"[BD:SOURCE_TEST_FAILED] [{claim.name}] source self-test failed ({ok}/{tot}): {fails}",
                              reason="SOURCE_TEST_FAILED")
    # Discrimination gate: the test set must tell the interpretations apart,
    # otherwise it cannot stop "formalization drift".
    if claim.reading_variants and not claim.run_reading_discrimination():
        raise SourceTestError(
            f"[BD:READING_DISCRIMINATION_ZERO] [{claim.name}] source_tests have zero discriminating power over the interpretations: "
            f"{len(claim.reading_variants)} interpretations share the same value as this claim "
            f"at all {tot} test points → the test set cannot detect formalization drift and is treated as invalid",
            reason="READING_DISCRIMINATION_ZERO")


def compare(P: Claim, Q: Claim, domain: Iterable[Any],
            max_witness: int = 8) -> DiffResult:
    _guard(P)
    _guard(Q)
    r = DiffResult(P.name, Q.name, max_witness=max_witness)
    for x in domain:
        if not (P.applies(x) and Q.applies(x)):
            r.out_of_domain += 1
            continue
        p, q = bool(P.predicate(x)), bool(Q.predicate(x))
        if p and q:
            r.common += 1
        elif p and not q:
            r.divergence += 1
            if len(r.divergence_witnesses) < max_witness:
                r.divergence_witnesses.append(x)
        elif q and not p:
            r.dominance += 1
            if len(r.dominance_witnesses) < max_witness:
                r.dominance_witnesses.append(x)
        else:
            r.neither += 1
    return r


VERDICT_KEYS = ("p_strict_contains_q", "q_strict_contains_p",
                "parallel", "equivalent", "disjoint")


def verdict_key(r: DiffResult) -> str:
    """Four quadrants → stable criterion key. The cross-language/cross-wording contract:
    the wording is translated into English, the key is not.

    The same key set as `expect.verdict` in casestudy/port's claims.json.
    """
    if r.divergence and not r.dominance:
        return "p_strict_contains_q"
    if r.dominance and not r.divergence:
        return "q_strict_contains_p"
    if r.divergence and r.dominance:
        return "parallel"
    if r.common:
        return "equivalent"
    return "disjoint"


def verdict(r: DiffResult, P: Claim, Q: Claim) -> str:
    """Human-readable verdict text. The criterion lives in verdict_key; this is presentation only."""
    key = verdict_key(r)
    if key == "p_strict_contains_q":
        return f"{P.name} strictly contains {Q.name}"
    if key == "q_strict_contains_p":
        return f"{Q.name} strictly contains {P.name} ({Q.name} has {r.dominance} extra point(s))"
    if key == "parallel":
        return (f"Parallel: neither contains the other ({P.name} has {r.divergence} unique point(s), "
                f"{Q.name} has {r.dominance} unique point(s))")
    if key == "equivalent":
        return "Equivalent over the comparison domain"
    return "Disjoint over the comparison domain"


def antiforgery_line(claims: Iterable[Any]) -> str:
    """The "attestation tier" aggregate line. The tier is a verified/unverified
    binary criterion; this is presentation only: aggregate into one line to avoid
    label fatigue (per-item labels get switched off like wallpaper), mark
    git-object positively, give self-attested an upgrade path (labels must be
    actionable), and list unknown tiers explicitly."""
    counts: Dict[str, int] = {}
    for c in claims:
        k = getattr(c, "source_kind", "self-attested")
        counts[k] = counts.get(k, 0) + 1
    parts = []
    if counts.get("git-object"):
        parts.append(f"git-object {counts['git-object']} (external anchor declared; verify with provenance.verify)")
    if counts.get("self-attested"):
        parts.append(f"self-attested {counts['self-attested']} ({SELF_ATTESTED_HINT})")
    for k in sorted(counts):
        if k not in SOURCE_KINDS:
            parts.append(f"{k} {counts[k]} (unknown tier, listed explicitly)")
    return "[Attestation tiers] " + ("; ".join(parts) if parts else "no accounts")


def render(P: Claim, Q: Claim, r: DiffResult, *,
           p_label: str = "P", q_label: str = "Q",
           meaning_divergence: str = "the region where P is stronger",
           meaning_dominance: str = "⚠️ the region where Q is stronger") -> str:
    """Render the report. meaning_* lets the caller inject **domain semantics** —
    the only outlet of a domain-agnostic core."""
    L = []
    add = L.append
    BAR = "=" * 74

    add(BAR)
    add(f"breakingdiff report  |  {P.name}   vs   {Q.name}")
    add(BAR)

    add("[Provenance binding]")
    for lab, C in ((p_label, P), (q_label, Q)):
        add(f"  {lab} source: {C.source}")
        add(f"  {lab} quote: {C.quote}")
        # mark each git-object positively; self-attested does not spam per item, it only enters the aggregate line at the end
        if C.source_kind == "git-object":
            add(f"  {lab} external anchor: git-object {C.source_obj}")

    add("")
    add("[Source self-test]")
    for C, lab in ((P, p_label), (Q, q_label)):
        ok, tot, fails = C.run_source_tests()
        add(f"  {lab}: " + ("no usable source examples (0 tests)" if tot == 0
                            else f"{ok}/{tot} " + ("passed" if not fails else "failed")))
        if C.reading_variants:
            d = C.run_reading_discrimination()
            add(f"      interpretations: {len(C.reading_variants)}; distinguishing points: {len(d)}"
                + ("" if d else "  ⚠️ zero discriminating power"))

    add("")
    add("[Comparison domain]")
    add(f"  {p_label} domain: {P.domain_note}")
    add(f"  {q_label} domain: {Q.domain_note}")
    add(f"  out-of-domain skips: {r.out_of_domain}")

    add("")
    add("[Four quadrants]")
    add(f"  {'Quadrant':<24}{'Count':>8}{'Share':>9}")
    add("  " + "-" * 42)
    add(f"  {'common      P∧Q':<24}{r.common:>8}{r.pct(r.common):>8.1f}%")
    add(f"  {'divergence  P∧¬Q':<24}{r.divergence:>8}{r.pct(r.divergence):>8.1f}%")
    add(f"  {'dominance  ¬P∧Q':<24}{r.dominance:>8}{r.pct(r.dominance):>8.1f}%")
    add(f"  {'neither     ¬P∧¬Q':<24}{r.neither:>8}{r.pct(r.neither):>8.1f}%")
    add("  " + "-" * 42)
    add(f"  {'total (comparison domain)':<24}{r.total:>8}")

    add("")
    add("[Witnesses]")
    add(f"  divergence witnesses: " + (" ".join(map(str, r.divergence_witnesses)) or "(none)"))
    add(f"  dominance witnesses: " + (" ".join(map(str, r.dominance_witnesses)) or "(none)"))

    if r.divergence:
        add("")
        add(f"  ▸ divergence = {meaning_divergence}")
    if r.dominance:
        add("")
        add("  " + "!" * 68)
        add(f"  ⚠️  dominance warning: {r.dominance} point(s): {meaning_dominance}")
        add("      Divergence ≠ better. \"Different\" only means this is another account; it does not mean it is better.")
        add("  " + "!" * 68)

    add("")
    add(f"[Verdict]  {verdict(r, P, Q)}")
    add("")
    add(antiforgery_line([P, Q]))
    add(BAR)
    return "\n".join(L)


# ─── N-account generalization: verdict-vector classification (the pairwise four quadrants are the N=2 special case) ───
# Two things pairwise comparison cannot catch: cross-version regression (v3 dropped a point v1 had, and neither adjacent pair reports it)
# and outliers with attribution (n−1 true, 1 false; the one to question is that single false). That is why compare_n exists.

@dataclass
class NWayResult:
    names: List[str]
    all_true: int = 0
    all_false: int = 0
    split: int = 0
    outliers: Dict[int, int] = field(default_factory=dict)   # account index -> outlier points (all the others true, it alone false)
    pioneers: Dict[int, int] = field(default_factory=dict)   # account index -> pioneer points (all the others false, it alone true)
    split_witnesses: List[Any] = field(default_factory=list)
    ratchet_total: int = 0
    ratchet_witnesses: List[Tuple[int, int, Any]] = field(default_factory=list)  # (old j, new k, witness point)
    ratchet_trusted: bool = True   # whether direction is fixed by order_key (False = list order only)
    anchor_name: Optional[str] = None
    out_of_domain: int = 0
    total: int = 0
    anchor: Optional[int] = None
    max_witness: int = 8

    def pct(self, n: int) -> float:
        return 100.0 * n / self.total if self.total else 0.0


def compare_n(claims: List[Claim], domain: Iterable[Any], *,
              chain: bool = False, anchor: Optional[int] = None,
              order_key: Optional[Callable[[int, Claim], Any]] = None,
              max_witness: int = 8) -> NWayResult:
    """Point-by-point differential over N ≥ 2 accounts. With chain=True, additionally run the ratchet check:
    for every pair j<k (j old, k new), a point where v_j is true and v_k is false counts as a ratchet violation — the old version had it, the new version dropped it.

    order_key: the ratchet direction is fixed by it, not by list position.
    Its signature is `(index, Claim) -> comparable value`; the caller re-sorts ascending by it.
    With it, even if the caller passes [v3, v1, v2] out of order, you still get the correct
    "v1 → v3" direction instead of treating v3 as the newest.

    Without it, list order is taken as time order, and ratchet_trusted=False is set and marked in
    the report: the order comes from the caller and this tool cannot verify it. If the ratchet
    semantics ("the old version had it, the new version dropped it") are reversed, the whole
    conclusion flips while the readout still looks completely normal — more dangerous than a zero
    readout — so it must be marked explicitly, never silently assumed that list order is time order.

    Why pass the index: sorted(key=...) passes only the element; a caller writing
    `lambda c: c.version` from intuition is fine, but `lambda i, c: ...` raises TypeError.
    Passing the index explicitly makes "I need positional information" part of the signature,
    so misuse shows up on the spot.
    """
    if len(claims) < 2:
        raise ValueError("compare_n needs at least two accounts")
    if anchor is not None and not 0 <= anchor < len(claims):
        raise ValueError(f"anchor={anchor} is outside the account range 0..{len(claims) - 1}")
    for c in claims:
        _guard(c)

    # Record anchor by "identity" before the index: claims may be re-sorted below,
    # and identity is how we find its new index afterwards.
    claims_anchor_identity = claims[anchor] if anchor is not None else None

    ratchet_trusted = order_key is not None
    if order_key is not None:
        # Sort by order_key only: when keys tie, Python's sorted keeps comparing the
        # elements themselves, and Claim holds an incomparable predicate function, so
        # sorting directly raises TypeError. Compute keys first, then sort by index
        # (Python's sort is stable, so equal keys keep the original order).
        keyed = [((order_key(i, c), i), c) for i, c in enumerate(claims)]
        keyed.sort(key=lambda pair: pair[0])
        claims = [c for _, c in keyed]
        # anchor records "the index the caller passed in", and must follow the account
        # after re-sorting; otherwise it silently anchors to another account — the
        # baseline is mislabeled while the report looks perfectly normal.
        if anchor is not None:
            anchor = claims.index(claims_anchor_identity)

    r = NWayResult(names=[c.name for c in claims], anchor=anchor,
                   max_witness=max_witness, ratchet_trusted=ratchet_trusted)
    r.anchor_name = claims[anchor].name if anchor is not None else None
    seen = [] if chain else None          # the ratchet check looks back at verdict vectors, so chain mode keeps them
    n = len(claims)
    for x in domain:
        if not all(c.applies(x) for c in claims):
            r.out_of_domain += 1
            continue
        v = [bool(c.predicate(x)) for c in claims]
        r.total += 1
        if chain:
            seen.append((x, v))
        t = sum(v)
        if t == n:
            r.all_true += 1
        elif t == 0:
            r.all_false += 1
        elif t == 1:
            i = v.index(True)
            r.pioneers[i] = r.pioneers.get(i, 0) + 1
        elif t == n - 1:
            i = v.index(False)
            r.outliers[i] = r.outliers.get(i, 0) + 1
        else:
            r.split += 1
            if len(r.split_witnesses) < max_witness:
                r.split_witnesses.append(x)
    if chain:
        for x, v in seen:
            for j in range(n):
                if not v[j]:
                    continue
                for k in range(j + 1, n):
                    if not v[k]:
                        r.ratchet_total += 1
                        if len(r.ratchet_witnesses) < max_witness:
                            r.ratchet_witnesses.append((j, k, x))
    return r


def render_n(claims: List[Claim], r: NWayResult, *,
             meaning_outlier: str = "outlier: this account is missing points all the other accounts cover (candidate suspect, not a verdict)",
             meaning_ratchet: str = "ratchet violation: the old version had it, the new version dropped it — a cross-version regression",
             meaning_split: str = "mixed shape: which account is right needs a human decision") -> str:
    """N-account report. meaning_* works as in render: the caller injects domain semantics."""
    L = []
    add = L.append
    BAR = "=" * 74
    n = len(r.names)
    title = "   vs   ".join(r.names)
    if r.anchor is not None:
        anchor_name = r.anchor_name or r.names[r.anchor]
        title += f"   (anchor: {anchor_name})"

    add(BAR)
    add(f"breakingdiff N-account report  |  {title}")
    add(BAR)

    add("[Provenance binding]")
    for C in claims:
        add(f"  {C.name} source: {C.source}")
        add(f"  {C.name} quote: {C.quote}")
        if C.source_kind == "git-object":
            add(f"  {C.name} external anchor: git-object {C.source_obj}")

    add("")
    add("[Source self-test]")
    for C in claims:
        ok, tot, fails = C.run_source_tests()
        add(f"  {C.name}: " + ("no usable source examples (0 tests)" if tot == 0
                              else f"{ok}/{tot} " + ("passed" if not fails else "failed")))
        if C.reading_variants:
            d = C.run_reading_discrimination()
            add(f"      interpretations: {len(C.reading_variants)}; distinguishing points: {len(d)}"
                + ("" if d else "  ⚠️ zero discriminating power"))

    add("")
    add(f"[Shape statistics]  {n} accounts, {r.total} points in the comparison domain")
    if not r.ratchet_trusted:
        add("  ⚠️ Order is not fixed by order_key; the caller's input order is treated as time order.")
        add("     The ratchet direction (\"the old version had it, the new version dropped it\") depends on this assumption;")
        add("     if list order is not time order, the direction of ratchet violations flips entirely while the readout still looks completely normal.")
        add("     To remove this uncertainty: compare_n(..., chain=True, order_key=<version/time ordering key>)")
    add(f"  {'Shape':<26}{'Count':>8}{'Share':>9}")
    add("  " + "-" * 46)
    add(f"  {'all_true':<26}{r.all_true:>8}{r.pct(r.all_true):>8.1f}%")
    add(f"  {'all_false':<26}{r.all_false:>8}{r.pct(r.all_false):>8.1f}%")
    add(f"  {'split':<26}{r.split:>8}{r.pct(r.split):>8.1f}%")
    for i, cnt in sorted(r.outliers.items()):
        add(f"  {'outlier ← ' + r.names[i]:<26}{cnt:>8}{r.pct(cnt):>8.1f}%")
    for i, cnt in sorted(r.pioneers.items()):
        add(f"  {'pioneer ← ' + r.names[i]:<26}{cnt:>8}{r.pct(cnt):>8.1f}%")
    add(f"  {'out_of_domain':<26}{r.out_of_domain:>8}")
    add("  " + "-" * 46)
    add(f"  Agreement ≠ correct: consistent readouts across same-source accounts are self-consistency, not cross-verification (P6)")

    if r.ratchet_total or r.split:
        add("")
        add("[Witnesses]")
        if r.ratchet_witnesses:
            add("  ratchet violations (old→new@point): " +
                "  ".join(f"{r.names[j]}→{r.names[k]}@{x}" for j, k, x in r.ratchet_witnesses))
            if r.ratchet_total > len(r.ratchet_witnesses):
                add(f"      … {r.ratchet_total} total, showing the first {len(r.ratchet_witnesses)}")
        if r.split_witnesses:
            add("  split witnesses: " + " ".join(map(str, r.split_witnesses)))

    if r.ratchet_total:
        add("")
        add("  " + "!" * 68)
        add(f"  ⚠️  {r.ratchet_total} ratchet violation(s): {meaning_ratchet}")
        add("      Adjacent pairwise diffs are blind to this kind of cross-version regression; trust the chain check for this readout.")
        if not r.ratchet_trusted:
            add("      ⚠️  Direction depends on list order (see the warning in the shape statistics section) and is not verified by order_key.")
        add("  " + "!" * 68)
    if r.outliers:
        add("")
        add(f"  ▸ {meaning_outlier}")
    if r.split:
        add(f"  ▸ {meaning_split}")

    add("")
    add(antiforgery_line(claims))
    add(BAR)
    return "\n".join(L)

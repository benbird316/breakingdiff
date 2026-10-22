# -*- coding: utf-8 -*-
"""
symbol_isolation red-first tests (2.3 static warning for production symbols shared by P/Q)
==========================================================
Frozen contract (this repository's refinement plan landing batch §2.3; see the
matching CHANGELOG.md entry):
  · at construction time, scan the P and Q predicates statically and extract the set
    of module-level symbols they call; a non-empty intersection → warning
    "predicates share symbol X; P6 independence is in doubt";
  · AST + dis two tracks: when source is available, use ast to parse the Name.id /
    Attribute.attr of Call.func; when source is unavailable, degrade to dis over
    LOAD_GLOBAL / LOAD_ATTR (PEP 552: a pure-dis single track goes silent because
    opcode names change across versions, so the degraded track must stay alive and
    reconcilable);
  · the builtin allowlist is exempt automatically: pure utility functions such as
    sorted / len / isinstance are not a same-source suspicion; any other shared
    symbol needs an explicit exemption with a registered reason;
  · not a hard block: a shared symbol is not the same source, so record but do not
    block.

Warning blocking semantics (established in an earlier batch, account carried over):
  the repository has no warning/severity tiering precedent (breakingdiff.py has zero
  warning machinery; coverage_guard/delivery_gate all raise). The contract's "warning
  level" lands as an explicit data state: the warning is a field in the return value
  (the warnings tuple); it raises nothing and blocks nothing, and the same Claim pair
  then goes through compare as usual.

Predicate shape (grounded in real code):
  Claim.predicate / Claim.applies are both Callable[[Any], bool] (breakingdiff.py
  L40-41); in production the most common shapes are lambda (the receipt_test.py
  mk_pair precedent) and a module-level def (the predicate_alignment test
  precedent). The contract's "predicate" = Claim.predicate (applies is the
  applicability-domain decision and is outside this contract's scan surface).

Test contract (the API shape the implementation must obey, frozen by this test; the
module lands at scripts/symbol_isolation.py, and the construction-time wiring is
called by the implementation at the Claim construction point):

    from symbol_isolation import BUILTIN_EXEMPT, check_symbol_isolation, scan_predicate

    scan = scan_predicate(fn: Callable) -> SymbolScan
      · scan.symbols : a symbol set that tests may inspect ("x" in scan.symbols)
      · scan.track   : "ast" (source available) | "dis" (degraded), honestly reports which track ran
    rep = check_symbol_isolation(P: Claim, Q: Claim, *, exemptions=None) -> report
      · rep.warnings : one text per effective shared symbol, with the symbol name and
                        the "P6" anchor; an empty tuple when nothing effective is shared
      · rep.shared   : the raw symbol intersection outside the allowlist (ascending) —
                        the audit surface before exemption; exemption/allowlist only
                        affect warnings, they do not erase the intersection record
      · rep.scans    : {"P": SymbolScan, "Q": SymbolScan} (for Claim.predicate)
      · rep.exempted : the (symbol, reason) pairs that actually triggered exemption
                        (the exemption action is visible for lookup)
      · exemptions   : Mapping[symbol, reason]; empty/None/whitespace-only reason → ValueError
                        (an empty-reason exemption is indistinguishable from "forgot to
                        write a reason", so it is refused loudly — the same discipline as
                        Claim construction's "an unknown tier that can be constructed is
                        a false report")
      · BUILTIN_EXEMPT : frozenset[str], covering at least {"sorted", "len", "isinstance"}

Account decisions (frozen by this test; the implementation aligns to them):
  1. Attribute call shape: when Call.func is an ast.Attribute, extract the .attr name
     (obj.method() → "method"). The same-source suspicion anchors on the called name —
     two predicates calling a same-named method is the signal, and whether the sources
     are really the same goes to a human for adjudication (a warning does not hard
     block). The AST track does not extract the carrier name (the obj name is not the
     name of Call.func).
  2. The dis track extracts names from LOAD_GLOBAL / LOAD_ATTR, including non-call
     references — dis cannot tell "reference" from "call", so report conservatively and
     let explicit exemptions backstop it; therefore the AST and dis symbol sets are not
     required to match item by item, only to each catch the target symbol.
  3. Staticness: a scan must not execute the predicate. Several fixtures in this test
     deliberately call undefined symbols — an implementation that executes the
     predicate dies with NameError at once, and the red cause then points at a
     violation of static semantics.
  4. A missing exemption reason fails loudly; builtin allowlisted symbols never enter
     rep.shared and never warn.

This file is a red-first test: scripts/symbol_isolation.py did not exist yet, and
every test except the fixture self-check goes explicitly red with NotImplementedError
(each red cause maps to a contract clause, see each case's docstring). Once the
implementation lands, the guard stops applying automatically and the assertions take
real effect — no always-true placeholder anywhere.

No pytest dependency. Usage: python symbol_isolation_test.py
"""
import inspect
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from breakingdiff import Claim, compare

try:
    from symbol_isolation import (BUILTIN_EXEMPT, check_symbol_isolation,
                                  scan_predicate)
except ImportError:
    BUILTIN_EXEMPT = frozenset()        # red-first phase: the implementation module does not exist yet
    check_symbol_isolation = None
    scan_predicate = None


def _require_impl():
    """Red-first guard: go explicitly red when the module is missing; the cause is
    "not implemented" rather than an ImportError crashing the whole file — each
    test's red cause maps to its own contract clause. Once the implementation lands,
    this guard stops applying automatically."""
    if check_symbol_isolation is None:
        raise NotImplementedError(
            "symbol_isolation.check_symbol_isolation is not implemented "
            "(2.3 static warning for production symbols shared by P/Q, red-first phase)")


class raises:
    """Minimal context manager: a stand-in for pytest.raises (same as receipt_test.py)."""

    def __init__(self, exc):
        self.exc, self.value = exc, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"expected {self.exc.__name__} to be raised, but nothing was")
        self.value = ev
        return issubclass(et, self.exc)


# ── fixtures ────────────────────────────────────────────────────
# Apart from exec_probe/wiring_probe, the probe symbols called inside the predicate
# bodies are not defined at module level: static scanning does not need them to
# exist, and if the implementation executes the predicate, NameError is direct
# evidence of violating static semantics (account decision 3).

def _p_with_shared(x):
    return static_probe_shared(x) > 0


def _q_with_shared(x):
    return static_probe_shared(x) < 9


def _p_unique(x):
    return probe_only_p(x) > 0


def _q_unique(x):
    return probe_only_q(x) < 9


def _p_exempt(x):
    return exempt_probe(x) is not None


def _q_exempt(x):
    return exempt_probe(x) == exempt_probe(x)


def _p_builtins(x):
    return len(str(sorted(x))) > 1 and isinstance(x, (list, tuple))


def _q_builtins(x):
    return len(str(sorted(x))) >= 1 and isinstance(x, (list, tuple))


class _AttrCarrier:
    def isolate_attr_method(self, x):
        return x is not None


_ATTR_CARRIER = _AttrCarrier()


def _p_attr_call(x):
    return _ATTR_CARRIER.isolate_attr_method(x)


def _q_attr_call(x):
    return bool(_ATTR_CARRIER.isolate_attr_method(x))


def exec_probe(v):
    return v


def _p_exec_shared(x):
    return exec_probe(x) > 0


def _q_exec_shared(x):
    return exec_probe(x) < 9


def wiring_probe(v):
    return v is not None


def _make_nosource_pair():
    """compile+exec a predicate pair whose co_filename points at a nonexistent file —
    inspect cannot get the source, which triggers the dis degraded track. Do not put
    the probe names into ns: defining a function body does not resolve names (lazy),
    and the scan must not execute it either."""
    src = (
        "def p_nosource(x):\n"
        "    return dis_probe_helper(x) and _NOS_CARRIER.attr_probe_method(x)\n"
        "\n"
        "def q_nosource(x):\n"
        "    return dis_probe_helper(x) is not None\n"
    )
    code = compile(src, "<nosource-symbol-isolation-probe>", "exec")
    ns = {"__name__": "nosource_symbol_probe"}
    exec(code, ns)
    return ns["p_nosource"], ns["q_nosource"]


def _mk_claim(name, pred):
    return Claim(name=name, predicate=pred, applies=lambda x: x is not None,
                 domain_note="symbol isolation fixture", source="tests/fixture",
                 quote="shared-symbol predicate fixture")


def _mk_pair(p_pred, q_pred):
    return _mk_claim("P side", p_pred), _mk_claim("Q side", q_pred)


def _mk_lambda_claims():
    # Independent lambda assignment lines: inspect.getsource takes the whole line,
    # which ast can parse (no other call is mixed into that line).
    p_pred = lambda x: wiring_probe(x)
    q_pred = lambda x: wiring_probe(x) is not None
    return _mk_claim("P wiring", p_pred), _mk_claim("Q wiring", q_pred)


# ── fixture self-check (green first) ────────────────────────────────────────

def test_fixture_probe_sourced_and_sourceless():
    """Green first (fixture self-check): the control-state infrastructure for the
    two-track tests — the def fixtures really do have source and the exec-compiled
    fixture really does not. A distorted fixture would turn the later two-track
    assertions into "passing for the wrong reason"; pin the fixtures true first."""
    src = inspect.getsource(_p_with_shared)
    assert "static_probe_shared" in src, "def fixture source extraction is distorted: " + repr(src)
    p_nos, _ = _make_nosource_pair()
    try:
        inspect.getsource(p_nos)
    except OSError:
        pass
    else:
        raise AssertionError("the source-less fixture unexpectedly has source — the control state of the dis degraded test is distorted")


# ── shared detection (contract: non-empty intersection → warning) ────────────────────

def test_shared_module_symbol_is_detected_and_named():
    """Contract: extract the set of module-level symbols called by the P/Q predicates;
    a non-empty intersection → warning whose text contains the symbol name and the
    "P6 independence is in doubt" anchor. The predicates call undefined symbols: an
    implementation that executes the predicate dies with NameError (staticness)."""
    _require_impl()
    P, Q = _mk_pair(_p_with_shared, _q_with_shared)
    rep = check_symbol_isolation(P, Q)
    hit = [w for w in rep.warnings if "static_probe_shared" in w]
    assert hit, "shared symbol static_probe_shared was not warned: " + repr(rep.warnings)
    assert any("P6" in w for w in hit), "the warning text lacks the P6 independence anchor: " + repr(hit)


def test_no_shared_symbols_yields_no_warning():
    """Control state: the two sides call different symbols → no warning, no
    intersection. "The target state is true" is not "the target state is being
    tested"; detection semantics need a negative control to be complete."""
    _require_impl()
    P, Q = _mk_pair(_p_unique, _q_unique)
    rep = check_symbol_isolation(P, Q)
    assert rep.warnings == (), "warned with nothing shared: " + repr(rep.warnings)
    assert rep.shared == (), "recorded an intersection with nothing shared: " + repr(rep.shared)


# ── builtin allowlist (contract: pure utility functions are exempt automatically) ──────────────

def test_builtin_calls_are_auto_exempted():
    """Contract: pure utility functions such as sorted/len/isinstance called on both
    sides are not a same-source suspicion — no warning, no shared intersection. An
    implementation without the allowlist goes red here."""
    _require_impl()
    assert {"sorted", "len", "isinstance"} <= BUILTIN_EXEMPT, \
        "the allowlist lacks the pure utility functions named by the contract: " + repr(sorted(BUILTIN_EXEMPT))
    P, Q = _mk_pair(_p_builtins, _q_builtins)
    rep = check_symbol_isolation(P, Q)
    assert rep.warnings == (), "builtin sharing was falsely reported: " + repr(rep.warnings)
    assert rep.shared == (), "builtin symbols leaked into the shared intersection: " + repr(rep.shared)


# ── explicit exemption (contract: an exemption must register a reason and stay visible) ────────────────

def test_explicit_exemption_silences_and_stays_auditable():
    """Contract: any other shared symbol needs an explicit exemption with a registered
    reason, and the exemption action is visible for lookup. shared still records the
    raw intersection (the audit surface); warnings no longer contain the exempted
    symbol."""
    _require_impl()
    P, Q = _mk_pair(_p_exempt, _q_exempt)
    reason = "both sides are pure lookup functions; same source is harmless (reason registered)"
    rep = check_symbol_isolation(P, Q, exemptions={"exempt_probe": reason})
    assert rep.warnings == (), "an exempted symbol still warned: " + repr(rep.warnings)
    assert rep.shared == ("exempt_probe",), "the raw intersection must stay on record: " + repr(rep.shared)
    assert ("exempt_probe", reason) in rep.exempted, \
        "the exemption action is not visible: " + repr(rep.exempted)


def test_exemption_without_reason_is_refused():
    """Contract: exempt explicitly and register a reason. An empty-reason exemption is
    indistinguishable from "forgot to write a reason", so refuse it loudly — a silent
    pass would degrade the exemption list into a liability channel."""
    _require_impl()
    P, Q = _mk_pair(_p_exempt, _q_exempt)
    with raises(ValueError):
        check_symbol_isolation(P, Q, exemptions={"exempt_probe": ""})
    with raises(ValueError):
        check_symbol_isolation(P, Q, exemptions={"exempt_probe": None})
    with raises(ValueError):
        check_symbol_isolation(P, Q, exemptions={"exempt_probe": "   "})


# ── AST / dis two tracks (contract: the track is reconcilable and the degraded track must stay alive) ────────

def test_ast_track_used_when_source_available():
    """Contract: use the ast track when source is available. track must report
    honestly — if the two-track semantics are not explicit, there is no way to
    reconcile when the dis track goes silent."""
    _require_impl()
    scan = scan_predicate(_p_with_shared)
    assert scan.track == "ast", "a predicate with source did not take the ast track: " + repr(scan.track)
    assert "static_probe_shared" in scan.symbols, "the ast track lost the called symbol: " + repr(scan.symbols)
    P, Q = _mk_pair(_p_with_shared, _q_with_shared)
    rep = check_symbol_isolation(P, Q)
    assert rep.scans["P"].track == "ast" and rep.scans["Q"].track == "ast", \
        "the combined entry point's scan-track record is distorted: " + repr(rep.scans)


def test_dis_fallback_when_source_unavailable():
    """Contract: when source is unavailable, degrade to dis over LOAD_GLOBAL/LOAD_ATTR.
    An exec-compiled co_filename pointing at a nonexistent file triggers the
    degradation. attr_probe_method exists only on the P side — intersection semantics:
    a one-sided symbol never enters the warning (this stops "treating the union as the
    intersection")."""
    _require_impl()
    p_nos, q_nos = _make_nosource_pair()
    scan = scan_predicate(p_nos)
    assert scan.track == "dis", "an object without source did not degrade to dis: " + repr(scan.track)
    assert "dis_probe_helper" in scan.symbols, "the dis track lost LOAD_GLOBAL: " + repr(scan.symbols)
    assert "attr_probe_method" in scan.symbols, "the dis track lost LOAD_ATTR: " + repr(scan.symbols)
    P, Q = _mk_pair(p_nos, q_nos)
    rep = check_symbol_isolation(P, Q)
    assert any("dis_probe_helper" in w for w in rep.warnings), \
        "the source-less pair's shared symbol was not warned: " + repr(rep.warnings)
    assert not any("attr_probe_method" in w for w in rep.warnings), \
        "a one-sided symbol must not enter the warning (intersection semantics): " + repr(rep.warnings)


def test_attribute_call_extracts_method_name():
    """Account decision 1: when Call.func is an Attribute, extract the .attr name; the
    AST track does not extract the carrier name. Both sides call the same-named
    method → the warning contains that method name."""
    _require_impl()
    scan = scan_predicate(_p_attr_call)
    assert "isolate_attr_method" in scan.symbols, "the ast track lost the attr name: " + repr(scan.symbols)
    assert "_ATTR_CARRIER" not in scan.symbols, \
        "the ast track only takes Call.func names; the carrier name does not count: " + repr(scan.symbols)
    P, Q = _mk_pair(_p_attr_call, _q_attr_call)
    rep = check_symbol_isolation(P, Q)
    assert any("isolate_attr_method" in w for w in rep.warnings), \
        "a same-named method call was not warned: " + repr(rep.warnings)


# ── not a hard block (contract: warning level = explicit data state, no exception, no block) ─

def test_warning_is_data_not_exception_and_flow_continues():
    """Contract: when a sharing warning exists, construction/comparison still complete
    as usual. First half: check raises nothing on a real shared pair; second half: the
    same Claim pair then compares normally — the warning is a data state, not an
    exception channel."""
    _require_impl()
    P, Q = _mk_pair(_p_exec_shared, _q_exec_shared)
    rep = check_symbol_isolation(P, Q)
    assert rep.warnings, "this case needs a real warning as its premise: " + repr(rep.warnings)
    r = compare(P, Q, (3, 1, 2))
    assert r.total == 3, "the compare main flow was interrupted while a warning existed"


# ── construction-time wiring (contract: takes the Claim construction point's product as input) ───────────

def test_construction_wiring_accepts_real_claims_with_lambdas():
    """Construction-time wiring: the entry point accepts real Claims. lambda is the
    most common predicate shape in production (the receipt_test.py mk_pair precedent);
    it must be scannable and its sharing detectable."""
    _require_impl()
    P, Q = _mk_lambda_claims()
    rep = check_symbol_isolation(P, Q)
    assert any("wiring_probe" in w for w in rep.warnings), \
        "the lambda predicate's shared symbol was not warned: " + repr(rep.warnings)
    assert rep.scans["P"].track == "ast", "a lambda with source did not take the ast track"


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

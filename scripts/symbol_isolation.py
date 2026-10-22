# -*- coding: utf-8 -*-
"""
symbol_isolation — static warning for production symbols shared by P/Q (2.3, warning level)
==============================================================
P6 requires the accounts behind the two claims to come from independent sources, and
until now that relied on people remembering. At construction time this module scans
the P and Q predicates statically: it extracts the symbol names each one calls and
intersects them; a non-allowlisted symbol in the intersection raises one warning.
A shared symbol is not the same source (both may call a pure utility function), so
the module records but does not block — the warning is a field in the return value,
the same Claim pair goes through compare as usual, and a human decides whether the
sources are the same.

The scan is purely static: it reads source or bytecode, and never executes the
predicates. Symbols referenced inside a predicate body may be undefined; only
executing them would show that we scanned the wrong thing.

Two-track basis (PEP 552): when source is available, use ast and read the Name.id /
Attribute.attr of Call.func; when it is not (exec-compiled artifacts and the like),
degrade to dis over the names of LOAD_GLOBAL / LOAD_ATTR. A pure-dis single track
goes silent because of pyc nondeterminism and opcode names changing across versions,
so the degraded track must stay alive too, and the track field reports honestly which
track ran, so the choice can be reconciled.

The builtin allowlist is exempt automatically: interpreter-level pure utility
functions such as sorted/len/isinstance are called by everyone and are not a
same-source suspicion. Any other shared symbol must be exempted explicitly with a
reason — an exemption with an empty reason is indistinguishable from "forgot to write
a reason", so it is refused loudly.
"""
import ast
import builtins
import dis
import inspect
import textwrap
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from breakingdiff import Claim

# Interpreter-level pure utility functions (builtin exception names included): both
# predicates calling them is not a same-source suspicion. Take every name in the
# builtins module directly — a hand-copied list cannot keep up with interpreter
# evolution.
BUILTIN_EXEMPT = frozenset(dir(builtins))

# Load-class opcodes extracted by the dis track; argval is the symbol name.
# LOAD_METHOD only exists in 3.11 and earlier (method calls merged into LOAD_ATTR
# from 3.12 on); collect both generations so no method call is missed.
_NAME_OPCODES = frozenset({"LOAD_GLOBAL", "LOAD_ATTR", "LOAD_METHOD"})


@dataclass(frozen=True)
class SymbolScan:
    symbols: frozenset   # the set of symbol names found
    track: str           # "ast" (source available) | "dis" (degraded), reported honestly


@dataclass(frozen=True)
class IsolationReport:
    warnings: tuple      # one text per effective shared symbol, with the symbol name and the P6 anchor
    shared: tuple        # the raw non-allowlisted intersection (ascending) — the audit surface before exemption
    scans: dict          # {"P": SymbolScan, "Q": SymbolScan} (for predicate)
    exempted: tuple      # the (symbol, reason) pairs that actually triggered exemption


def _scan_ast(fn: Callable) -> SymbolScan:
    """Primary track when source exists: parse the names of Call.func in the source.
    An Attribute call takes the .attr name (obj.method() is recorded as method) —
    the same-source suspicion anchors on the called name, not the carrier name, so
    the carrier is not taken. getsource of a lambda inside a function body carries
    indentation, so dedent before parse; otherwise IndentationError would push a
    predicate that does have source down to the dis track."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    symbols = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            symbols.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            symbols.add(node.func.attr)
    return SymbolScan(frozenset(symbols), "ast")


def _scan_dis(fn: Callable) -> SymbolScan:
    """Degraded track when source is missing: scan bytecode instructions that load a
    name. dis cannot tell a "reference" from a "call", so non-call references are
    recorded conservatively; over-reporting is caught by explicit exemptions."""
    symbols = set()
    for instr in dis.get_instructions(fn):
        if instr.opname in _NAME_OPCODES and isinstance(instr.argval, str):
            symbols.add(instr.argval)
    return SymbolScan(frozenset(symbols), "dis")


def scan_predicate(fn: Callable) -> SymbolScan:
    """Statically scan the set of symbols a single predicate callable invokes. Does
    not execute the predicate."""
    try:
        return _scan_ast(fn)
    except (OSError, TypeError, SyntaxError):
        return _scan_dis(fn)


def check_symbol_isolation(P: Claim, Q: Claim, *,
                           exemptions: Optional[Mapping[str, str]] = None
                           ) -> IsolationReport:
    """Construction-time wiring: warn on symbols shared by a Claim pair's predicates.

    exemptions is a "symbol -> reason" mapping; an empty/None/whitespace-only reason
    → ValueError (a silent pass would degrade the exemption list into a liability
    channel). Allowlisted symbols never enter the intersection and never warn;
    explicit exemptions only suppress warnings, shared still records the raw
    intersection, and the exemption action stays visible in exempted for lookup.
    """
    reason_by_symbol = dict(exemptions) if exemptions else {}
    for symbol, reason in reason_by_symbol.items():
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                f"the exemption reason for shared symbol {symbol!r} is empty: an "
                "exemption with an empty reason is indistinguishable from "
                "\"forgot to write a reason\"; either write the reason or do not exempt")

    scans = {"P": scan_predicate(P.predicate),
             "Q": scan_predicate(Q.predicate)}
    shared = sorted((scans["P"].symbols & scans["Q"].symbols)
                    - BUILTIN_EXEMPT)
    exempted = tuple((s, reason_by_symbol[s])
                     for s in shared if s in reason_by_symbol)
    warnings = tuple(f"predicates share symbol {s}; P6 independence is in doubt"
                     for s in shared if s not in reason_by_symbol)
    return IsolationReport(warnings, tuple(shared), scans, exempted)

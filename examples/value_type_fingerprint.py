# -*- coding: utf-8 -*-
"""
Worked example · value-layer type fingerprint
==============================================================================
Scenario: two snapshots of one config; a key's value is still legal and the file
still parses, but the value's **type** changed from bool to int. No parser raises
on this — it is classic silent drift.

Approach: write "the value type of this key is the same across both versions" as a
real Claim, with a verbatim quote, a source self-test drawn from the quote, and
two interpretations; the core runs the three gates first, then computes the four
quadrants.

One of the two claims passes and one is rejected, deliberately:
  · (a) type fingerprint → passes the gates. The distinguishing point is
    cartFailure.off, bool → int.
  · (c) value-set shape → fails the discrimination gate. In this corpus, every
    flag whose value set changed also changed its cardinality and its variant
    names, so the claim and the two interpretations agree everywhere. The lesson:
    "syntactically registrable" also requires an instance in the corpus that
    separates it from a close interpretation.

Corpus: data/otel-2025-01.json and data/otel-2026-10.json, taken from the flagd
config of opentelemetry-demo; both are real commit snapshots, nothing hand-made.

Usage: python value_type_fingerprint.py
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
from breakingdiff import Claim, SourceTestError, compare, render

F_OLD, F_NEW = 'otel-2025-01.json', 'otel-2026-10.json'
SHA_OLD, SHA_NEW = '0c7c104a97', '258466eede'
SRC = ("open-telemetry/opentelemetry-demo src/flagd/demo.flagd.json "
       f"@{SHA_OLD} and @{SHA_NEW}")
# Verbatim from the 2025-01 cartFailure / kafkaQueueProblems block (the script
# checks that it really occurs in the source text)
QUOTE_TYPE = '"variants": {\n        "on": true,\n        "off": false\n      },'
QUOTE_SHAPE = '"variants": {\n        "on": 100,\n        "off": 0\n      },'


def _read(fn):
    with open(os.path.join(HERE, 'data', fn), encoding='utf-8') as f:
        return f.read()


RAW = {fn: _read(fn) for fn in (F_OLD, F_NEW)}
DOC = {fn: json.loads(text)['flags'] for fn, text in RAW.items()}
OLD, NEW = F_OLD, F_NEW


def fingerprint(v):
    """Type identity from the consumer's point of view. bool must be checked before
    int — that is exactly why this claim holds."""
    if v == '<ABSENT>':
        return 'absent'
    if isinstance(v, bool):
        return 'bool'
    if isinstance(v, int):
        return 'int'
    if isinstance(v, float):
        return 'float'
    if isinstance(v, str):
        return 'str'
    if v is None:
        return 'null'
    return type(v).__name__


def _val(fn, flag, variant):
    return DOC[fn].get(flag, {}).get('variants', {}).get(variant, '<ABSENT>')


def _variants(fn, flag):
    return DOC[fn].get(flag, {}).get('variants') or {}


def _vset(fn, flag):
    return frozenset(repr(v) for v in _variants(fn, flag).values())


COMMON = sorted({(f, v) for f in set(DOC[OLD]) & set(DOC[NEW])
                 for v in set(_variants(OLD, f)) & set(_variants(NEW, f))})
COMMON_SET = set(COMMON)
COMMON_FLAGS = sorted(set(DOC[OLD]) & set(DOC[NEW]))
ALL_KEYS = sorted({(f, v) for fn in (OLD, NEW) for f in DOC[fn]
                   for v in _variants(fn, f)})


def make_type_claim(fingerprint=None):
    """A factory rather than a constant: the fingerprint function is injectable, so
    the test can mutate "break the protection" as mutation evidence."""
    fp = fingerprint or globals()['fingerprint']

    def consistent(p, _fp=fp):
        return _fp(_val(OLD, *p)) == _fp(_val(NEW, *p))

    variants = (
        Claim(name="reading: values are equal (Python ==)",
              predicate=lambda p: _val(OLD, *p) == _val(NEW, *p),
              applies=lambda p: p in COMMON_SET,
              domain_note="same domain as the claim (the interpretation only changes the formalization)",
              source=SRC, quote=QUOTE_TYPE, quote_source=RAW[OLD]),
        Claim(name="reading: repr values are equal",
              predicate=lambda p: repr(_val(OLD, *p)) == repr(_val(NEW, *p)),
              applies=lambda p: p in COMMON_SET,
              domain_note="same domain as the claim",
              source=SRC, quote=QUOTE_TYPE, quote_source=RAW[OLD]),
    )
    return Claim(
        name="P the value type is the same in both versions",
        predicate=consistent,
        applies=lambda p: p in COMMON_SET,
        domain_note=f"(flag, variant) keys present in both versions, {len(COMMON)} in total",
        source=SRC, quote=QUOTE_TYPE, quote_source=RAW[OLD],
        source_tests=(
            (("cartFailure", "off"), False),        # false -> 0
            (("kafkaQueueProblems", "off"), True),  # 0 -> 0
            (("paymentFailure", "off"), True),      # same type
        ),
        reading_variants=variants,
    )


BASE_KEYS = Claim(
    name="Q the key exists in both versions",
    predicate=lambda p: p in COMMON_SET,
    applies=lambda p: True,
    domain_note="union of the two versions' keys",
    source=SRC, quote=QUOTE_TYPE, quote_source=RAW[OLD],
)


def make_shape_claim():
    variants = (
        Claim(name="reading: compare cardinality only",
              predicate=lambda f: len(_vset(OLD, f)) == len(_vset(NEW, f)),
              applies=lambda f: f in set(COMMON_FLAGS),
              domain_note="same domain as the claim",
              source=SRC, quote=QUOTE_SHAPE, quote_source=RAW[OLD]),
        Claim(name="reading: compare the set of variant names only",
              predicate=lambda f: set(_variants(OLD, f)) == set(_variants(NEW, f)),
              applies=lambda f: f in set(COMMON_FLAGS),
              domain_note="same domain as the claim",
              source=SRC, quote=QUOTE_SHAPE, quote_source=RAW[OLD]),
    )
    return Claim(
        name="P the flag's value set is the same in both versions",
        predicate=lambda f: _vset(OLD, f) == _vset(NEW, f),
        applies=lambda f: f in set(COMMON_FLAGS),
        domain_note=f"flags present in both versions, {len(COMMON_FLAGS)} in total",
        source=SRC, quote=QUOTE_SHAPE, quote_source=RAW[OLD],
        source_tests=(
            ("cartFailure", False),
            ("kafkaQueueProblems", False),
            ("paymentFailure", True),
        ),
        reading_variants=variants,
    )


BASE_FLAGS = Claim(
    name="Q the flag exists in both versions",
    predicate=lambda f: f in set(COMMON_FLAGS),
    applies=lambda f: True,
    domain_note="union of the two versions' flags",
    source=SRC, quote=QUOTE_SHAPE, quote_source=RAW[OLD],
)


def quote_check():
    print("#" * 74)
    print("# Mechanical check: does the quote occur verbatim in the source file (provenance is verifiable)")
    print("#" * 74)
    for q, fn in ((QUOTE_TYPE, OLD), (QUOTE_SHAPE, OLD)):
        print(f"  {str(q in RAW[fn]):<6} {q!r}")
    print()


def run_type():
    print("#" * 74)
    print("# (a) type fingerprint: a real Claim passes the three gates")
    print("#" * 74)
    claim = make_type_claim()
    ok, tot, fails = claim.run_source_tests()
    print(f"  source self-test {ok}/{tot}  " + ("passed" if not fails else f"failed {fails}"))
    disc = claim.run_reading_discrimination()
    print(f"  interpretations: {len(claim.reading_variants)}; distinguishing points: {len(disc)} {disc}")
    print()
    r = compare(claim, BASE_KEYS, ALL_KEYS, max_witness=40)
    print(render(claim, BASE_KEYS, r,
                 p_label="type-fingerprint claim", q_label="existence baseline",
                 meaning_divergence="(cannot happen: the claim implies the baseline)",
                 meaning_dominance="⚠️ present in both versions, but the type fingerprint changed — silent drift"))
    return r


def run_shape():
    print()
    print("#" * 74)
    print("# (c) value-set shape: the gate rejects it as expected")
    print("#" * 74)
    claim = make_shape_claim()
    ok, tot, fails = claim.run_source_tests()
    print(f"  source self-test {ok}/{tot}  " + ("passed" if not fails else f"failed {fails}"))
    try:
        compare(claim, BASE_FLAGS, COMMON_FLAGS, max_witness=40)
    except SourceTestError as e:
        print(f"  gate rejected: {e}")
    print()
    print("  Why this is not a bug: in the three flagd snapshot pairs, only")
    print("  cartFailure (2->7) and kafkaQueueProblems (2->4) changed their value set,")
    print("  and both changed cardinality and variant names at once, so the claim and")
    print("  the two interpretations agree everywhere. To let this tier pass the gate,")
    print("  the corpus needs an instance with \"same cardinality, different set\" or")
    print("  \"renamed without changing values\" —")
    print("  the JSON Schema domain has one (see the equal-cardinality, different-set")
    print("  shape in the §2 table of the plan), flagd does not. That is exactly why")
    print("  \"a worked example that really runs\" has to run first.")


def main():
    print()
    quote_check()
    run_type()
    run_shape()
    print()


if __name__ == '__main__':
    main()

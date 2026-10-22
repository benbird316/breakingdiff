# -*- coding: utf-8 -*-
"""Port-layer case: the Python reference implementation.

Read `claims.json`, turn each claim spec into a real `breakingdiff.Claim`, run it
through the repository core for the four quadrants, then assert that the readout matches
`expect`. This is the baseline of the three implementations: the Go / Rust ports are
equivalent as long as their readouts match it point by point.

Usage:
    python reference.py            # human-readable readout + assertions
    python reference.py --json     # machine-readable result (test_port.py compares it with the other two)
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from breakingdiff import Claim, compare, verdict, verdict_key  # noqa: E402

SPEC_PATH = os.path.join(HERE, 'claims.json')

VERDICT_KEYS = {
    'parallel': 'parallel',
    'equivalent': 'equivalent',
    'p_strict_contains_q': 'p_strict_contains_q',
    'q_strict_contains_p': 'q_strict_contains_p',
    'disjoint': 'disjoint',
}


class SpecError(ValueError):
    """claims.json does not match the contract this implementation understands."""


def _eval_op(op, point):
    """Operator evaluation: four operators are all of it — enough to express the
    decision chain, no general expression language needed."""
    kind = op['op']
    if kind == 'always':
        return True
    value = point[op['field']]
    if kind == 'ge':
        return value >= op['value']
    if kind == 'gt':
        return value > op['value']
    if kind == 'band':
        return op['lo'] <= value < op['hi']
    raise SpecError(f"unknown operator {kind!r} (a claim spec may only use always/ge/gt/band)")


def _build_claim(spec):
    def predicate(point):
        return _eval_op(spec['predicate'], point)

    def applies(point):
        return _eval_op(spec['applies'], point)

    source_tests = tuple(
        (case['point'], bool(case['expected']))
        for case in spec.get('source_tests', ())
    )
    return Claim(
        name=spec['name'],
        predicate=predicate,
        applies=applies,
        domain_note='n in [0, 24]',
        source=spec['source'],
        quote=spec['quote'],
        source_tests=source_tests,
    )


def _witness_values(items):
    """Project witness points uniformly onto the n value: cross-language comparison
    must not depend on the serialized shape of a parameter point."""
    return [point['n'] for point in items]


def run(spec):
    results = []
    for pair in spec['pairs']:
        P = _build_claim(pair['P'])
        Q = _build_claim(pair['Q'])
        r = compare(P, Q, spec['domain'])
        results.append({
            'id': pair['id'],
            'common': r.common,
            'divergence': r.divergence,
            'dominance': r.dominance,
            'neither': r.neither,
            'out_of_domain': r.out_of_domain,
            'verdict': verdict_key(r),
            'divergence_witness': _witness_values(r.divergence_witnesses),
            'dominance_witness': _witness_values(r.dominance_witnesses),
            'rendered': verdict(r, P, Q),
        })
    return results


def compare_against_expect(spec, results):
    """Return the list of mismatches; an empty list = the readout matches expect item by item.

    Only contract keys are compared: `rendered` does not enter reconciliation — the
    wording is not the contract (one of this case's teaching points).
    """
    diffs = []
    for pair, got in zip(spec['pairs'], results):
        want = pair['expect']
        for key in ('common', 'divergence', 'dominance', 'neither',
                    'out_of_domain', 'verdict'):
            if got[key] != want[key]:
                diffs.append(f"{pair['id']}.{key}: expected {want[key]!r}, got {got[key]!r}")
        for key in ('divergence_witness', 'dominance_witness'):
            if got[key] != want[key]:
                diffs.append(f"{pair['id']}.{key}: expected {want[key]!r}, got {got[key]!r}")
    return diffs


def main(argv):
    with open(SPEC_PATH, encoding='utf-8') as f:
        spec = json.load(f)

    results = run(spec)
    if '--json' in argv:
        payload = {
            'claim_spec': 'claims.json',
            'results': [{k: v for k, v in r.items() if k != 'rendered'} for r in results],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0

    diffs = compare_against_expect(spec, results)
    for r in results:
        print(f"[{r['id']}] common={r['common']} divergence={r['divergence']} "
              f"dominance={r['dominance']} neither={r['neither']} "
              f"out_of_domain={r['out_of_domain']} verdict={r['verdict']}")
        print(f"        rendered: {r['rendered']}")
    if diffs:
        print("\nMismatches with expect:", *[f"\n  - {d}" for d in diffs], sep='')
        return 1
    print(f"\nReference implementation matches claims.json expect item by item ({len(results)} pairs)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

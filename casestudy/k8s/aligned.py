# -*- coding: utf-8 -*-
"""Aligned case · Kubernetes API cross-version drift (the quiet zone, P3).

The proposition of this case is not "the tool counts things". It is:

    **On an existence baseline, a removal lands in the DIVERGENCE column, not
    the dominance column — the product column is a function of the baseline,
    not of the data.**

Every other case in `casestudy/` teaches how to write a claim. This one teaches
how to read a quadrant, and it is the only case in the portfolio that sits in
the programming domain.

Setup
-----
Two official OpenAPI snapshots, unmodified: release-1.28 and release-1.31 of
kubernetes/kubernetes. Parameter space = one request dimension
`(path, method, param_name)`, where an operation with no body/path/query
parameters contributes one point at `param_name = ""`. Methods are restricted
to the seven HTTP verbs; anything else in a swagger `paths` object is not an
operation and is skipped.

Claims
------
    P  "this dimension exists in 1.28"        (old account)
    Q  "this dimension exists in 1.31"        (new account)

Read the quadrants with P as the old account and you get:

    common      both versions have it
    divergence  only 1.28 has it  ← **the removal list. The breaking changes.**
    dominance   only 1.31 has it  ← the addition list
    neither     neither has it    ← structurally 0 here; the union covers everything

★ "The destructive-change column" is therefore `divergence`, and that is the
opposite of the intuition the four-quadrant vocabulary creates. Swap the
baseline (P = new, Q = old) and the same 193 points move to dominance. Nothing
about the data changed — only which side you called the old one. A tool that
reports only the dominance column as "the product" gets the direction backwards
on this whole class of change.

The second account in this file is the type fingerprint, and it exists to
reproduce a **zero hit**: on 727 common parameter dimensions, not one value type
changed between the two specs. See TEACHING-k8s.md §3 for why that is the
expected result and what it costs.

Run: python aligned.py
"""
import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_FILE, NEW_FILE = "k8s-1.28.json", "k8s-1.31.json"
METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
PARAM_IN = ("path", "query", "body", "formData")
DIMENSION_COUNT = 2049  # |A∪B| = 1499 common + 193 only-old + 357 only-new


def _find_root():
    """Search upward for breakingdiff.py — no hard-coded depth, so the directory
    can be moved without changing the failure mode."""
    cur = HERE
    while True:
        if os.path.isfile(os.path.join(cur, "scripts", "breakingdiff.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit(
                "[FATAL] cannot find scripts/breakingdiff.py walking upward. "
                "This case must run inside the breakingdiff repository.")
        cur = parent


_ROOT = _find_root()
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from breakingdiff import Claim, SourceTestError, compare, render  # noqa: E402

SRC = ("kubernetes/kubernetes api/openapi-spec/swagger.json "
       "@release-1.28 and @release-1.31 (official tags, unmodified)")


def _read(fn):
    with open(os.path.join(HERE, fn), encoding="utf-8") as f:
        return f.read()


def _specs():
    return {OLD_FILE: _read(OLD_FILE), NEW_FILE: _read(NEW_FILE)}


def _dims(spec_text):
    """One request dimension -> ('op'|'param', declared type or None).

    Operation-level points carry the empty name and no type; parameter-level
    points carry the parameter name. Keeping the two kinds in one space is what
    lets removals and parameter removals be counted together — a removal is a
    removal whichever level it happened at.
    """
    paths = json.loads(spec_text).get("paths", {})
    out = {}
    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if method.lower() not in METHODS or not isinstance(op, dict):
                continue
            out[(path, method.lower(), "")] = ("op", None)
            for prm in op.get("parameters") or []:
                if isinstance(prm, dict) and prm.get("in") in PARAM_IN:
                    typ = prm.get("type") or (prm.get("schema") or {}).get("type")
                    out[(path, method.lower(), prm.get("name", ""))] = ("param", typ)
    return out


RAW = _specs()
OLD, NEW = _dims(RAW[OLD_FILE]), _dims(RAW[NEW_FILE])
COMMON = sorted(set(OLD) & set(NEW))
UNION = sorted(set(OLD) | set(NEW))
COMMON_SET = set(COMMON)

# A verbatim fragment from the old spec, checked at Claim construction time.
QUOTE = '"io.k8s.api.networking.v1alpha1.ClusterCIDR": {'


def fingerprint(v):
    """Consumer-side type identity. bool must precede int — Python equality trap."""
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if v is None:
        return "null"
    return type(v).__name__


def make_existence_claim(side=None):
    """Factory, not a constant: the mutation test injects a broken version."""
    acc = OLD if side is None else side
    return Claim(
        name="P the dimension exists in release-1.28",
        predicate=lambda p: p in set(acc),
        applies=lambda p: True,
        domain_note=f"union of both specs' request dimensions, {len(UNION)} points",
        source=SRC, quote=QUOTE, quote_source=RAW[OLD_FILE],
        source_tests=(
            (("/apis/flowcontrol.apiserver.k8s.io/v1beta2/", "get", ""), True),
            (("/apis/flowcontrol.apiserver.k8s.io/v1beta2/flowschemas", "delete", "dryRun"), True),
            (("/apis/networking.k8s.io/v1alpha1/", "get", ""), True),
        ),
    )


def make_existence_claim_new():
    return Claim(
        name="Q the dimension exists in release-1.31",
        predicate=lambda p: p in set(NEW),
        applies=lambda p: True,
        domain_note=f"union of both specs' request dimensions, {len(UNION)} points",
        source=SRC, quote=QUOTE, quote_source=RAW[OLD_FILE],
        source_tests=(
            (("/apis/flowcontrol.apiserver.k8s.io/v1beta2/", "get", ""), False),
            (("/apis/resource.k8s.io/v1alpha2/", "get", ""), False),
            (("/apis/networking.k8s.io/v1alpha1/", "get", ""), False),
        ),
    )


def make_type_claim(fp=None):
    """Type identity on the dimensions both specs share.

    Expected to score zero on both non-common columns — see TEACHING-k8s.md §3.
    That is not the engine failing; it is the criterion having no purchase in a
    strongly-typed contract domain.
    """
    f = fp or fingerprint

    def same(p):
        return f(OLD[p][1]) == f(NEW[p][1])

    variants = (
        Claim(name="reading: value equality",
              predicate=lambda p: OLD[p][1] == NEW[p][1],
              applies=lambda p: p in COMMON_SET,
              domain_note="looser form of the body",
              source=SRC, quote=QUOTE, quote_source=RAW[OLD_FILE]),
        Claim(name="reading: repr equality",
              predicate=lambda p: repr(OLD[p][1]) == repr(NEW[p][1]),
              applies=lambda p: p in COMMON_SET,
              domain_note="looser form of the body",
              source=SRC, quote=QUOTE, quote_source=RAW[OLD_FILE]),
    )
    return Claim(
        name="P the parameter type is unchanged between the two specs",
        predicate=same,
        applies=lambda p: p in COMMON_SET,
        domain_note=f"parameter dimensions common to both specs, {len(COMMON)} points",
        source=SRC, quote=QUOTE, quote_source=RAW[OLD_FILE],
        source_tests=(
            # Real common parameter dimensions, read off the corpus — a source test
            # point that does not exist raises KeyError instead of quietly passing.
            (("/api/v1/namespaces", "post", "dryRun"), True),
            (("/api/v1/namespaces", "post", "fieldValidation"), True),
            (("/apis/storage.k8s.io/v1/volumeattachments/{name}/status", "put", "body"), True),
        ),
        reading_variants=variants,
    )


TYPE_BASE = Claim(
    name="Q the dimension exists in both specs",
    predicate=lambda p: p in COMMON_SET,
    applies=lambda p: True,
    domain_note="the common-dimension set, used as the existence baseline",
    source=SRC, quote=QUOTE, quote_source=RAW[OLD_FILE],
)


def api_group(path):
    """The group segment of a request path — the axis an operator actually reads."""
    if "/apis/" in path:
        return path.split("/apis/")[1].split("/")[0]
    if "/api/" in path:
        return "core/" + path.split("/api/")[1].split("/")[0]
    return path


def removals_by_group():
    # p is a (path, method, param) dimension, so the group comes off p[0].
    # Measured 2026-10-21: handing the whole tuple to api_group() compiles, runs,
    # and then fails at the first format — `"/apis/" in <tuple>` tests tuple
    # membership, not substring, so it is always False and the group silently
    # degrades to the dimension itself.
    c = Counter(api_group(p[0]) for p in set(OLD) - set(NEW))
    return c.most_common()


def additions_by_group():
    c = Counter(api_group(p[0]) for p in set(NEW) - set(OLD))
    return c.most_common()


def quote_check():
    print("#" * 74)
    print("# provenance binding: is the quote verbatim inside the old spec?")
    print("#" * 74)
    print(f"  {str(QUOTE in RAW[OLD_FILE]):<6} {QUOTE!r}")
    print()


def run_existence():
    print("#" * 74)
    print("# (1) existence account — P = old spec, Q = new spec")
    print("#" * 74)
    P = make_existence_claim()
    Q = make_existence_claim_new()
    for C in (P, Q):
        ok, tot, fails = C.run_source_tests()
        print(f"  {C.name[:44]:<46} source tests {ok}/{tot}"
              + ("" if not fails else f"  FAILED {fails}"))
    print()
    r = compare(P, Q, UNION, max_witness=6)
    print(render(P, Q, r,
                 p_label="exists in 1.28",
                 q_label="exists in 1.31",
                 meaning_divergence=(
                     "★ ONLY 1.28 HAS IT — this is the breaking-change column. "
                     "A client that calls any of these gets 404 on 1.31+. The product "
                     "column sits in `divergence`, not `dominance`: P is the OLD account, "
                     "so 'still in the old one but not the new one' reads as P ∧ ¬Q."),
                 meaning_dominance=(
                     "ONLY 1.31 HAS IT — new surface, additive. Switch the two "
                     "accounts and this column becomes the removal list; the count "
                     "does not move, the label does.")))
    print()
    print(f"  union size {len(UNION)} (pinned constant {DIMENSION_COUNT})")
    print()
    print("  Removal list collapsed by API group — 193 points become rows a human acts on:")
    for g, n in removals_by_group():
        print(f"    {g:<50}{n}")
    print()
    print("  Additions collapsed by API group (the other column, for contrast):")
    for g, n in additions_by_group()[:5]:
        print(f"    {g:<50}{n}")
    return r


def run_type():
    print()
    print("#" * 74)
    print("# (2) type-fingerprint account — the gate REFUSES it, which is the finding")
    print("#" * 74)
    C = make_type_claim()
    ok, tot, fails = C.run_source_tests()
    disc = C.run_reading_discrimination()
    print(f"  source tests {ok}/{tot}; candidate readings {len(C.reading_variants)}, "
          f"discriminating points {len(disc)} {disc}")
    print()
    print("  The discrimination gate rejects this claim, and the rejection IS the result:")
    print()
    try:
        compare(C, TYPE_BASE, COMMON, max_witness=6)
    except SourceTestError as e:
        print(f"  BLOCKED  {e}")
    print()
    print("  What that means, precisely. The body (type fingerprint) and both looser")
    print("  readings (value equality, repr equality) return the same value at every")
    print("  test point — because in this corpus no parameter's declared type ever")
    print("  changes between the two specs. A test set on which nothing can separate the")
    print("  body from its own approximations **cannot detect formalization drift**, so")
    print("  the gate treats the source tests as invalid rather than passing them.")
    print()
    print("  ★ This is strictly louder than a zero readout. '0 differences' invites")
    print("    'the criterion found nothing, fine'. 'The claim could not be certified'")
    print("    forces the next question: is this criterion applicable to this domain at")
    print("    all? Answer: no. A strongly-typed contract domain puts the type in the")
    print("    contract, so it does not drift quietly.")
    print()
    n_param = sum(1 for p in COMMON if OLD[p][0] == "param")
    print(f"  For scale (plain enumeration, NOT a tool readout): {n_param} parameter-level")
    print("  dimensions are common to both specs, and the declared type is string in")
    print(f"  {sum(1 for p in COMMON if OLD[p][0] == 'param' and OLD[p][1] == 'string')} of them,")
    print(f"  undeclared in {sum(1 for p in COMMON if OLD[p][0] == 'param' and OLD[p][1] is None)}.")
    print("  Two values only — which is the mechanical reason no reading can separate.")
    print()
    print("  This reproduces the 'zero hits in a strongly-typed contract domain' entry in")
    print("  references/writing-claims.md's criterion-selection table — but derives it")
    print("  from a gate refusal instead of asserting it from a count.")
    return None


def main():
    print()
    quote_check()
    run_existence()
    run_type()
    print()


if __name__ == "__main__":
    main()

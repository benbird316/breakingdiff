# How to write rules for a new domain

This page answers one question: given a new corpus in hand (two versions of a configuration, two versions of a spec, two implementations), how do you write, from scratch, a Claim that passes the gates. The worked example is examples/value_type_fingerprint.py; read it alongside and run it as you go.

## Contents

- Step 1: fix the parameter space and flatten one way of reading
- Step 2: take the corpus and record provenance
- Step 3: quote verbatim from the source text
- Step 4: write the predicate and the self-test
- Step 5: run the gates and fix what the errors point at
- Step 6: mutation evidence (including: two hard disciplines for mutation tests / both directions: over-blocking must be tested too)
- Conventions for writing a new case
- Four-quadrant entry semantics
- Criterion selection (measured across 6 domain pairs, small sample, not a statistical conclusion)
- Dimension discipline: different things cannot go into the same set for comparison
- Common ways to die

## Step 1: fix the parameter space and flatten one way of reading

First answer "what unit does this claim act on". For flagd it is `(flag, variant)`, for K8s it is `(operation, path, method)`, and for a decision class it is the input itself. A coarse parameter space leaks divergence (an account at the surface level missed 1 of 3 real divergences); a fine one makes the predicate hard to write.

Under cross-domain comparison, flatten every domain into the same shape: `group = params[:-1], item = params[-1], value = scalar`. The flattening code lives in the case's `_load()`; change two fields to plug in your own format.

## Step 2: take the corpus and record provenance

Use two real snapshots as the corpus, placed under `examples/<name>/data/`. Record three things as provenance: repository name, file path, commit hash (the `SRC` at the top of a case has this shape). The corpus snapshot must be preserved as-is — provenance checks and source-example self-tests both use it as the base.

## Step 3: quote verbatim from the source text

Open the old corpus and copy the passage to be claimed **including indentation and line breaks** (in the case, `QUOTE_TYPE` carries newlines and eight spaces of indentation). Compacted JSON and reordered fragments both make the verbatim check fail — the check runs mechanically at construction time:

```python
Claim(..., quote=QUOTE, quote_source=RAW[OLD])
```

`quote_source` takes the full source text. Without it only non-emptiness is checked, and a fabricated source text passes; the case convention is to always pass it.

## Step 4: write the predicate and the self-test

A predicate is an ordinary function; give `True`/`False` per claim semantics. Three things are not optional:

```python
Claim(
    name="P value type is consistent between the two versions",
    predicate=consistent,                # the body
    applies=lambda p: p in COMMON_SET,   # scope, usually only keys shared by both versions
    source=SRC, quote=QUOTE, quote_source=RAW[OLD],
    source_tests=((("cartFailure", "off"), False),
                  (("kafkaQueueProblems", "off"), True)),
    reading_variants=variants)
```

- **`source_tests` is a tuple of tuple pairs**. When a test point is itself a tuple, write `((("a", "b"), True),)` — one level of parentheses too few and `"a"` is split into single characters and passed into the predicate, with the symptom being a `TypeError` from a surge in argument count.
- **Do not hard-wire `applies`**. A type-fingerprint claim applies only to keys shared by both versions; new and old keys fall outside the domain, and only then is the four-quadrant account clean.
- **`reading_variants` needs at least two near-equivalent interpretations**. Value equality (`==`) and repr equality are the two common candidates. Their job is to serve as targets for the discriminating-power gate: if a near-equivalent interpretation has the same value as the body on every test point, the gate judges this self-test invalid. This is how the value-domain-shape variant was rejected in the case — not a bug: in that corpus every variable-value flag changed both cardinality and name at once, so no instance could separate the interpretations.

Python numeric equality has a trap: `False == 0` and `1 == True` are both true. When writing type checks, `bool` must come before `int`; the case's `fingerprint()` is a ready-made pattern.

## Step 5: run the gates and fix what the errors point at

```
from breakingdiff import compare, render
compare(P, Q, domain)      # three gates: two at construction time + source-example self-test at comparison time
```

| Error | Meaning | Fix |
|:--|:--|:--|
| `ProvenanceError: missing source/text` | source or quote is empty | fill it in |
| `ProvenanceError: quote is not in quote_source` | the excerpt is not verbatim | go back to the corpus and copy it verbatim again, including indentation and line breaks |
| `SourceTestError: source-example self-test` | some test point's expected value is wrong, or the predicate is wrong | check each expected value; expected values must come from the real corpus and cannot be picked by hand |
| `SourceTestError: the interpretation has no discriminating power` | a near-equivalent interpretation equals the body everywhere | change the candidate interpretation; or confirm the corpus truly has no separating instance, and switch criterion variant |

`source_tests=()` with no reading_variants — an existence baseline, say — cannot be bitten by any of the three gates: the gates verify that the self-evidence is self-consistent, not that the claim is true. A baseline holds because its own predicate computes it on the real domain.

## Step 6: mutation evidence

After writing a new criterion, **deliberately break** the protected behavior, run it once to see what form it goes red in (a raise? an under-report? at which point?), then write the assertion from the measurement. Do not assume from intuition that "breaking it only yields a silent under-report" — in the case's tests, the degenerate fingerprint actually raised at the source-example self-test, with two defense lines sounding at once, nothing like intuition. The injection point must be a point really consumed: changing a parameter nobody reads does not count as breaking.

### Two hard disciplines for mutation tests

Both were actually hit in this project, and both produced "looks protected, actually not".

#### ① In a multi-defense-line scenario, `assertRaises` is not enough

**You must check which defense line caught it; asserting "it raised" is not enough.**

Measured: the delivery gate added two zero-readout defenses (empty catalog, four-quadrant total of 0). After a mutation deleted the empty-catalog check, `raises(DeliveryError)` still went all green — the domain-skip check caught it, and **the defense line we meant to verify was not working at all**.

**Criterion: the test verifies "something blocked it", not "the defense line I had in mind blocked it" — with multiple checks these are two different things.**

```python
# ✗ anyone else catching it still goes green
with raises(DeliveryError):
    require_spec_alignment(spec)

# ✓ it must be this defense line that caught it
with raises(DeliveryError) as e:
    require_spec_alignment(spec)
assert "comparison domain is empty" in str(e.value)
```

One same-source variant: **an assertion that is not strong enough equals no assertion**. Measured: `assert poc_keys` (non-emptiness only) still went green after one item was deleted — two items remained and non-emptiness held. Write `assert len(poc_keys) == 3`.

**Criterion: ask "will this assertion go red when half of it is gone"; if not, it is not strong enough.**

#### ② "Not caught" has two possible causes

```
not caught  → ① the test has a hole
            → ② the mutation never took effect
```

**You must first confirm the mutation really took effect, then conclude that the test is inadequate.**

Measured: `str.replace` failed to match the catalog entry (a punctuation mark had been changed mid-way through the corpus), so the file never changed — yet the wrong conclusion "the test has a hole" was drawn. Switching to **deleting by exact line number** and retesting, the test went red correctly.

Practice: after mutating, read the file back to confirm the change took effect, or have the mutation script report "N replacements made"; **N=0 means the mutation never took effect**, and then "not caught" is not evidence.

### Both directions: over-blocking must be tested too

Breakage has more than one form. "A gate that is too loose" and "a gate that is too tight" are both bad:

- too loose → lets through what it should block (the two disciplines above cover this)
- too tight → blocks what it should let through. Measured: after writing "block divergence too" as a mutation, `test_divergence_does_not_block` went red at once

**An error in direction is as harmful as an error in amount** — a gate that dares not let anything through gets bypassed after two uses (see dimension discipline).

## Conventions for writing a new case

- One instance = `examples/<name>.py` + `examples/<name>_test.py`, with the corpus under `examples/data/`; follow the six steps above
- Write predicates as factory functions (e.g. `make_type_claim(fingerprint=None)`) so mutation tests can inject a broken implementation
- `bool` must be judged before `int` (the Python numeric equality trap: `False == 0`, `1 == True`)
- Provide at least two candidate interpretations (value equality and repr equality are the most common); failing the discriminating-power gate is not a bug — if the corpus cannot produce an instance, extend the corpus before registering

## Four-quadrant entry semantics

compare() decides each parameter point in two steps: first look at `applies` (whether the claim is defined at this parameter point); if either side is undefined, it falls out of domain and the predicate is not evaluated at all; only when both sides are defined does predicate truth enter the four quadrants (both true lands in common, no action needed). **"Absent" and "judged false" are two different things**: an item not in the catalog is absent; a predicate computing `False` is judged false.

| Quadrant | What input lands here | Suggested action for the consumer |
|:--|:--|:--|
| out_of_domain (out of domain) | either side has `applies=False` (typical cause: the P-side item is absent) | check whether the catalog misses it |
| dominance (dominance ¬P∧Q) | the P predicate is false (explicit `False`), Q true | add a test or change the spec (human adjudication) |
| neither (neither ¬P∧¬Q) | both predicates are false | run the predicate calibration self-check (`check_predicate_alignment`) to look for predicate distortion |
| divergence (divergence P∧¬Q) | P true, Q false | the test is finer than the spec, mostly hardening |

Out of domain does not count into `DiffResult.total` and does not enter the four-quadrant percentages — an omitted item only shows up on the "out-of-domain skips" line, and the four-quadrant readout stays clean. This is the other side of "do not hard-wire `applies`" from Step 4: narrow the scope and the missed items do not appear as failures; they simply disappear. neither has a ready mechanical treatment: before compare, run `check_predicate_alignment(P, Q, pre_point, post_point)` from `scripts/predicate_alignment.py` — give the Claim pair two calibration fixtures (a known pre-change state + a known post-change state); if the P and Q predicates judge **both fixtures false**, the thing the predicates are looking for is wholly misaligned with the data's two known states (typically after key-shape drift, the key-shape expectation did not follow), and it reports "predicate distortion" and blocks rather than landing in neither. One side false, one true is a normal differential signal; the calibration gate does not block it. Calibration points are not comparison-domain samples and do not enter the four-quadrant counts.

Similar design precedents: the wiretype spec marks `field-removed` as breaking and `field-added` as info, grading semantics by the direction of change; the ow library distinguishes `.absent` (absent = unchanged) from `.optional` (undefined is a legal value) for "may be missing", the same shape as "absent (out of domain) ≠ judged false (dominance)". Sources: wiretype ARCHITECTURE.md, ow on bestofjs

## Criterion selection (measured across 6 domain pairs, small sample, not a statistical conclusion)

| Criterion | Power | Boundary |
|:--|:--|:--|
| Type fingerprint | high precision | only effective in domains where the value type has freedom (zero hits in K8s/strongly typed contract domains) |
| Value equality `==` | nearly useless | a degraded version of the type fingerprint; on common points equality is close to a tautology, so compare repr or fold it into the fingerprint |
| Value-domain shape | broad coverage | low precision; description rewrites hit too |
| Key-name unit morphology | a denoised version of value-domain shape | hits only when the unit-word name changes |

Believe a "zero hits" conclusion only after the coverage diagnostics: empty-scalar rate, number of distinct values, most-common value distribution — print those three lines and true green and false green are distinguishable at a glance. In the K8s swagger, 2089/2916 parameters are `$ref`; without dereferencing you see only 827 inline parameters, all strings — a "zero change" produced by incomplete extraction does not count.

## Dimension discipline: different things cannot go into the same set for comparison

This is the same class of error that keeps recurring in this project; it has appeared three times:

| Occasion | Mixed comparison | Consequence |
|:--|:--|:--|
| `coverage_guard` | file paths vs commitment items | **100% gate noise**; every run judges out of bounds, and after two uses someone turns it off |
| `delivery_gate` | file → item vs item → four quadrants | a two-level structure collapses into one level, and dimension has nowhere to live |
| bootstrap catalog | PoC technique files vs test-assertion corpus | "the PoC mentions a word" is read as "a test asserts an item" |

**Criterion: do the elements of these two sets answer the same question?** `['src/auth.py']` and `['R1','R2']` — one is a location, one is a commitment; putting them into the same set for comparison necessarily produces noise.

**Once a gate makes noise, its fate is to be switched off**, and once it is off nobody looks at what it was blocking. So the substance of dimension discipline is: **noise is more fatal than under-reporting**; under-reporting at least leaves a trace.

The fix is usually to split into two levels with an explicit mapping in between:

```python
file_coverage: Dict[str, Sequence[str]]   # file → the items it touches
catalog: Sequence[str]                     # item → surface under test
```

## Common ways to die

- the corpus cannot produce an instance that "separates the body from a near-equivalent interpretation" → this criterion cannot be registered in this domain; extend the corpus first
- a key disappearing/appearing lands out of domain → additions and removals must be caught; write a separate pair of existence claims with the domain taken as the union of both versions (this count varies with the corpus; do not hard-wire it in the docs)
- an anonymous family hits with high repetition (the same pattern repeated N times) → hit concentration must report its denominator; don't count one finding as N
- a hand-copied reordered quote → the verbatim check blocks it at construction time; do not wait until compare to find out
- **two things of different dimension thrown into the same set** → 100% gate noise, more fatal than under-reporting (see dimension discipline)
- **with multiple defense lines, only `assertRaises` without checking the message** → a different defense line catching it keeps the test green
- **for "not caught" in mutation evidence, first check whether the mutation really took effect** → otherwise you draw the wrong conclusion "the test has a hole"

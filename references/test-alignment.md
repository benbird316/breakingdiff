# Test alignment scenarios

Normally you compare two snapshots of the same artifact. This scenario compares two "accounts" of the same tool:

- P claim account = the behavior the tests actually pin down
- Q contract account = the behavior the spec promises, or that consumers declare a dependency on

Re-read the four quadrants for this scenario:

| Quadrant | Reading |
|:--|:--|
| common P∧Q | the test pins it and the spec promises it — held |
| dominance ¬P∧Q | the spec promised it and the test does not hold it, **a coverage gap to fill** (this column is the product) |
| divergence P∧¬Q | the test pins it and the spec does not promise it, **the test is finer, mostly hardening**; delete it if it is too fine |
| neither ¬P∧¬Q | neither side cares |

The value of divergence is the opposite of the original scenario. There the four quadrants are equal and do not adjudicate who is right; here a test finer than the spec is an advantage — do not mechanically delete it as a "redundant constraint". The first version of the instance called it "a constraint the test added itself", which was wrong: the negative suggestion leads to wrongful deletion.

## Three hard disciplines

1. **Q must be frozen, and the file itself must be frozen.** "We won't change the spec this round" is a verbal agreement, and files are alive: change the spec next round and last round's readout changes with it. To really freeze, read a snapshot or record a hash; do not rely on "we agreed not to change it".

2. **Report proportions, not absolute numbers.** Measured: degrade Q to "promises everything" and dominance does not move (4 items), while divergence drops from 4 to 0. The meaning is that writing the spec a little wider and promising a few more items makes the gap "look covered" (items squeeze into common), while test coverage does not change by a single line. So you must report both "total items + dominance proportion" (e.g. 4/15 = 27%). Reporting only 4 lets Q's granularity manipulate you.

3. **Audit the catalog as seriously as the predicate.** The predicate goes into the real file to find the marker, and the marker must be verbatim so anyone can recompute; but the "item to marker" mapping is written in the code's catalog, and swapping a marker for an item changes the four quadrants. The catalog itself is a judge.

## Where Q comes from (ordered by evidence strength)

| Source | What it is | Strength | Cost / floor |
|:--|:--|:--|:--|
| Downstream call surface | sample N real downstreams and record the APIs/parameters actually called | first-hand | sampling bias; **call surface ≠ dependency semantics** |
| Real issues | bugs reported by consumers = behavior the tests do not cover but someone depends on | first-hand | few in number, need triage |
| Contract tests | the Pact family, dependencies declared by consumers | semi-ready-made | most libraries have none; covers only what is declared |
| Spec documents | promises in README/API docs | close to self-bootstrap | written by humans, not external |

**Floor**: the call surface only shows "what downstream calls", not "what semantics it depends on". A downstream calling `foo(x)` does not mean it depends on the return value at `x=0`. This is an innate precision loss that implementation cannot recover; say so in the report.

## Two uses, two trigger points

- Self-bootstrap (when changing code): Q = the spec frozen before this round, preventing "tests and implementation drift together".
- Real library (at delivery): Q = external consumers, preventing "tests all green but the behavior downstream receives changed".

One sentence for the common core: **the verification source must be independent of the party under test**. The criterion for finding Q is "find a Q that this round's author cannot change".

Recursive reminder: Q itself has an oracle gap. The bootstrap spec was written by a human/agent in a previous round, and a real library's consumers often cannot say what they depend on. The end point is always a human; do not treat Q as ultimate truth.

## Examples

`examples/test_alignment_bootstrap.py` is the bootstrap version: P = the assertions of this skill's test suite, Q = the commitments of SKILL.md. The four-quadrant readout changes as the catalog grows (15 items in the first version, 13 after removing two rot-prone numbers from the docs; measured 2026-10-16: 71 items, common 50, dominance 17/71 = 24%, divergence 4/71 = 6%, neither 0) — this count varies with the corpus; do not hard-wire it in the docs. The readout of record is the last line of `python test_alignment_bootstrap.py`.

Run: `cd examples && python test_alignment_bootstrap.py`

The real-library version (B) does not exist yet; to choose Q, see the table above: first capture the downstream call surface and real issues, flatten them into `{API name + parameter slot: shape}` in the same key space as the test assertions; dominance is then the review checklist.

## The code delivery gate (compare ⇄ gate)

`scripts/delivery_gate.py` turns this skill from "an agent uses it when it remembers to" into "a checkpoint that must be passed before delivery".

**A gate cannot be established by comparing before and after the refactor.** Both sides are written by the same agent, and agreement is only same-source self-consistency (it fails P6); such a gate gives a false green — **a false green is worse than no gate: it makes people think they verified**.

**So the gate changes opponents**: it does not compare "your own past", it compares "an independent source".

```
Q contract account = specs, contracts, type definitions, and actual consumer dependencies written by humans/upstream
P claim account = this change + the behavior the tests actually hold
dominance ¬P∧Q = the spec promised it, the tests do not hold it ← what delivery should block
divergence P∧¬Q = the test is finer than the spec (mostly hardening, no change needed)
```

In this comparison Q comes from humans/upstream and P from the agent, so **P6 holds**.

Usage (a project builds `bd_gate.py`):

```python
from delivery_gate import GateSpec, require_spec_alignment
require_spec_alignment(GateSpec(
    name="auth refactor",
    spec_claims=[...],    # each with a verbatim quote, checked at construction time
    test_claims=[...],
    catalog=[...],        # surface under test: the commitment items to compare this round
    changed_files=[...],  # files changed this round
    file_coverage={...},  # file → the items it touches (different dimension, do not mix)
))
```

### Three hard disciplines for the delivery gate

1. **Dominance > 0 fails.** The spec promised it and the tests do not hold it; the treatment is one of two (add a test / change the spec to say it is not a commitment), **decided by a human, the tool does not adjudicate**.
2. **Divergence does not block.** A test finer than the spec is usually hardening; turning a weakened spec into the shape of the test treats hardening as a defect.
3. **Out-of-domain skips > 0 fails.** If an item never entered the comparison domain, the readout is invalid for it — **A zero readout is not a pass.**

### Two-level coverage structure (dimension discipline)

```
file → item   file_coverage explicit mapping   (declaration completeness)
item → four quadrants  catalog                (surface under test completeness)
```

**A file path and a commitment item are two different things, and cannot go into the same set for comparison.** (For the consequence see the "Dimension discipline" section of writing-claims.md; for the incident log see `CHANGELOG.md`.)

Two kinds of non-registration are blocked separately, with separate wording: **a file not registered in `file_coverage`** = declaration missing; **the item is not in the catalog** = surface under test missing — both produce false greens, and the fixes differ.

### The delivery gate itself can go silently dead

Once it is changed to always pass, the report still prints, the format still matches, and it simply no longer blocks anything — **it disguises itself as a pass**. So `delivery_gate_test.py` uses mutation evidence to pin down "the gate was changed to always pass" and "the coverage gate was removed" separately.

### Coexisting with existing gates

- **Wiring A (a blocking gate)**: suits projects with no gate system; the delivery gate blocks directly before delivery.
- **Wiring B (merge into an existing gate)**: suits projects that already have a gate system; hanging another blocking gate on top only double-blocks noise, so merge P/Q into the existing full gate and file the differential readout as a QA record.

**Blocking-gate threshold: a differential readout with precision < 90% must not be used as a blocking gate**; it can only be filed.

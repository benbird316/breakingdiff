# breakingdiff

A domain-agnostic N-account claim differential engine. Write one executable claim for each of two (or more) accounts of the same artifact, mechanically compute their verdict vector at every parameter point, and report only divergence — it does not adjudicate right or wrong.

**Usage and rules live in [`SKILL.md`](SKILL.md)** — that is the file an agent reads to decide whether and how to use the tool.
This file is for **humans**: read it when you want to change the tool, add a new instance, or trace how it came to be.

`MIT` · version `1.0.0` · Python standard library only, no external dependencies.

---

## Why it looks like this: the core insight

Diff-detection tools are not scarce, but they all share one premise: **change raises an error**.
If the parser, the type checker, the compiler, and CI are all green, the change ships.

The real blank spot is on the other side: **the change is legal, raises nothing, and nobody stops it**.

```
The key is still there · the type is still int · the tests are still green — but the semantics have quietly changed
```

**No tool in the set this project was written against catches this kind of drift** — and that set is a premise, not a survey: the tools it sits next to all share one assumption, *change raises an error*, and the set is not enumerated here. If one exists that enumerates the other side, this section is wrong and the tool is unnecessary. Yet the shape is exactly what mechanical enumeration handles:
compress each of the two materials into one `parameter point → bool` claim, compare point by point,
and divergence becomes **one specific spot**, not a vague impression that "something is probably inconsistent".

**Divergence ≠ better.** This tool reports only where things differ.

**Agreement ≠ correct either.** Two accounts that agree at every point can both be wrong: a defect
they share is invisible to a diff. Divergence tells you *where to look*; it does not tell you which
side is right, and agreement tells you even less — only that this particular comparison found nothing.

**What counts as an account.** One rendition of the same artifact that someone could have shipped:
a release note, an implementation, an API snapshot, a dataset. Two accounts make a test only when
they are **independently produced** — if both sides come from the same source, a shared defect
cancels itself out and the diff reads clean. Whether each side must carry citable provenance is a
per-instance decision; the rule is P6 (independence) in [`SKILL.md`](SKILL.md), and
[`references/domain-mapping.md`](references/domain-mapping.md) shows what P6 looks like outside programming.

---

## Install and verify

The library is `scripts/` plus `examples/`: standard library only, a flat directory rather
than a package — modules import each other by bare name, so put `scripts/` on `PYTHONPATH`
instead of copying a single file out.

Verification needs a little more, in three corners only: `go` and `rustc` for
`casestudy/port`, `pyarrow` for 7 of `casestudy/malecns`'s 24 assertions, and a corpus for
four of the five case studies (`port` needs only the toolchain). Corpora are never committed —
they are fetched on demand and pinned by
SHA256 in their manifest, which is why a clone stays under 1MB of code:

| case study | corpus | fetch |
|---|---|---|
| `malecns` | two Feather tables, 56MB | `python fetch_corpus.py` |
| `llama` | llama.cpp release archive, 2.1GB | `python fetch_corpus.py` |
| `k8s` | two OpenAPI snapshots, 6MB | `python fetch_data.py` |
| `pdg` | PDG sqlite, 7MB | `python fetch_data.py` |
| `port` | none — needs `go` and `rustc` | — |

All fetch scripts run from inside their own case-study directory.

```bash
# one entry point runs everything — the same script backs the pre-commit hook and CI
python scripts/ci_gate.py                 # every test (28 files)
python scripts/ci_gate.py --list          # what would run, without running it
python scripts/ci_gate.py --only refs     # one file or group, while iterating

# enable the local gate once per clone — git cannot do this for you
git config core.hooksPath .githooks && chmod +x .githooks/pre-commit

# the reference gate and the version check (repo root; exit 0 is the only pass)
python scripts/refs_guard.py           # reference integrity: 0 red, 0 SKIP, 0 warn
python scripts/version_stamp.py check  # version has one source of truth

# the four examples as readouts rather than gates
python examples/value_type_fingerprint.py    # four quadrants 25/0/1/0
python examples/iteration_chain.py           # 3 ratchet violations
python examples/test_alignment_bootstrap.py  # bootstrap readout
python examples/forgery_poc.py               # all five forgery tricks pass
```

`ci_gate.py` discovers tests by name (`test_*.py` or `*_test.py`) rather than from a stored
list, so a new test is covered the moment it lands. A list drifts silently, and it already
had: a hand-written 27-file list was missing `examples/docaudit/test_docaudit.py`, one
directory deeper than its siblings. The same command backs the pre-commit hook and the
GitHub workflow, so a green local run and a green CI run executed the same set of files.

Measured 2026-10-22: 28/28 green in 39s with every corpus present, 20s on a fresh clone
without them (wall clock, one machine; a partial fetch lands in between — 32s with only
`malecns` present). A case-study test with no corpus takes its no-corpus path instead of failing,
which keeps a clone self-sufficient — and means CI cannot vouch for the corpus-anchored
assertions. Those only run where the corpus was fetched. The limit is stated rather than
papered over: a green CI badge is not evidence that the case studies still reconcile.

Three guards, three different jobs — they are not interchangeable:

| Guard | Owns |
|---|---|
| `refs_guard.py` | reference integrity: the `SKILL.md`→`references` links, orphan reconciliation, pointer form, pointer-promise fulfilment |
| `coverage_guard.py` | whether the surface under test was actually covered — the tier-three defense in ② below |
| `leak_guard.py` | residue in the files an agent reads: absolute paths, machine names, grading-side material |

`coverage_guard.py` is a library gate invoked from tests (`require_covered`) rather than a command,
which is why only `refs_guard.py` appears in the block above.

To run one example, run it from the repository root — `python examples/<name>.py` — rather than
copying it out: `value_type_fingerprint.py` reads shared fixtures from `examples/data/`, and
`forgery_poc.py` has no paired `_test.py`, so a single copied file reproduces neither.

---

## Directory layout

```
breakingdiff/
├── SKILL.md            ← rules and usage (the agent reads this on every trigger)
├── INDEX.md            ← file navigation: what each file is, when to read it
├── CHANGELOG.md        ← evidence: release record, mutation ledger, the failure behind each mechanism
├── README.md           ← this file: project positioning and design rationale
├── ORCHESTRATION.md    ← multi-agent rules that bind every batch run, not only the dispatcher
├── VERSION             ← single source of truth for the version (one-line semver)
├── LICENSE             ← MIT
├── scripts/            ← verdict, gate, and deployment modules (count per the scripts/ table in INDEX.md) + their mutation-evidence tests
├── examples/           ← runnable examples, the tests that pin them, and the docaudit claims fixture
├── casestudy/          ← 5 runnable case studies (pdg / llama / malecns / port / k8s) + 5 teaching docs + README (read on demand; entry point in that directory's README)
├── probes/             ← blind-run task sheets: cold-start usability acceptance for context-free agents (assets public, scoring material local)
└── references/         ← 8 on-demand method docs
```

Per-file "what it is · when to look" → [`INDEX.md`](INDEX.md).

### Choosing a case study: start from what you want to do, not from directory names

The five formal case studies sit in five different pit layers. Once you hit a row in the first column, read only the material that row points to:

| What you want to do | What to learn | Where to look | What it teaches |
|---|---|---|---|
| Write an account as claims, unsure how to choose P and Q | data-extraction layer | `casestudy/pdg/` + `TEACHING-pdg.md` | Of the four error modes, only the provenance one is blocked mechanically |
| Industrial evidence does not line up (release notes vs artifact), or the corpus is still missing | probe layer + ledger layer | `casestudy/llama/` + `TEACHING-llama.md` | The degenerate readout is **all zeros**, quieter than the data-extraction layer |
| Assertions keep going red although the data is fine | strength layer | `casestudy/malecns/` + `TEACHING-malecns.md` | Same data: bounded bands flag 12 points, point-value claims 2,720 — both are this tool's readout on a sampled grid, not bounds of the space; a 45.6M-synapse public connectome |
| Rewrite an implementation (Python→Rust/Go) and confirm behavior did not drift | port layer | `casestudy/port/` + `TEACHING-port.md` | `claims.json` is read by all three implementations; a wrong port's offset is predictable |
| Audit a cross-version API change and need to know what a client will stop being able to call | scope layer + quadrant reading | `casestudy/k8s/` + `TEACHING-k8s.md` | On an existence baseline the removals land in **divergence**; a criterion the domain cannot support is refused by the gate instead of reported as zero |

The full version (how to run, claim counts, which conclusion stops holding when the corpus or toolchain is absent) → [`casestudy/README.md`](casestudy/README.md).

### How the layering works: split by reader, not by content type

To decide whether a piece of content belongs in the main document, ask **who reads it, and when**:

| File | Reader | Holds | When read |
|---|---|---|---|
| `SKILL.md` | agent | rules and usage | every trigger |
| `INDEX.md` | people looking for a file (agents and humans) | file navigation | when you don't know which file to read |
| `references/` | people writing an instance | methods and criterion selection | before writing a new rule |
| `CHANGELOG.md` | people verifying | evidence: failures, mutation ledger | when tracing why a decision was made |
| `README.md` | people taking over | project positioning and design rationale | on first contact |

**Why the length of SKILL.md counts as a cost**: the agent reads the whole file on every trigger,
so its size converts directly into trigger precision. `INDEX.md`, `README.md`, and `CHANGELOG.md` are read only at specific moments,
so content placed there carries no marginal cost.

So the split is not decided by "is this section important" — the directory tree is important,
but it is **only used when you are looking for a file**; an agent deciding how to use the tool does not need it.

### Repository layout conventions

Organized into the three buckets of the agentskills spec: `scripts/` (executable), `examples/` + `references/` (read on demand).
`examples/` is the extra directory the spec allows; every example is self-contained.

**No MCP**: in practice, shipping the same core as both an MCP bundle and a skill bundle raises mis-selection —
two entry points describing the same thing leave the trigger unsure which one to take.

---

## Core API

```python
# core: diffing and rendering
from breakingdiff import Claim, compare, render, compare_n, render_n

r = compare(P, Q, domain)              # compute the four quadrants point by point
print(render(P, Q, r, meaning_dominance="..."))   # domain semantics are injected by the caller

rn = compare_n(claims, domain, chain=True, order_key=lambda i, c: c.version)

# surface-under-test coverage gate (decide before reading out)
from coverage_guard import require_covered
require_covered(changed_markers, covered_markers, what="this round's changes")
# uncovered → CoverageError

# code-delivery gate
from delivery_gate import GateSpec, require_spec_alignment
require_spec_alignment(GateSpec(
    name="auth refactor",
    spec_claims=[...], test_claims=[...],
    catalog=[...], changed_files=[...], file_coverage={...},
))
```

For the three anti-self-deception pieces (receipt / provenance / blind write), see the SKILL.md sections "Receipt vs. delivery", "Provenance tiers",
and "Blind-written expectations"; for the field contract see `references/receipt-format.md`.

**The core holds no domain knowledge** — what a "dominance" quadrant means in terms of risk is injected by the caller through
`meaning_*=`. That is why it works across four domains: programming, engineering, theory, and research.

---

## Three design principles (why it ended up like this)

### ① Gates raise instead of warn

> A zero readout must turn into a non-zero cost, or it gets read as a pass anyway.

Most "quality checks" are built as warnings; the warnings then scroll past every day and nobody reads them.
Build it as a raise, and it becomes a real gate.

### ② A gate can also fail silently, in three tiers

| Tier | Form | Existing defense |
|:--|:--|:--|
| One | Under-reporting inside the surface under test | There is a readout, but the readout is too small |
| Two | Incomplete extraction manufactures a false green | "Run coverage diagnostics first" was proposed; no action was specified |
| Three | **The surface under test is missing entirely** | `coverage_guard.py` — a zero readout is the most dangerous, because it looks like "everything is normal" |

In practice this tool has failed: the 2026-10-12 incident (tier three) and several on 2026-10-15 (a new section was left out of the catalog,
and the gate went red on the spot). **The record is in `CHANGELOG.md`.**

### ③ Every gate exception must be verifiable verbatim

An exemption mechanism is the easiest place for "semantic guessing" to hide. So:
`exempt` uses **verbatim equality**, and any relaxation must be written explicitly as `PREFIX:` —
substring matching would let `exempt=['coverage']` silently swallow `coverage gate notes`.

## Why these mechanisms exist

| Real problem hit | Mechanism |
|---|---|
| After convergence landed, the old readout's semantics flipped and the same decision was redone in two batches | phase-transition recipe (`references/phase-transition.md`) |
| Predicate and actual state decoupled at the same time, making "distortion" and "a third shape" indistinguishable | dual calibration self-check (`scripts/predicate_alignment.py`) |
| Q calls the primitive under test to verify the primitive under test (same source, different author) | shared-symbol warning (`scripts/symbol_isolation.py`) |
| Re-anchoring the quote ledger is manual archaeology | re-anchor helper (alive / dead / suspected new site, `scripts/reanchor.py`) |
| Receipts needed their own runner, so nobody used them | thin pytest / main wrappers (each `*_test.py` runs directly) |
| Double interception noise under an existing gate system | gate within a gate (`SKILL.md` "Coexisting with an existing gate system") |

The evidence for each row is in the `CHANGELOG.md` release record, which names the file each mechanism is defined in (mechanisms only, never projects).

---

## When changing this tool

1. **Read `references/writing-claims.md` first** — six steps and you can write a valid instance
2. **After a change, run every test, not just the file you touched**
   — a change to `coverage_guard.py` moves the EXPECT values and the catalog of the bootstrap example
3. **A verdict-logic change must ship with mutation evidence** — break the behavior under protection and confirm the tests go red
   (test both directions too: too loose disguises itself as a pass, too tight can be bypassed)
4. **After changing SKILL.md, run `test_alignment_bootstrap.py`** — the coverage gate checks
   whether the new section landed inside the surface under test; going red is a designed failure, so follow the prompt and add it to the catalog or the exemption set

Three easy traps — with several lines of defense, check which one blocked it; for "not caught", first check whether the mutation took effect;
different dimensions never go into one set — are all in step six of `references/writing-claims.md`.

---

## License and status

MIT (see [`LICENSE`](LICENSE)). Version `1.0.0` (single source of truth = the root `VERSION`,
checked by `scripts/version_stamp.py check`).

Released tool; the core has no external dependencies and uses only the standard library.

**Where to ask.** This release has no issue tracker configured — it ships as an archive, so a
question arrives as a diff plus the gate output. If you are taking the project over, read
[`CHANGELOG.md`](CHANGELOG.md) first: it records which defense line was ever proven and which was
only written down.
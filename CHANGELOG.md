# Changelog

**Rules live in `SKILL.md`, methods in `references/`, evidence here.** Three
audiences: the agent reads the first on every trigger; anyone writing rules for
a new domain reads the second; anyone checking whether a defense line has ever
been proven reads this file.

The repository ships as one snapshot at 1.0.0. This file records what that
snapshot claims, and what has actually been measured behind each claim. It keeps
no development chronology: intermediate builds were never published.

---

## 1.0.0 (2026-10-22)

First public release.

### Core capabilities

- **N-account claim differential**: pairwise four-quadrant map (common /
  divergence / dominance / neither) plus multi-account outlier / pioneer /
  ratchet checks, each with live witnesses (which key, which entry).
- **Claim construction gate**: source-test self-check, discrimination across
  candidate interpretations, and predicate-distortion self-check (P and Q
  predicates against two calibration points; distortion blocks instead of
  falling into neither).
- **Coverage gate**: a change outside the parameter space raises — *a zero
  readout is not an approval*.
- **Delivery gate**: item-by-item reconciliation of spec/contract claims
  against what tests actually guard (P6: the two sources must be independent).
- **Receipt and blind-written expectations**: deterministic JSON receipt plus
  two tiers of reconciliation, with expectations written before readouts.
- **Provenance tiers**: `self-attested` / `git-object`, verified through
  verbatim quote matching and line-range comparison.

### Verification gate

- **One entry point**: `scripts/ci_gate.py` discovers tests by filename —
  prefixed `test_` or suffixed `_test` — anywhere under the root, and runs all of
  them. No stored list exists, so none can drift. The pre-commit hook and the
  GitHub workflow both call this one script, which is why "green locally" and
  "green in CI" mean the same set of files executed.
- **A gate that ran nothing exits 2, not 0**: zero discovered tests is a runtime
  error. A pattern typo or a checkout that dropped the tree would otherwise print
  a clean summary over an empty run.
- **Three exit tiers, the same as `receipt.py`**: 0 green, 1 gate red (block the
  commit), 2 the gate could not run. "Did not run" is not "ran red".
- **Measured 2026-10-22**: 28 test files, 28/28 green in 42s with every corpus
  present, 20s on a corpus-free tree. `pyarrow` is the only third-party package
  the suite touches, declared in `requirements.txt` with the measured versions as
  its anchor.
- **Line endings normalized to LF** (`.gitattributes`). Several tests compare
  output byte for byte, so an EOL difference between a Windows working tree and
  the Linux runner would turn a green local run red in CI with no code change.
  Before the file existed the tree held 19 CRLF / 71 LF / 1 mixed against an
  all-LF index. The suite happened to be EOL-insensitive at that moment (26/26 on
  a force-LF copy), so this is a guard against the next byte-exact test rather
  than a fix for a present failure — stated because a guard nobody can tell apart
  from a fix gets deleted the moment the "bug" stops reproducing.

### Five worked cases, five different pits

| Layer that breaks | Case | What the readout looks like when it does |
|---|---|---|
| data extraction (accounts not aligned) | `casestudy/pdg/` | 100% `all_true`, or entirely split |
| probe + ledger (evidence extracted wrong) | `casestudy/llama/` | all zeros — quieter than the layer above |
| strength (claim stronger than the data's own variation) | `casestudy/malecns/` | false red all over: true data read as bad data |
| port (implementation replaced, claim kept) | `casestudy/port/` | three readouts each self-consistent, diverging from each other |
| scope (surface under test smaller than the change) | `casestudy/k8s/` | a clean one-point readout, or a gate refusal instead of a number |

Running each one, its assertion count, and what stops holding when the corpus or
toolchain is absent → `casestudy/README.md`.

### Defense lines and mutation evidence

Counts below were recorded while each line was being built. Re-deriving one means
injecting the same mutations again; the test that locks each line sits beside it in
`scripts/*_test.py`. The count is a development record, the test is the lock.

| Defense line | Mutations that turned red (recorded) |
|---|---|
| `coverage_ratio` denominator includes gaps | 3 |
| `exempt` matches verbatim only | 2 |
| `ratchet_trusted` direction flag | 2 |
| `anchor` follows reordering | 1 |
| Delivery-gate decision sequence (six checks: empty domain / out-of-domain / dominance / divergence / coverage / empty catalog) | 13 |
| PoC corpus-layer exclusion (dimension discipline) | 1 |
| Verification section carries no hard-coded counts | 2 |
| Ratchet direction promise | 1 (weak mutation) |

### Failures that produced the mechanisms

Each row is a failure this repository actually hit, and the mechanism that now
stands where it did. The rule is in `SKILL.md`; the method is in `references/`.

| Failure observed | Mechanism | Defined in |
|---|---|---|
| After a convergence landed, the earlier readout's semantics had flipped, and one decision was made twice in two batches | phase-transition recipe: red-first baseline turned into a regression lock | `references/phase-transition.md` |
| Predicate and actual state decoupled at the same moment, so "predicate distortion" and "a third shape" could not be told apart | dual-calibration self-check: all-false blocks instead of landing in neither | `scripts/predicate_alignment.py` |
| Q called the primitive under test to verify that primitive — same source, different author | static shared-symbol warning; recorded, does not block | `scripts/symbol_isolation.py` |
| Re-anchoring the quote ledger after a spec revision was manual archaeology | three-state re-anchor report: alive / dead / suspect new site | `scripts/reanchor.py` |
| Receipts had no runner, so nobody produced them | thin wrappers; every `*_test.py` runs directly as a script | `scripts/`, `examples/` |
| Two gate systems each vetoed the other's output until the signal was noise | gate within a gate | `SKILL.md`, "Coexisting with an existing gate system" |
| A warning-level check is unread after a week | raise instead of warn; the zero readout is the most dangerous shape | `scripts/coverage_guard.py` |
| The agent's own summary drifted from what was delivered | delivery gate: the claim and the guarded items are compared item by item | `scripts/delivery_gate.py` |
| Deliberate forgery can pass every gate | capability declaration table plus a working forgery PoC | `examples/forgery_poc.py` |

### Gate failures caught on this repository

| Incident | What happened | What it proves |
|---|---|---|
| Tier three, 2026-10-12 | A substantial `SKILL.md` rewrite left six preconditions, four domain scenarios and three exclusions outside the catalog; the four quadrants returned an unchanged `7/4/2/0`, and "no change" was read as "verified" | a zero readout is not an approval; the same day's fix also found the gate deriving the checked set from the catalog — the same source as the checked set, a tautology |
| Catalog omission, 2026-10-15 | A new section was left out of the catalog; the gate went red on the spot | the gate catches omission at the moment of the change, not at review time |
| Under-reporting, tier one | The assertion book read one test file, so assertions living in other files counted as gaps out of thin air | an incomplete P-side is a false red, not a smaller check |
| Doc contract vs. new gate, 2026-10-22 | Replacing the printed test list with a single entry point broke two checks in the same run: `trigger_conditions_test.py` still demanded every filename appear in README, and `refs_guard` read the glob written into `AGENTS.md` as a dead link (it cut `*_test.py` down to `_test.py`) | the gate caught the contradiction in the run that introduced it, before any commit. The doc assertion was rewritten to check the gate's real discovery instead of text matching — a behaviour check replacing a string check — and the glob became prose, because a filesystem-path check cannot be trusted against a wildcard |

### Key lessons (condensed)

- **Three-level silence is the most dangerous**: a zero readout looks like
  "everything is fine" — hence the coverage gate raises instead of warning.
- **A stale promise is worse than an absent sentence**: docs do not hard-code
  counts; the command list lives in README.
- **Quantities of different dimensions must not share one comparable set** —
  three occurrences during iteration.
- **Gates stop carelessness, not forgery**: the forgery PoC proves deliberate
  forgery can bypass them; their value is raising the cost of carelessness.
- **A test can pin a bug as the spec** — surface-locking mutations and
  red-first baselines are the countermeasure.

### Known limits at 1.0.0

- `casestudy/port` needs `go` and `rustc`. The Rust binary is built on demand;
  when the toolchain is missing the affected items are skipped and named.
- `casestudy/malecns` needs its two Feather files (fetch with `fetch_corpus.py`)
  and `pyarrow` for 7 of its 24 assertions. Without `pyarrow` those seven exit as
  a runtime error (exit 2), not as a red — an environment gap is reported as an
  environment gap.
- No test requires `pytest` or any other runner: every `*_test.py` runs as a plain
  script. The standard library covers all of them except the one `malecns`
  reconciliation path that imports `pyarrow` (see above).

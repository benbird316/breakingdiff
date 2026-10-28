# Changelog

**Rules live in `SKILL.md`, methods in `references/`, evidence here.** Three
audiences: the agent reads the first on every trigger; anyone writing rules for
a new domain reads the second; anyone checking whether a defense line has ever
been proven reads this file.

The repository ships as one snapshot. This file records what that snapshot
claims, and what has actually been measured behind each claim. It keeps no
build-by-build chronology: intermediate builds were never published. It does keep
a **mechanism-level incident ledger** (below): what failed, the readout that
showed it, how many mutations went red, the fix, and the test that now locks the
fix. That ledger was reconstructed from pre-1.0 development notes — it is not
part of this repository's public commit history, and it claims no git provenance
there.

---

## 1.0.1 (2026-10-29)

Second public release: the first batch of fixes and curation after 1.0.0. No API was
removed — `compare`/`compare_n` still return on a zero domain for their consumers — but
the reading surface no longer reports a comparison that never happened.

### Zero-domain readouts, verdict wording, witness caps

- `DiffResult` gains `domain_total` (every parameter point handed over, skips included)
  and `in_domain` (points that entered the quadrant map; equal to `total`). When
  `in_domain == 0`, `render()` opens with a top banner naming the domain size and the
  out-of-domain count, and `verdict()` returns a dedicated "nothing was compared"
  wording instead of "disjoint over the comparison domain". It does not raise: the
  delivery gate, the forgery PoC and other consumers read the counts.
- `NWayResult` gains the same two fields; `render_n()` opens with a zero-domain banner
  that separates an empty parameter domain from an all-out-of-domain one — two causes,
  two fixes. `total` keeps its old meaning.
- All-false domain (P and Q false at every point): the human verdict now reads as
  equivalence on a double negative. `verdict_key()` is unchanged (`disjoint`), because
  the case studies key on that string as a cross-language contract.
- Witness truncation is announced — `… first N of M, K not listed` — for divergence and
  dominance witnesses and for N-way split witnesses. A capped list is a sample, not the
  column count.

### Gate-layer silent exemptions

- `coverage_guard.find_uncovered`: a `PREFIX:` with a blank suffix (empty, spaces, tabs,
  full-width space) now raises `ValueError` naming the raw declaration, at parse time —
  even with `changed=[]`. An empty prefix normalized to `""`, and `startswith("")`
  exempted every changed marker of the round.
- `delivery_gate.require_change_coverage`: the same refusal for a blank `PREFIX:`, and
  prefix matching is now normalized on both sides with the same `_norm` as
  `coverage_guard` (one source, so the two gates cannot drift). Exact exemptions stay
  verbatim.
- `coverage_guard.coverage_ratio`: duplicate changed items are collapsed verbatim,
  order-preserving, before the denominator — `["a","a","b"]` with `["a"]` covered is
  `1/2`, not `2/3`.
- New `scripts/breakingdiff_test.py` (15 tests: zero-domain banner / verdict / keys,
  all-false wording versus `verdict_key`, witness-cap notices, N-way zero domain), and it
  is registered in `examples/test_alignment_bootstrap.py`'s P-side corpus
  (`TEST_FILES_ALL`) so its assertions count as guarded rather than as gaps.
  `coverage_guard_test.py` 13→19; `delivery_gate_test.py` 20→25 (blank-`PREFIX:`
  refusal, declaration-side and file-side prefix normalization, and two mutation pins).
  Each guard ships with its mutation pin in the same file (banner removed / banner
  always on / wording reverted / truncation notice removed / blank-prefix guard removed /
  guard over-tightened / dedupe removed / raw prefix matching restored).
- `scripts/ci_gate.py` now discovers 29 test files, 29/29 green (34–42s across repeated
  runs on one machine, measured 2026-10-29; the `llama` archive was absent, so its 16
  corpus-anchored items took the skip path, and `malecns` needs `pyarrow`).

### Corpus pins in the case studies

- `casestudy/pdg` is pinned to PDG 2024: edition 2024, schema 0.2, 18,064 `pdgdata`
  rows, 7,593,984 bytes, SHA256 `a925777f…fd532e`, citation S. Navas et al. (2024).
  `fetch_data.py` is now a verifier/recoverer, not a downloader — a present file is
  checked field by field; a missing one prints the recovery steps and the anchor and
  exits non-zero; `aligned.py`/`misaligned.py` run the same structural guard before
  reading. The online 2026 edition (schema 0.3, 19,587 rows, about 25.75 MB) is
  different data, not a newer snapshot; migrating is a future item. The sqlite is
  tracked in-repo (`.gitignore` exception), since the 2024/2025 upstream URLs now 404.
  `pdg/test_aligned.py` 22→34.
- `casestudy/llama`: `corpus_manifest.json` pins exact bytes and SHA256 for all three
  used CUDA assets (`b10472` = 146,707,438; `b10595` = 146,496,057; `b11681` =
  154,609,844) and for the CPU and CUDA-12.4 alternatives, with the CPU assets marked
  `readings_unverified`. `fetch_corpus.py` checks bytes then SHA256 and refuses to
  unpack on a mismatch, and gains `--links` (print URLs/bytes/SHA256; no download).
  New `casestudy/llama/DOWNLOAD.md` lists all 9 assets. The docs state `b10472`/`b10595`
  = CUDA 13.3 and `b11681` = CUDA 13.4 (family inferred from the shipped DLLs, minor
  version from the official asset name), llama.cpp (ggml-org) nightlies rather than
  Meta's Llama weights, and the unverified CPU readout. `llama/test_aligned.py` 36→45.
- Every case-study CLI entry reconfigures stdout to UTF-8: on a GBK Windows console the
  report markers used to die with `UnicodeEncodeError` at the moment a warning was
  printed. The contract is now pinned, not just written —
  `examples/iteration_chain_test.py` enumerates all 14 CLI entries: 5 corpus-free entries
  run as real subprocesses under `PYTHONIOENCODING=gbk` (exit 0, no `UnicodeEncodeError`,
  stdout valid and non-empty UTF-8), while the 9 corpus-dependent entries skip with the
  reason named, never silently. A static guard checks the switch in all 14, and the list
  is reconciled against what is on disk (`if __name__ == "__main__":`), with the runnable
  and skipped sets required to be disjoint.

### Documentation

- `VERSION` 1.0.0 → 1.0.1. The README no longer repeats a literal version number; both
  places point at the root `VERSION` as the single source of truth.
- README: the suite count is the gate's own discovery (29 files), the measured readout is
  dated, the corpus table names the PDG 2024 sqlite as the one corpus that ships in the
  repository, and the PDG row says its script verifies rather than downloads. `AGENTS.md`
  no longer repeats a fixed suite count either.
- `SKILL.md`: contracts for the zero-domain banner / `domain_total` / `in_domain`, verdict
  wording versus `verdict_key`, the witness-cap notice, the blank-`PREFIX:` refusal and
  the ratio dedupe, plus the PDG 2024 and llama asset pins. (SKILL.md and this file move
  in the same batch by rule.)
- Post-release documentation audit (31 findings, 0 blocker), applied in full. Hard
  copy-facing errors: the Core-API snippet uses a real `Claim` attribute for `order_key`;
  `references/test-alignment.md` carries the current bootstrap readout (73 items,
  50/19/4/0) instead of the stale 71-item snapshot. Navigation: `INDEX.md` puts the
  docaudit row inside the examples table, adds `probes/`, `LICENSE`, `requirements.txt` and
  `ci_gate.py` rows, and no longer claims one line for every file; `AGENTS.md` marks its
  gate and source-of-truth rules as binding rather than navigation, covers `examples/` and
  fixes the discovery rule (`.py` files only). Factual: the README scopes "no tool catches
  this kind of drift" to the parser/type-checker/compiler/CI stack (naming `oasdiff` as the
  adjacent counter-case), replaces the unanchored synapse count with the malecns manifest's
  row counts, aligns the PDG sqlite units (7,593,984 B ≈ 7.59 MB / 7.24 MiB), and stops
  claiming there is no issue tracker; `casestudy/README.md` reconciles the four error modes
  and the k8s readout-versus-refusal wording. `references/strength.md`'s interleaved
  worked-case paragraph is restored, and `references/receipt-format.md` now says a
  generator domain raises `ReceiptError [RC:DOMAIN_NOT_MATERIALIZED]` instead of silently
  digesting as 0. `SKILL.md`'s do-not-use list names tolerance-based numeric checks (with a
  pointer to `references/domain-mapping.md`), and its frontmatter now says the tool reports
  where the accounts differ rather than "only divergence", with the short form kept in the
  body and glossed (all four quadrants are reported; only the correctness verdict is
  withheld). (SKILL.md and this file move in the same batch by rule.)
- This file now carries the mechanism-level incident ledger the README points at, with
  its provenance stated: reconstructed from pre-1.0 notes, not in the public history.

---

## Pre-1.0 incident ledger (mechanism level, reconstructed)

> Reconstructed from pre-1.0 development notes. Intermediate builds were never
> published, so these entries are **not in this repository's public commit history** and
> cannot be checked against it; the dates are the dates the notes carry. What is kept is
> the mechanism, the readout, the red count, the fix, and the test that now locks it.
> Working labels, role names, project names and local paths are omitted.

### 2026-10-12 — tier-three silence in the coverage catalog

A substantial SKILL.md rewrite put the six structural preconditions, the four domain
scenarios and the three exclusions outside the catalog. The four-quadrant readout of the
before and after versions was **identical — `7/4/2/0`** — and was read as "the rewrite did
not make the docs more self-deceptive". In fact **13 catalog items were blind** to that
change. After folding them into the catalog, the dominance column went **from 2 items to
12**. The same shape appeared on the P side: the bootstrap instance's assertion account
read only one test file, so assertions living in the other test files were counted as gaps
out of thin air; searching across all four test files moved two items into the common
column.

**Criterion:** under-reporting does not only miss real problems, it can invent them; when
fixing under-reporting, check both directions.

### 2026-10-15 — three mechanisms that looked right and failed silently

| Site | Defect | Fix |
|---|---|---|
| `coverage_ratio` | numerator and denominator came from the same source (`len(in_scope), len(in_scope)`), so the ratio could not report less than 100% | the denominator is the round's changed items, gaps included |
| `find_uncovered` | `exempt` matched by substring in both directions: `exempt=["coverage"]` silently swallowed `coverage gate notes` | verbatim equality; a relaxation must be declared as `PREFIX:` |
| `compare_n` ratchet | `j<k` was taken as "old → new"; passing `[v3, v1, v2]` computed a reverse regression and warned about nothing | `order_key(i, Claim)`; without it `ratchet_trusted=False` and the report says the direction is unverified |

The old tests were part of the defect: `test_ratio_uses_in_scope_denominator` covered only
the all-covered and all-outside cases, bypassing the one mixed input with discriminating
power. `test_ratio_denominator_includes_gaps` added mixed inputs and asserts
`covered < total` over four gap combinations. When exemptions moved to verbatim equality
one existing test went red on the spot — it had been matching `exempt=["typo"]` to
`changed=["fixed a typo"]` by substring, which pinned the bug as the spec.

Two real bugs surfaced on the way to `order_key`: `sorted`'s tie-break compared `Claim`
objects, and an incomparable `predicate` raised `TypeError` (fix: compute the key first,
then sort by index); and `anchor` pointed at the wrong index after re-sorting, anchoring
the baseline to another account while the report still looked normal (fix: remember the
anchor by identity and recover it with `claims.index(identity)`; regression pin
`test_anchor_name_follows_the_same_reordering`).

### 2026-10-15 — the delivery gate and two entry points reading `0/0/0/0`

- The delivery gate cannot be established by comparing before and after the refactor
  (same source, P6 fails; a false green is worse than no gate). Q = the spec, contract or
  consumer dependency (human-produced), P = what the tests actually guard
  (agent-produced); dominance reads as "the spec promised it, the test does not guard it".
  Two-level coverage: `changed_files` and `catalog` were mixed into one `require_covered`
  call — 100% gate noise — and were split into an explicit `file_coverage` mapping.
- Empty-catalog hole: the PoC's "`applies` always false" was blocked by "out-of-domain
  skip > 0" on a 3-point domain, but `catalog=[]` gave out-of-domain 0 and quadrant counts
  `0/0/0/0`, so the gate released; both entry points read like "everything is normal".
  Fix: move "the comparison domain is empty" to the front of the decision sequence.
- `order_key` semantics existed in the code but SKILL.md never promised them, so the item
  sat in divergence; the fix was the document, not the data, and the item moved into
  common. `forgery_poc.py` stays out of `TEST_FILES_ALL` (it holds moves, not assertions;
  forcing it in would falsely inflate six topic hits) — corpus-layer exclusion and
  promise-layer registration each carry a test.
- Material overlap is a leak: when a blind-run payload overlaps the corpus the agent may
  legitimately read, a high score cannot be trusted. The first payload overlapped the
  worked example (`otel-2025-01.json` / `otel-2026-10.json`) and was voided and re-run
  with fresh material.

### Mutation ledger (same batch: 16 counted, 15 data rows, all caught)

The original count is **16 (the header included)**; the table merges the **15 data rows**
into three lines by mechanism. The original values are kept, not recomputed; each number
is how many tests went red under that mutation.

| Broken on purpose | Tests that went red |
|---|---|
| `coverage_ratio` denominator back to `in_scope` / `exempt` back to substring / `ratchet_trusted` forced true / `anchor` not following the re-sort | 3 / 2 / 2 / 1 |
| Delivery gate always passing / blind to dominance / blind to out-of-domain / coverage gate removed / empty catalog not refused / `0/0/0/0` not refused | 4 / 3 / 1 / 3 / 1 / 1 |
| Delivery gate also blocking divergence (over-blocking) / PoC entering `TEST_FILES_ALL` / verification section hard-coding counts / verification section missing a file / the "ratchet direction" promise deleted | 1 / 1 / 1 / 1 / 1 (weak) |

**Over-blocking is also broken**: a gate that dares not pass anything is routed around
after two uses; a wrong direction and a wrong amount are equally harmful. Three
disciplines were recorded in the same batch: with several lines of defense, `assertRaises`
alone is not enough — check which line caught it; confirm the mutation really took effect
(a `str.replace` that missed on punctuation drift produced the false conclusion "the test
has a hole"); and quantities of different dimensions must not be compared in one set.

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
- **Entry point narrowed to three demands**: the frontmatter description opens on
  the moment of use — about to claim that two or more accounts of one artifact
  agree, on a read-through alone — and names the three demands with a user behind
  them: confirming a migration or rewrite did not drift, auditing a legal change
  that raised nothing, and checking an agent's early claim against the artifact it
  finally lands. The engine's domain-agnostic generality and every measured result
  below are unchanged; only the routing text moved, from 1119 characters to 958
  (the `skills-ref` limit is 1024, and the longer text would have been rejected).
  The agent case is bound to the enumerability requirement on purpose: drift that
  lives in prose cannot be parameterised, and claiming it could is the one way
  this description could over-promise.
- **Attribution in frontmatter**: `metadata.author: Benbird316`, not a top-level
  `author:` key. The frontmatter field set is closed —
  `name` / `description` / `license` / `compatibility` / `metadata` /
  `allowed-tools` — and `skills-ref` rejects anything else with
  `Unexpected fields in frontmatter`. This was measured in both forms rather than
  read off the spec: the top-level key fails validation, the nested form passes
  and resolves to `{"author": "Benbird316"}` under `read-properties`.

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
- **Measured 2026-10-22**: 28 test files, 28/28 green in 39s with every corpus
  present, 20s on a corpus-free tree, 32s with only `malecns` present (wall clock,
  one machine — the figure moves with which corpora were fetched). `pyarrow` is the
  only third-party package the suite touches, declared in `requirements.txt` with
  the measured versions as its anchor.
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

The mechanism-level record behind the 2026-10-12 and 2026-10-15 rows — readouts and red
counts — is in the pre-1.0 incident ledger above.

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

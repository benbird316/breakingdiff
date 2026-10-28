---
name: breakingdiff
license: MIT
metadata:
  author: Benbird316
description: Use when you are about to claim that two or more accounts of one artifact agree, on a read-through alone. A claim differential turns that claim into a recomputable readout. One executable claim per account, point-by-point over a shared parameter domain, four quadrants (common, divergence, dominance, neither) each with a live witness. Three jobs carry the demand. A Python to Rust/Go port against its source; a bug fix against the behaviour it promised to leave alone; an agent's early claim against the artifact it finally lands. It reports where the accounts differ (and where they agree), never which side is right. Needs N>=2 independent accounts whose parameter points can be enumerated, a change that raises no error, bivalent predicates. Do not trigger for one material, for an account that is prose and cannot be enumerated, line diffs, code-quality opinions, public-spec API compatibility (oasdiff covers it), tolerance-based numeric checks, or when a verdict on who is right is wanted.
---

# breakingdiff — a claim differ

One executable claim per account of the same artifact; compute the four quadrants mechanically and attach witnesses:

```
common      P ∧  Q        both hold
divergence  P ∧ ¬Q        P is stronger
dominance  ¬P ∧  Q        Q is stronger ← the product: new capabilities the old account no longer covers
neither    ¬P ∧ ¬Q        neither holds
```

**Divergence ≠ better.** The tool reports where things differ; it does not adjudicate which side is right. The short form, **report only divergence, never adjudicate**, means all four quadrants are reported and only the correctness verdict is withheld.

## When to use, when not to

**Where the trigger sits**: The trigger is not an instruction the user gave; it is the moment you are about to output a claim about the relationship between two or more materials, with only a read-through behind it.

Use when: two legal snapshots of one config/spec/policy; two implementations on the same input; behavioral equivalence before and after a refactor; a clause-by-clause comparison of acceptance criteria; two definitions — find counterexamples in the same parameter domain; a clause-by-clause comparison of what the evidence covers (research); a change with no public spec and no off-the-shelf gate — the niche where all the value sits in P3.

Do not use when: an allow/deny verdict is needed; you need to adjudicate who is right; OpenAPI changes (oasdiff covers them); the change raises an error (parsers and compilers already stop it); the value survived but its meaning changed (`total_cents` cents→yuan) — formalize the semantics first; any of the six structural preconditions is missing.

One exclusion deserves its own sentence, because it is easy to miss: **tolerance-based numeric checks** (floating-point equality, p-value thresholds). A tolerance is not a boolean the tool can decide — it is a third state someone chose by hand, and who owns it changes the readout. Tolerance → read **references/domain-mapping.md** → it pins why the decision rule has to be settled before running.

### Six structural preconditions

**P1** N ≥ 2 accounts, not one; only one material or same-source accounts fails. **P2** enumerable into finite parameter points (flagd→`(flag, variant)`); the account is prose and cannot be enumerated into parameter points → do not run. **P3** the change is legal and raises nothing — decides whether the tool is irreplaceable. **P4** bivalent per point. **P5** point-by-point recomputation needed. **P6** the sources of the accounts are independent — one author or pipeline means same-source self-consistency, not cross-verification.

P1+P2 decide "can it", P3 "should it". All the value is in P3; P6 decides whether agreement counts as verification. Domain change → read **references/domain-mapping.md** → adds no criterion, relaxes none.

## N accounts and the iteration chain (compare_n)

Pairwise quadrants are the N=2 case. For N ≥ 2, compute per-point verdict vectors `(v₁,…,vₙ)` and sort into five shapes:

| shape | definition | meaning |
| :--- | :--- | :--- |
| all_true / all_false | all N agree | agreement ≠ correct (P6) |
| outlier(i) | exactly the i-th is False and the rest are True | dropped a point; carries attribution |
| pioneer(i) | exactly the i-th is True and the rest are False | only one has it; needs an external anchor |
| split | the remaining mixed shapes | witnesses; a human decides |

**Iteration-chain ratchet check**: `compare_n(..., chain=True)` checks every pair j<k for `v_j=T, v_k=F` — the old version had it, the new version dropped it = a **ratchet violation**. Adjacent pairs miss cross-version regressions; run both.

**ratchet direction must be fixed by `order_key`, not list position** (`order_key(i, Claim)`; when given, re-sort ascending). Without it, `ratchet_trusted=False`: reversing direction flips the conclusion while the readout looks normal — worse than a zero readout.

`anchor` records the input **index**; after re-sorting it follows identity, or silently anchors to another account. A wrong item, or the item is not in the catalog — both pass silently.

**Majority voting is only a clue, never a verdict**: n−1 true, 1 false marks a "candidate suspect" only; those n−1 may be same-source. Adjudication belongs to an external anchor or a human.

## Test alignment (advanced usage)

Compare two statements of one tool: P = what the test assertions assert, Q = what the spec commitment or a consumer's dependency promises. Dominance is the coverage gap "the spec promised it and the test does not uphold it"; divergence is "the test is finer than the spec" (usually hardening).

Q source, the three hard disciplines, and the inherent floor → read **references/test-alignment.md** → it stops "all green, spec not upheld" from passing. Worked instance: `examples/test_alignment_bootstrap.py`.

## Coexisting with an existing gate system

`scripts/delivery_gate.py` makes this skill a checkpoint before delivery. It swaps the opponent: not "your own past" (same source, fails P6) but an independent Q from a human or upstream against the agent's P. Three disciplines: **dominance > 0 is a fail** (add a test or amend the spec; a human decides), **divergence does not block** (the test is finer than the spec), **out-of-domain skip > 0 is a fail** (**a zero readout is not a pass**).

Swap argument, usage, two-level coverage, approaches A/B, and the `precision < 90%` threshold that makes it **forbidden as a blocking gate** → read **references/test-alignment.md** (the code delivery gate section) → it stops same-source agreement from slipping into delivery.

## Three-layer structure

**Public surface**: `compare` / `compare_n` / `render`, the coverage and delivery gates, and the receipt (write / verify); a Stop hook is the only process-level entry. Other `scripts/` modules are repo maintenance (test guards, version stamp, dist layout) → `README.md` / `AGENTS.md`. Import: `from breakingdiff import Claim, compare, compare_n, render` (add `scripts/` to `PYTHONPATH`; command list → `README.md` "Install and verify").

Need a file → `INDEX.md`. No MCP: two entry points for one thing confuse the trigger (`README.md`).

Applied examples by layer: pdg data-extraction, llama probe+ledger, malecns strength, port, k8s scope; run them via `casestudy/README.md`.

**Two cases pin their corpus instead of fetching whatever is current.** `pdg` is pinned to the PDG 2024 sqlite — edition 2024, schema 0.2, 18,064 rows, exact byte count and SHA256; the fetch script verifies or prints recovery steps and never substitutes the online 2026 edition, which is different data rather than a newer snapshot of the same corpus. `llama` pins exact bytes and SHA256 for its three used assets: `b10472`/`b10595` are CUDA 13.3, `b11681` is CUDA 13.4, the builds are llama.cpp (ggml-org) nightlies rather than Meta's Llama weights, the CPU alternative's readout is recorded as unverified, and every URL is listed in `casestudy/llama/DOWNLOAD.md`.

## Workflow

Full six steps, gate-error lookup table, common ways to die, case-study conventions → read **references/writing-claims.md** → only the skeleton stays here:

1. **Fix the parameter space** into enumerable points: flagd `(flag, variant)`, K8s `(operation, path, method)`.
2. **Write two Claims** (P old, Q new/baseline), each with `source` (repo + file + commit), `quote`, `source_tests` (`((point, expected),)` — a tuple of tuple pairs), `reading_variants`. Pass `quote_source` too: construction also checks the quote verbatim.
2b. **Declare the claim's strength** — shape, band width, and where the width comes from — and run the error-mode ladder before a gate depends on it. Method → read `references/strength.md` → it keeps true data from being read as bad data.
3. **Run `compare(P, Q, domain)`** (N ≥ 3: `compare_n(claims, domain, chain=...)`). Three gates run automatically at construction time and at comparison time: an empty `source`/`quote` → `ProvenanceError`; any test point fails → `SourceTestError`; an interpretation has the same value as the body at every test point → `SourceTestError`.
4. **Read the report**: dominance first, divergence next; inject semantics via `meaning_dominance=`.
5. **Mutation evidence** when adding a criterion: break the behavior, measure how it goes red, then assert.

## Boundaries

- **A gate verifies that the self-attested material you supplied is self-consistent**, not that the claim is true; a Claim with `source_tests=()` and no reading_variants is bitten by no gate — by design.
- **The template covers only keys present in both versions.** Additions and removals land in out-of-domain skip; a disappeared key is dominance-level, so write existence Claims over the union of both versions.
- The predicate needs human compilation (agent drafts, gates verify, a human confirms provenance).
- The gate checks the claim against the source text it cites, not whether that source is authoritative or complete.
- Reports are always a lower bound: a coarse parameter space misses real divergence.
- **A zero readout is not a pass** (see "Three-level silence"): a change outside the space reports "zero change" — zero information.

## Three-level silence: before reading out, judge whether the surface under test still covers the change

| Tier | Form |
| :- | :--- |
| One | under-reporting: coarse surface, so the readout is a lower bound |
| Two | false green from incomplete extraction |
| Three | surface missing: every change is outside the catalog |

**A zero readout is not a pass.** **If this change were wrong, would the existing readout move? If not, it is not inside the surface under test.**

It has fired in real iterations: one SKILL rewrite blinded 13 catalog items at once while the four quadrants returned the same readout as before, and that was read as "verification passed". **The mechanism holds every time; it is not a one-off lesson** — the record is in `CHANGELOG.md`.

Before compare, `require_covered(changed_markers, covered_markers, what="…")` raises `CoverageError` with the gaps: fold into the space, or exempt explicitly. `scripts/coverage_guard.py` checks verbatim markers only (better to under-report than to falsely claim coverage); exemptions and `PREFIX:` relaxations are verbatim; it raises rather than warns. **A gate can itself fail silently in three tiers** — `coverage_guard_test.py` pins that with mutation evidence.

**At the report layer the zero shape is stated, not left to the reader.** `compare`/`compare_n` keep returning — the delivery gate and the forgery PoC read the counts — but when nothing entered the comparison map the report cannot be read as a four-quadrant finding. `DiffResult` and `NWayResult` expose `domain_total` (every parameter point handed over, skips included) and `in_domain` (points that entered the quadrant or shape map); `render`/`render_n` open with a zero-domain banner, and `render_n` separates an empty parameter domain from an all-out-of-domain one because the two need different fixes. `verdict()` words the zero domain as no comparison having happened and the all-false shape as equivalence on a double negative, while `verdict_key()` stays `disjoint` — the machine key is a cross-language contract and does not move. A capped witness list is a sample, not a column count: the report says how many entries it did not list.

**The same rule reaches exemptions and the ratio.** A `PREFIX:` whose suffix is blank — empty, spaces, tabs, full-width space — raises `ValueError` instead of exempting every marker, because an empty prefix matches all of them; the delivery gate refuses the same declaration and normalizes prefixes on both sides, so the two gates cannot drift apart on what a declared prefix covers. `coverage_ratio` counts each distinct changed item once (verbatim, order-preserving) before taking the denominator: a change listed twice is one change, not two.

### Forged PoC and capability declaration table: effective against sloppiness ≠ effective against deliberate forgery

`examples/forgery_poc.py` pins one fact: a forged Claim passes provenance binding, source self-test, and discrimination — **the three gates are effective against sloppiness, ineffective against deliberate forgery**. A **capability declaration table** declares per technique "can this currently fool the gate" (`CAPABILITY`); status is in `CHANGELOG.md`.

### Reconciliation between the delivery gate and the PoC

`delivery_gate_test.py` builds the gate from the unchanged PoC and asserts up front that it passes: **the PoC records which techniques can fool a gate; the delivery gate is the real gate; they must line up.** ★ `forgery_poc.py` stays out of `TEST_FILES_ALL`: techniques are not assertions.

### Under-reporting does not only miss real problems; it can invent them

If P reads one test file, assertions elsewhere become gaps; search all assertion files (`TEST_CORPUS`). **When fixing under-reporting, also ask "will it invent false problems"; check both sides.**

## Receipt vs. delivery

"Verified / unverified" is a binary: **self-attested is NEVER worded as "verified"**. After compare/compare_n, `scripts/receipt.py` writes one deterministic JSON receipt: 0=pass / 1=gate failure / 2=runtime error. The receipt is produced by the party that ran compare and is still self-attestation; verification is re-execution: the auditor re-executes per rerun_cmd and compares byte for byte (deleting the receipt and rerunning, or rerunning from a different CWD, must be byte-identical). No receipt or a mismatch = unverified. Field contract → read **references/receipt-format.md** → receipt-field drift goes red on the spot.

## Blind-written expectations

A blind write lands the expectation before the readout (`write_expected → compare → reconcile`); the two reconciliation tiers and the token check → read the "Blind-written expectations" section of **references/receipt-format.md** → it prevents writing the expectation after seeing the result.

## Provenance tiers

`Claim.source_kind` has only two tiers (executed/AST is an interface left unimplemented). self-attested (≈SLSA L1) proves only that someone declared it; supplying `source_obj` (a full 40-char sha:path) promotes it to git-object. git-object (≈SLSA L2) means the quote appears verbatim in a commit blob, defending against later tampering — **it does not defend against source forgery**, nor judge whether upstream is trustworthy. Verification mechanics → read the "Provenance tiers" section of **references/receipt-format.md** → it prevents "verified the wrong repo while claiming verified".

## Host hooks (optional installation)

The hook decision is a **product state machine** (disk markers, not transcript semantics); the decision order, condensed:

    1. stdin empty or not JSON → exit 0 silently
    2. stop_hook_active=true → exit 0 immediately (prevents a blocking loop; before any disk IO)
    3. no marker (no .breakingdiff/) → exit 0 instantly (the first fast-path branch)
    4. pending without receipt → exit 2 + feed actionable text back over stderr (receipt internal 2)
    5. receipt gate fails → exit 2 + stderr diffs (receipt internal 1 → hook 2)
    6. claims newer than receipt → exit 2 + stderr (stale product)
    7. otherwise → exit 0

The installation snippet and the Windows PowerShell wrapper → read **references/hooks.md** → it prevents the decision order and its documentation from drifting (a hooks change goes through the /hooks menu review). **Honest degradation**: a hook is a product-expiry reminder, not a requirements judge — if the agent never writes pending, it stays silent; it **raises the cost of sloppiness, not the cost of forgery**, a backstop rather than a replacement.

## Verification runs

Commands and expected numbers → read **README.md**, "Install and verify" → the starter instance outputs the four quadrants 25/0/1/0. **After changing a decision, rerun everything**; a `coverage_guard.py` change moves the bootstrap EXPECT and the catalog.

### Mutation evidence

Every protected behavior needs an assertion that **breaking it must go red**, in **both directions**: too loose (**it disguises itself as a pass**) and too tight (it blocks what should pass, and after two uses people route around it); **a wrong direction and a wrong amount are equally harmful**. Three hard disciplines: **with several lines of defense, `assertRaises` is not enough**; **first confirm the mutation really took effect**; **things of different dimensions cannot go into the same set for comparison**. Ledger: `CHANGELOG.md`; methods → read step six and "Dimension discipline" of **references/writing-claims.md** → read before changing a criterion.

Red-first → regression lock → read **references/phase-transition.md** → prevents missing freeze and cleanup steps.

## Conclusion discipline

A term choice looks arbitrary → read `references/iglossary.md` → it records the frozen English–Chinese mapping and each term's meaning in this system.

MUST: every count cited is taken verbatim from the tool's readout text, and you can point at its enumeration witnesses (which domain, which points).

NEVER: give a number that does not exist in the tool output — a hand-counted number, however confident, must not be stated as a readout; either add a Claim that puts it into the readout, or mark it "unverified inference".

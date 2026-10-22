# ORCHESTRATION.md — breakingdiff multi-agent orchestration handbook

> **This file is written for whoever dispatches the batches (a human or an agent), not for the agents executing a batch.**
>
> `SKILL.md` answers "how do I use this tool"; `README.md` answers "why does this tool look the way it does".
> This file answers a third question: **how do you split one convergence batch across multiple agents so that all three sides do not go wrong together.**
>
> The position in one sentence: **the tool guarantees that two sets of claims say the same thing over the same parameter domain; it does not guarantee that the parameter domain you handed it is correct.**
> The latter is an orchestration responsibility; see §4.

---

## §1 When to split across multiple agents, and when not to

**Default to a single agent.** The only reason to split is **independence**, not workload.

| Case | Split? | Reason |
|---|---|---|
| The write-red / converge / QA steps of one convergence batch | **Split, and you must split** | Independence is the only source of P6; two sets of claims written by the same agent are bound to be same-source self-consistent |
| Blind run (read the source to find duplicate surfaces / read the declaration surface to find task gaps) | Split | The two blind-run types reach conclusions from different sources and cross-check each other |
| Requirements analysis + construction | **Do not split** | The requirements side needs it, the construction side needs it; the two are unfoldings of one decision, and splitting loses the adjudication |
| Multiple independent sites inside one batch | Do not split | They can run in parallel, but they do not amount to independent verification |
| Bug hunting (not a convergence batch) | Do not split | The differential engine does not apply |

**Anti-pattern**: splitting work one person could finish into three agents just to "look rigorous".
Three sides that agree but share a source buy zero extra information at three times the cost.

---

## §2 The four roles, and what each is forbidden to do

The batch order is fixed: **blind run → requirements → write-red (P) → converge → QA (Q) → gate**.

### 2.1 Blind-run agent

- **Reads**: the source (contract mode) or the declaration surface only (functional-heuristic mode; see §4.1)
- **Forbidden**: seeing anyone else's conclusion before giving its own; **forbidden** to pick a plan for the convergence batch (that is the requirements batch's job)
- **Output**: a site table + three-state classification (same-form / form variant / **look-alike but semantically distinct**) + reasons

> **Look-alike but semantically distinct is the most valuable part of this report.** "It looks the same, so merge it" is the most expensive mistake in refactoring.
> Every "must not merge" needs a written reason (concurrency-lock protocol / persistent-surface reconciliation / freshness check / human alignment by design…),
> not "I think they are different".

### 2.2 Requirements-batch agent

- **Reads**: the blind-run report + **consumer-view materials** (`SKILL.md`, `references`, CLI output shape)
- **Output**: candidate plans A/B/C…, each with **adopt / reject + reason + blast radius + benefit**
- **Forbidden**: deciding the adjudication itself — **the user adjudicates**

### 2.3 Write-red agent (P)

- **Never touch production code.** Not once. Not even to change one character.
- **What it locks is the pre-change behavior**, including the parts of the current behavior that look like bugs
  > `SKILL.md` records a real case: one test once pinned a bug down as spec.
  > This is **a feature, not a defect** — refactoring should keep the bug; fixing a bug is another commit.
- **Its commit must land before the convergence batch** (the write-red artifact gets its own commit)
  — Reason: if the convergence batch goes red, you must be able to return to the baseline with a single command and re-adjudicate, instead of doing archaeology inside a mixed diff.

### 2.4 Convergence agent (execution)

- **Only converges**; changes no criterion, touches no P artifact, touches no test
- **When P goes red, it must not change P**. Red = an in-design differential signal; **hand it over to the contract-test engineer to refresh**
  (the precedent of "red first, then green", option two).
  > If the convergence side refreshes P itself, it becomes P's author as well, and P6 dies on the spot.
- **Judge "merge only when the form is byte-identical"**. "It looks the same" is not a reason to merge — a form variant must keep its separate shape.

### 2.5 QA agent (Q)

**This is the only independent anchor in the whole chain.**

- **The only way to make P6 hold**: Q = the spec/contract/consumer-side dependency (human output), P = what the tests actually guard (agent output)
- **Prevent circular reasoning**: expected values must be **independently reproduced**; Q must not call P's predicate
  > Example: in one convergence, the Q artifact computed the expected keys independently with low-level system calls,
  > **explicitly not through the primitive under test**.
  > If Q reuses P's predicate, the consistency is constructed, not measured.
- **Forbidden** to take the construction diff and "verify" the construction — that is an audit, not verification, and its strength is an order of magnitude lower.
- **Output**: Q claims + mutation evidence (see §5)

---

## §3 Upstream independence: more important than "different agents"

**Different agents are only a necessary condition, not a sufficient one.**

```
misread the requirements → wrong dispatch prompt → P written wrong (wrong baseline)
                                               → convergence converges against the wrong baseline
                                               → Q written against the wrong baseline (wrong independence)
all three sides green, identically wrong. The differential engine cannot catch it — it checks whether P and Q agree at the parameter points.
```

The criterion: **ask "if this link is wrong, will the next link go wrong with it?"**

| Link | Upstream source | Independence |
|---|---|---|
| Blind run | Source + contract | ✅ Strongest |
| Requirements batch | Blind run + consumer view | ✅ Strong |
| Write-red P | Requirements batch | ⚠️ Inherited |
| Convergence | Write-red P | ⚠️ Inherited |
| **QA Q** | **Source (read independently)** | ✅ **Key isolation point** |

**Only the Q link can break the inheritance chain.** So Q's independence is the batch's lifeline —
if it drifts, the whole chain drifts with it.

---

## §4 The four things a dispatch prompt must contain

Miss any one and the executor will fill it in themselves, at the cost of rework.

1. **Scope boundary**: which sites are in the batch and which are explicitly left alone
   > Counter-example: one blind run listed "3 look-alike but semantically distinct classes", which is exactly why the convergence batch did not merge them in passing.
   > No scope = the executor expands by their own reading = breaking the lock surface (golden frozen keys, adjudicated docstring declarations).

2. **The iron rule of unchanged values**: output and on-disk bytes stay byte-identical; serialization parameter forms pass through point by point, **with no form normalization**
   > "Normalizing the newline while you are at it" during convergence is a classic accident: it changes the on-disk bytes.

3. **A list of prohibitions** (what this role must not touch, named one by one)

4. **Red-state handling path**: who to find when it goes red, which role it is handed to, **and no fixing it yourself**

### §4.1 The blind-run type must be declared

- **Functional-heuristic blind run** (no reading the source; feed consumer-facing materials only) → for **behavior-declaration / self-report / documentation** batches
- **Contract-mode blind run** (source reading required; check emit↔consume / key↔value alignment) → for **contract / data / key / interface** batches

**The choice must be declared in the plan's discipline section**; not declaring it = the executor chooses = the two batches' conclusions are not comparable.

---

## §5 Close-out duty: mutation evidence is not optional

**The criterion in one sentence: if you break the implementation, will this lock go red?** If it does not, it has no discriminating power.

Two kinds are mandatory:

- **Lock-surface mutation** (gate side): inject a drift form into the module under test; the lock surface must mismatch
  > Example: inject a drift form into the primitive under test (first-element substitution / element rotation / tuple demotion) → the key-shape expectation must mismatch.
  > Note this only tests "the sensitivity of the claim"; it **does not** test Q's discriminating power over the implementation — that is the next item.

- **Implementation mutation** (tested side): on a copy in a tempdir, **deliberately break the implementation**, run Q, confirm red
  > This one is stronger than any written declaration, and it is **the only mechanical way to prove that "Q is not same-source self-consistent"**.

### §5.1 The pyc timestamp-granularity trap (methodology, already hit)

`pyc` timestamps have **second** granularity. Doing an "equal-length reorder" mutation within the same second produces a **false green**.
The mutation driver must carry `PYTHONDONTWRITEBYTECODE=1`.

### §5.2 Gate-noise discipline

Putting two things of different dimensions into one `require_covered` → **100% gate noise → it gets switched off after two uses**.

> **A gate that makes noise gets switched off — and once it is off, nobody looks at what it was blocking.**

The coverage structure must be two-level (changed files / item markers, each with its own set). Exemptions go by literal equality;
relaxing one requires writing `PREFIX:` explicitly, and it **raises instead of warning**.

---

## §6 Readout discipline: how to read the four quadrants, and how not to phrase them

`compare` outputs common / divergence / dominance / neither.

| Readout | You may say | You must not say |
|---|---|---|
| `common=N, divergence=0` | "P and Q agree at N parameter points" | ❌ "the refactor is equivalent" ❌ "verification passed" |
| `dominance>0` | "one form dominates another over the domain, **pending adjudication**" | ❌ "an improvement" |
| all 0 | **zero information**, not a pass | ❌ any form of pass statement |

**The gate verifies that "the self-attestation material you supplied is self-consistent", not that "the claims are true".**

Delivery wording:
- `self-attested` must **never** be phrased as "verified"
- What actually verifies is **re-execution**: rerun per the receipt's `rerun_cmd` and compare byte by byte
- A receipt is self-attestation; verifying the receipt is still self-attestation

---

## §7 Three-level silence self-check before the readout

**Before running compare**, answer one question first: **if this change is wrong, will the current readout change?**

| Level | Form | Readout behavior |
|---|---|---|
| Level one | coarse granularity, the real divergence is missed | there is a readout, but it is too small — **a candidate lower bound** |
| Level two | incomplete extraction manufactures a false green | zero change, but the data was not fully extracted |
| Level three | the change lies entirely outside the parameter space | **zero readout** — the most dangerous, it looks like "everything is normal" |

```python
from coverage_guard import require_covered
require_covered(markers_changed_in_this_round, markers_covered_by_the_parameter_space, what="changes in this round")
# not covered → CoverageError; you must either fold it into the space or declare an explicit exemption
```

**The exemption surface must be listed explicitly, item by item, with reasons** (in the suite docstring, not in your head).
"No silent exit from the space" — a silent exit from the space = a three-level-silence false green.

---

## §8 Capability declaration table: discipline when changing gates

See `examples/forgery_poc.py` for this tool's own adversarial record (permanent; it constructs forged Claims that go all green and fool the gate).

**Do not keep a "cannot block" ledger.** With a ledger, every defense that lands requires hand-editing the expectation,
and the moment "the improvement goes red" the screen fills with confusion.

Use a declaration table instead: `CAPABILITY` declares whether each technique "can fool the gate as of today", and the tests only reconcile the declaration against the measured result.
- An improvement = measured confirmation that it is blocked + that technique graduates into its own independent regression test; **not one existing claim needs changing**
- Residual risk (known and accepted): an ungraduated table entry can be silently deleted = the declaration surface shrinks. Graduated entries must not be deleted — they have names in the test files.

`forgery_poc.py` **does not go into** `TEST_FILES_ALL`: it holds techniques, not claims,
and it has no `test_` functions. Letting it into the P-side corpus would treat "the PoC mentions a word" as "a test asserted something" —
**different dimensions put into the same set**.

---

## §9 A complete worked example (self-contained, domain-agnostic)

Below is one convergence batch that ran end to end. **Sites are described in generic form and bound to no specific project** —
what is worth copying is the structure, not the numbers.

Scenario: a repo has 18 sites of same-form code — "read the file stat → build a cache key → look up the in-process cache" —
and they are to be converged onto one shared primitive.

| Link | Artifact | Key decision |
|---|---|---|
| Blind run | Site table | 18 sites in three states: 13 true same-family / 5 form variants / **3 look-alike classes that must not be merged** |
| Requirements batch | Candidate plans | consumer view; candidate branches; landing-point decision (two plans rejected, reasons on file) |
| User adjudication | — | ambiguous sites go to the user for adjudication with the numbers in hand; objections recorded |
| Write-red P | **Independent commit** | per-family parameter points + domain-completeness lock; ambiguous sites get one claim frozen for each of the two interpretations |
| Convergence | Changes | 16 sites wired to a single-source primitive; **all 5 look-alike cases preserved** |
| P refresh | Refresh batch | pre-change frozen state → regression lock after convergence; red states are handed over, not fixed by the convergence side |
| QA Q | Q suite | expected keys independently reproduced with **low-level system calls**, **without going through the primitive under test** |
| Gate | Full run | — |

**The three actions most worth copying from this example**:

1. **Write-red as an independent commit** — when convergence goes red, one command returns to the baseline
2. **Handing over the P refresh** — the convergence side does not touch P artifacts, which keeps P6 intact
3. **Q independently reproducing expected values** — prevents circular reasoning

**And one counter-example**: what happens if the 3 look-alike classes get merged in passing —
each carries different semantics (freshness check / cross-run reconciliation / concurrency-lock protocol),
after the merge the readout is green and the behavior has already changed. **The blind run listing these three classes is the most valuable part of the whole report.**

---

## §10 Dispatch template (copy as-is)

```markdown
## Task
<one sentence: what this batch converges>

## Scope
- In the batch: <site list, each with file:line>
- Explicitly untouched: <site list + reason>
- Lock surface (do not touch): <golden frozen keys / adjudicated docstring / behavior contract surface>

## The iron rule of unchanged values
Output and on-disk bytes stay byte-identical. Serialization parameter forms pass through point by point; do not normalize the form.

## Your role
<write-red / converge / QA / blind run>

## Prohibitions
- <named one by one>

## Blind-run type
<functional-heuristic / contract-mode> (this batch's choice and reason)

## Red-state handling
Red → hand over to <role>; do not fix it yourself. Handover record path: <path>

## Output obligations
- Record on disk: <path>
- Mutation evidence: N lock-surface mutations + N implementation mutations
- Exemption surface declared explicitly (item by item + reason)

## Evidence discipline
Grade every conclusion: measured / inferred from code / unconfirmed. Bare numbers are forbidden.
```

---

## §11 Related files

| File | When to read |
|---|---|
| `SKILL.md` | deciding whether to use it, the six preconditions, three-level silence |
| `README.md` | why it is designed this way, when you want to change the tool, verification commands |
| `references/writing-claims.md` | when writing a Claim, criterion-strength table |
| `references/receipt-format.md` | delivery receipt fields |
| `references/test-alignment.md` | test alignment (advanced) |
| `references/phase-transition.md` | when turning a red-first baseline into a regression lock |
| `references/domain-mapping.md` | cross-domain applicability, when unsure whether to use it |
| `references/hooks.md` | host hooks |
| `CHANGELOG.md` | status of each adversarial technique, real failure records |
| `examples/forgery_poc.py` | permanent baseline: effective against sloppiness ≠ effective against deliberate forgery |

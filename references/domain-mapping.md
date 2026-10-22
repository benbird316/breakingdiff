# Cross-domain applicability

The authority for the decision is the "six structural preconditions" table in SKILL.md: the P1-P6 criteria, the P3 value statement, and the do-not-trigger list all live in the main document. This file answers one prior question: in another domain, what does each of the six preconditions look like, and where does it get stuck. It adds no criteria and relaxes none.

## The three main sticking points

Across domains the usual blockers are not P1, P3, P5 (these three differ little between domains) but the three below.

### P2 enumeration: compress the account from prose into parameter points

Programming domains come with structure: when a flag changes, it changed. Leave the programming domain and the account first lives in prose: clauses are sentences, claims are paragraphs, definitions are natural language. If you cannot flatten it, that is a P2 miss and you should not run.
Decision question: can each account get a stable identifier and a parameter key that can be queried point by point?
A clause table can; a paragraph cannot. "Article 3.2" can; "the overall spirit" cannot.

### P4 binarization: the relation lands true/false at every parameter point

Continuous quantities (effect size, percentage deviation) need the decision rule pinned down before running; pre-registration is exactly for this.
Tolerance is another pit: in floating-point equality, p-value thresholds, and similar cases, the tolerance itself is a third state chosen by hand — whether exceeding the tolerance counts as divergence depends on who chose the tolerance, and the tool cannot give this answer. The criterion fails before the readout does.

### P6 independence: whose hand did the N accounts come from

A new procedure copied from the old, an agent writing both docs and code, a review copied from another review — an agreement readout is evidence of self-consistency, not cross-verification. The tool still runs and still gives a readout; the readout is not extrapolated into correctness. Across domains P6 breaks most easily where it "looks like two things": the same person, the same pipeline, the same model session all count as same-source.

## Per-domain decision table

✓ means the domain's typical material pair usually satisfies it, not that it is exempt — every concrete case still goes through the six preconditions one by one.

| Domain | Typical material pair | P1 | P2 | P3 | P4 | P5 | P6 | Main sticking point |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| Programming | two versions of a config/contract snapshot; test claims vs frozen spec | ✓ | natural structure | ✓ | ✓ | ✓ | depends on the pipeline | P6 breaks when both versions come from the same refactoring pipeline |
| Research | claimed conclusions vs evidence list; two versions of an experimental protocol; pre-registration vs report | ✓ | holds once compressed into items | ✓ | pin the decision rule for statistics first | ✓ | usually good | run only on enumerable items; decide tolerance ownership for p-value cases first |
| Engineering/industrial | old vs new procedure; acceptance criteria vs deliverables; compliance clauses vs audit working papers; bill of materials | ✓ | (clause, object) | ✓ | binarize clause strength first | ✓ | depends on the revision chain | new standards are often revised from old ones; quantitative clauses carry tolerance |
| Theory (mathematics) | two definitions; two frameworks | ✓ | hardest, formalize first | ✓ | boundary counterexamples are binarizable | ✓ | depends on the school | if prose definitions cannot be flattened, do not run |
| Agent self-check | doc claims vs independent code extraction; CHANGELOG vs the actual diff | ✓ | holds once extracted into items | ✓ | existence is decidable | ✓ | naturally good but must be verified | docs and code generated in the same session count as same-source |

## Per-domain applicable and inapplicable forms

**Programming** (the baseline domain; criteria in the main text of SKILL.md)
Applicable: two versions of flagd/K8s configuration, two versions of an API contract, test claims vs a frozen spec.
Not applicable: the value unchanged but the meaning changed (`total_cents` from cents to yuan); what the parser/CI already blocks (P3 broken).

**Research**
Applicable: N claimed conclusions in a paper vs an item-by-item evidence comparison (only the part that can be compressed into items); pre-registered decision rules vs the final report's readout; two versions of an experimental protocol compared clause by clause.
Not applicable: evidence quality assessment (not a binary relation); effect-size comparison (a continuous quantity, unless the decision rule is already pinned in the pre-registration); opinion differences between reviews (the account is prose).

**Engineering/industrial**
Applicable: a procedure revision clause by clause (is the old clause still in the new version — lost, changed, moved); acceptance criteria vs the deliverables list; compliance clauses vs audit working papers; two versions of a bill of materials part number by part number.
Not applicable: automatically equating "should/prefer/may" strength changes (you must first pin the strength mapping into a decision rule); holistic judgments like "the new version's spirit is more conservative" (P2 cannot flatten it).

**Theory (mathematics)**
Applicable: two definitions counterexample-witnessed in the same parameter domain (are they equivalent at the boundary); an axiom list compared item by item.
Not applicable: correctness of a proof process (not a two-account comparison question); intuitive equivalence (P2 cannot flatten it).

**Agent self-check**
Applicable: interfaces/config items claimed in a doc table vs independently extracted from code (a list reconstructed by AST or grep, not a paraphrase); CHANGELOG claims vs the actual diff.
Not applicable: LLM paraphrase extraction (same model, same session = same-source, P6 breaks); doc tone vs code style (not a per-parameter-point relation).

## Per-domain Q sources

One sentence for the Q criterion: find an account this round's author cannot change (the strength tiers in test-alignment.md generalize across domains; here are the per-domain landing points).

| Domain | Strong Q (first-hand) | Weak Q (close to self-bootstrap, use with care) | Same-source trap |
|:--|:--|:--|:--|
| Programming | downstream call surface; real issues; the frozen previous spec | README promises written by humans | tests and implementation drift together |
| Research | pre-registration file (timestamp-locked); raw-data readouts | the paper's own methods section | a review copied from another review |
| Engineering/industrial | field execution records; audit working papers; the buyer's tender clauses | the revision notes shipped with the new procedure | revision notes copied from the body text |
| Theory (mathematics) | formalizations that are axiomatized and independently cited | the prose definitions of the original paper | a textbook copying the same original definition |
| Agent self-check | mechanical extraction from code/data (AST, grep reconstruction) | an LLM paraphrasing the docs | docs and code generated in the same session |

Universal floor: Q also has an oracle gap — what pre-registration omitted and the spec never mentioned is invisible to the tool. The end point is always a human.

## Equivalent forms of the trigger sentence

Each domain's example sentence in description is another way of saying the same trigger point:

| Domain | description example sentence | Equivalent form |
|:--|:--|:--|
| Programming | behavioral equivalence before and after a refactor | "is it still the same behavior after the change?" "the config survived the migration, right?" |
| Programming | test claims vs spec commitments | "did the tests hold the spec?" "do the claim account and the spec account line up?" |
| Research | claimed conclusions vs item-by-item evidence coverage | "is this conclusion backed by evidence?" "do the claims and the citations line up?" |
| Research | two versions of an experimental protocol compared | "what did the protocol revision lose?" "does the pre-registration match what was actually done?" |
| Engineering/industrial | old vs new procedure, clause by clause | "which old clause did the new procedure lose?" "revision review" |
| Engineering/industrial | compliance clauses, clause by clause | "is the clause still there?" "do the audit findings line up with the clauses?" |
| Theory (mathematics) | two sets of definitions counterexample-searched in the same parameter domain | "are these two definitions equivalent at the boundary?" |
| Agent self-check | doc claims vs independent code extraction | "the doc says it exists, does the code really have it?" "do the README and the implementation match?" |

## Hard boundaries

1. This file adds no criteria and relaxes no P1-P6. When decisions conflict, the six-precondition table of SKILL.md prevails.
2. The three sticking points are "decide before running", not "explain after running": if P2 cannot flatten, P4 cannot pin, or P6 cannot be independent, any hit means you should not run, rather than running and then using the sticking point to explain why the readout looks strange.
3. The ✓ in the decision table means "the typical material pair usually satisfies it"; for material pairs beyond the typical, go through the six preconditions item by item again.
4. The Q source table continues the floor from test-alignment.md: Q in any domain has an oracle gap, and an agreement readout is not extrapolated into correctness.

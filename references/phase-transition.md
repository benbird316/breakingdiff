# Phase transition recipe: pre_fix → regression_lock

This recipe answers one question: when a differential readout moves from a red-first baseline to a regression lock, which things move, in what order, and when they must not move. Phase transitions are entirely manual today, and two batches have already been redone; what is distilled here is the standard order and criteria, ready for the next differential suite to reuse.

## What the two phases are

| Phase | Readout status | What to do when red appears | When it applies |
|:--|:--|:--|:--|
| pre_fix (red-first baseline) | working readout, updated with changes | red is a signal: drive the fix, and the readout follows once fixed | development, while the account is still evolving |
| regression_lock (regression lock) | a fixed regression baseline | red is a block: a change broke a baseline commitment, check the change first, do not change the baseline | after the suite stabilizes, when the readout must serve as a gate |

To tell which phase you are in, look at "what you intend to do when red appears": if you intend to fix the object under test, you are still in pre_fix; if you intend to re-check the change you just delivered, you are already in regression_lock. Phase is a state in the operator's head; the engine has no such field (see Boundaries).

## Same engine, where the two phases differ

compare, the three gates, the receipt, and blind-write reconciliation are all shared by both phases; not a single decision semantic changes. The only difference is how expectations are treated:

- during pre_fix the account is evolving, claims_identity (each account's name/predicate/applies) may change every round, and reconcile reporting surprise is the correct signal for "expectation expired" — the expectation follows the account and is rewritten every round.
- during regression_lock the account is frozen and the expectation is fixed; surprise returns to being an anomaly and is always investigated as an incident.

So "turning the lock" has no switch to press at the tool level; three things must move: where the old readout goes, the P/Q semantic wording, and the expected file. Move them in the order below.

## Step 1: archive the old readout as differential history

Archive, do not delete. The last round's readout, report, and receipt before the lock are archived as a whole; the form follows the project's existing convention, and this recipe does not dictate directories or file names. The only criterion: **the readout at lock time must be retrievable from the archive byte for byte** — the receipt's verification subject is re-execution with a byte-for-byte comparison, and if the archive cannot preserve that property, the differential history is only shaped like an archive.

Why archiving is mandatory: after the lock, only differential history can answer "what the surface under test looked like when the baseline was locked, which items were out of domain" — without an archive, baseline legitimacy rests on memory, and memory cannot reconcile.

## Step 2: switch the P/Q semantic wording

What does not move: predicate, quote, source_tests, applies. Move any of these and it is no longer a conversion but a change of criterion — changing criteria has its own path, in the criterion template of Step 3, not here.

What moves: semantic labels and report wording. The reading of dominance switches from "the spec promised it, the test does not hold it, a coverage gap to fill" to "behavior the baseline promised was lost, a regression block"; divergence, common, and neither get the same item-by-item review: every semantic label that lands in the report must change from the tone of a working readout to the tone of a baseline commitment; the exact wording is decided by a human after seeing the numbers.

Why the predicate must not be changed along the way: claims_identity consists of name/predicate/applies; with the predicate unchanged the identity is continuous, and only then are the differential history and the lock-period readout comparable from the same source. Change the predicate and the two phases' readouts break the chain, and the archiving in Step 1 was for nothing.

## Step 3: migrate EXPECTED

Mechanism facts: the expected file is reconciled against run_kind, claims_identity, domain_digest, expected_counters with hard counter reconciliation, and any inequality is a surprise; the content-addressed written_marker of the expected content makes editing the expectation afterwards fail the check on the spot.

Migration path:

1. The old expected file is archived with the differential history, not deleted — its written_marker and the reconciliation chain with the already archived receipt survive.
2. Re-run write_expected with the post-lock account; the expectation lands before the readout, and blind-write semantics are unchanged. Note that run_kind has only two legal values, `pairwise|nway`, and encodes the readout family only; phase cannot and should not be expressed through run_kind.
3. The first reconcile inside the conversion window producing surprise is the expected signal (identity changed); archive it as "expectation expired". After the window closes, surprise returns to being an anomaly.

### Criterion template: neither=1 caused by predicate distortion means updating the readout is unreachable

Before letting the lock through, check the neither count:

| neither readout | Attribution | Treatment |
|:--|:--|:--|
| 0 | — | proceed with the conversion normally |
| >0 | a real divergence (behavior really changed, legal semantic drift) | decide after seeing the numbers, a human judges (next section) |
| >0 | predicate distortion (both predicates false on the same fact) | fix the predicate first; updating the readout to pass the conversion is forbidden |

Identifying predicate distortion: pair two calibration fixtures (known pre-change state + known post-change state); P and Q are both false on both fixtures — what lands in neither is not a third shape, but both sides failing to measure the fact. Calibration points do not enter the four-quadrant counts.

Why "updating the readout is unreachable": a distorted readout means the ruler itself is broken. Update it into the regression baseline and the broken ruler is fixed from then on; every subsequent regression check measures with it — what it blocks is no longer the regression but the ruler itself. Fixing the predicate changes claims_identity, so after the fix you must walk the three steps again; you cannot patch the expectation in place.

## Adjudication principle: the tool gives the recipe, it does not adjudicate for you

Whether EXPECTED changes, whether to lock or update the readout, whether neither counts as distortion or a real divergence — all are decided by a human after seeing the numbers. This recipe lists only criteria and steps and does not turn them into automation rules. Reason: once an adjudication error is fixed into the baseline by automation, the error gains executive power and repeats automatically at every conversion; a human deciding after seeing the numbers at least looks at the evidence anew each time.

## Boundaries

- **phase is not a first-class attribute.** Neither the engine, the receipt, nor the expected file has a phase field (run_kind has only `pairwise|nway`, and encodes the readout family only); phase exists only in the operator and in this document. Decide whether to make it a first-class attribute after a third consumer re-verifies.
- Until then, this recipe is an operating guide, not a code contract: no machine reads it, and skipping a step is not blocked by a tool. Retrieving the differential history byte for byte, fixing predicate distortion first, and the moment the conversion window closes all rest on the person executing the recipe.
- The recipe changes no gate semantics: the compare/compare_n decision structure, the three gates, and the two tiers of blind-write reconciliation all stay as they are.

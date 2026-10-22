# Blind run: what a failure means, and what to learn from it

This directory holds one task sheet ([`brief.md`](brief.md)) and one question:

> Can an agent with **no context**, reading only `SKILL.md`, get this tool actually
> running and produce a readout that does not step past its own evidence?

The run is single-arm and it measures a **usability floor**, not the engine's quality.
A failure here is not a verdict on the tool — it is a pointer to one specific thing
that was not learnable from the material the reader had.

The scoring table is organizer-side material and is not published: publishing it ends
any future blind run. This page is the part that survives publication — **a failure
atlas**, because every failure shape has somewhere to go and learn.

---

## Four failure shapes, four different lessons

| # | What the run looks like | What it means | What to learn | Where to read |
| :- | :--- | :--- | :--- | :--- |
| 1 | Reads both materials, writes a comparison from memory — no `compare()` anywhere in the transcript | The trigger never fired. Either P1–P6 were never checked, or the sentence "how do these two relate" was read as a line diff | The trigger is a **claim about a relationship**, not an instruction the user gave; a read-through is not an account | `SKILL.md` "When to use, when not to" · [`examples/trigger_conditions_test.py`](../../examples/trigger_conditions_test.py) |
| 2 | Runs the tool, gets a readout, then states a conclusion that the readout cannot support ("essentially the same" over four divergence points) | The readout was treated as decoration. The tool did its job; the reader stepped past it | **Divergence ≠ better.** A conclusion must name the witness it rests on, point by point | `SKILL.md` "Divergence ≠ better" · [`casestudy/k8s/`](../../casestudy/) (baseline flip: removals land in divergence, not dominance) |
| 3 | Readout is well-formed and means nothing: `all_true` 100%, or all zeros, or one common point and no differences | A **degenerate readout**. Two very different causes: the accounts were never aligned (extraction), or the probe never reached the artifact | Each layer has a signature. Learn to recognise the shape before trusting the number | [`casestudy/pdg/`](../../casestudy/) (selection modes come out green with **no attribution**) · [`casestudy/llama/`](../../casestudy/) (all zeros is **quieter** than green) |
| 4 | Hundreds of red points on data that is fine | The claim is **stronger than the data's occurrence pattern** — a design choice, not a data defect | Strength follows the occurrence pattern; band width is a decision, and it must be declared | [`casestudy/malecns/`](../../casestudy/) (same data: bands flag 12, point-value claims 2,720) · [`references/strength.md`](../../references/strength.md) |

A fifth shape is not a failure of the reader at all: the readout is **refused**
(`READING_DISCRIMINATION_ZERO`, `CoverageError`). That is the gate working — the
domain could not support the criterion, so it declined to certify instead of
reporting zero. See [`casestudy/k8s/`](../../casestudy/) §3 and
[`casestudy/TEACHING-k8s.md`](../../casestudy/TEACHING-k8s.md).

---

## Triage: is it the document, the reader, or the tool?

Three questions, in this order. Do not fix anything before the answer is known.

**1. Did it trigger at all?**
Not triggering while P3 plainly holds ("the change is legal and raises nothing") is a
**document** defect, not a reader defect: the trigger sentence failed to describe the
moment. Fix `SKILL.md`'s trigger, not the reader's judgement. If P3 does *not* hold,
not triggering was correct and the material was badly chosen for a blind run.

**2. Did it trigger but talk past the readout?**
Then the tool was right and the reader was wrong. This is the failure worth *teaching*
rather than fixing: the tool already produced a witness, and the witness was ignored.
Material to add is an example, not a rule — `k8s` is the one that shows a reader
assuming the wrong column reporting the additions and missing every breaking change.

**3. Was the readout degenerate — and if so, which kind?**
- all green / no attribution → accounts not aligned → `pdg`
- all zeros → evidence extracted wrong, or probe never reached the artifact → `llama`
- all red on true data → strength above the occurrence pattern → `malecns`
- **refused** → the gate declined; that is a pass, and reporting it as "zero problems"
  is the failure

Degenerate readouts are the reason this repository keeps saying **a zero readout is not
a pass**. If the run reports a clean zero without asking "would this readout move if the
change were wrong", the lesson is
[`SKILL.md`](../../SKILL.md) "Three-level silence", not the case studies.

---

## What to do after a failed run

1. **Name the shape** (one of the four above) before touching any file.
2. **Reproduce once.** A shape that appears in two independent runs is a document
   defect and belongs in `CHANGELOG.md` under the mechanism it produced. A shape seen
   once is reader variance — record it, change nothing. Two runs is the threshold
   because one run cannot tell "the document misled me" from "I read carelessly".
3. **Fix one layer only.** The temptation is to add a rule to `SKILL.md` *and* a warning
   to the tool. Adding both produces a skill nobody can afford to load and a tool with
   duplicated policy.
4. **Re-run the same brief unchanged.** Changing the brief after a failure hides the
   question. If the material was contaminated (overlapping a published corpus), void the
   round and say so — that has happened once here, and the void is recorded rather than
   quietly re-scored.

---

## Why a failed blind run is worth publishing at all

Because the failure shapes are the product. A reader who can name which layer broke can
get a useful readout out of this tool with no support at all; a reader who cannot will
produce a confident paragraph that means nothing, and it will look exactly like success.

That is also why this page names no scores: the number would invite optimisation against
the number, and the thing being measured is whether the reader stayed inside the evidence.

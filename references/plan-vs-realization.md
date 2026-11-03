# Plan vs realization: freezing one side of the comparison

A change can raise no error and still leave two accounts of it: the plan written
before the work, and the artifact that landed after. This article is the method
for comparing them. The runnable instance is `examples/plan_vs_realization.py`;
the regression test next to it is the executable form of the same method.

## When to use it

Use it after a change has landed, when the question is not "did it crash" but
"does what landed match what was promised". Two accounts only mean something if
one of them could not have been rewritten after the other existed. That is what
the freeze is for.

## Write the two claims

One claim per side, over one shared parameter domain. The domain is the set of
points at which both sides can be asked a yes/no question — for a command line
that is the flag list; for a port it is the behavior under test.

- P (realization): what the landed artifact actually does at each point.
- Q (plan): what was promised at each point, frozen before the work began.

Each claim carries provenance: the source, a verbatim quote, and the full text
the quote was taken from. The quote is checked verbatim at construction, so a
paraphrase cannot stand in for the sentence it claims to cite. Give each claim
source_tests: a tuple of (point, expected) pairs the predicate must reproduce,
so the account cannot silently drift from what the source says.

## Freeze the plan

Record the plan's identity before the work starts, in either of two forms:

- digest: `sha256:<hex>` over the plan text; recomputed at compare time.
- commit: the full 40-character lowercase hex sha that already pins the text,
  together with the pinned text.

The commit form is accepted as it is. A commit already pins the content, and
demanding a digest on top would be tighter than the exception needs to be.
Either form supplies independence; neither is preferred.

At compare time the freeze is verified first. If the plan was amended after the
freeze, the check raises before any number is printed. An amended plan is a new
round: freeze the edited plan, then compare. Do not carry the old freeze over.

## Read the four quadrants

- common: promised and landed. The plan held on this point.
- dominance: promised, did not land. The plan's shortfall; this column is the
  product when the question is whether the work kept its promise.
- divergence: landed, was not promised. Work outside the plan. "Different" is
  not "better"; it is another account, to be read, not scored.
- neither: absent from both accounts.

The verdict key is stable across wordings: p_strict_contains_q, q_strict_contains_p,
parallel, equivalent, disjoint. Translate the wording, not the key. A readout with
both dominance and divergence non-zero is parallel — the two accounts are
different accounts, not a ranking.

## Report language

State how independence was obtained. With a valid freeze, the status line is
`contract vs realization`: the plan side was fixed before the artifact existed.
Without a freeze, the pair is `same-source self-consistency`: one hand wrote both
accounts and could have written them at any time. That is a legitimate check of
internal agreement, and it is not verification. Keep the distinction in the
report even when the numbers look identical — a passing four-quadrant readout
from a same-source pair says nothing about whether the plan held, and reading it
as verification is the one thing this method stops.

A freeze mismatch is reported as a mismatch, never as a result. Re-freeze the
amended plan and run again; a mismatch is not a zero.

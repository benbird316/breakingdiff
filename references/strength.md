# strength — decide how strong a claim is

A claim is not just "what is asserted"; it also declares **how much natural variation is
allowed**. A point value or a hard equality hides that tolerance instead of stating it.
Choosing the strength is a separate decision from choosing the account, the domain, or the
predicate, and it is a separate failure source.

## The failure this prevents

Same data, same comparison domain, only the shape changes: a bounded band flags 12 points, a
point value 2,720, hard equality 4,354. No error is raised, the construction gates pass, and
the readout looks strict. Enumerating the accounts and the domain correctly can still produce
a readout that is all false red — true data read as bad data.

## The operational loop

1. **State the data's occurrence pattern** — how much variation is normal for this domain.
2. **Pick the shape** — by the drift you want to catch, not by what is easy to write.
3. **Give the band width a provenance** — and record which kind of provenance it is.
4. **Preregister** the claim's strength before looking at the readout.
5. **Run the error-mode ladder** and freeze the staircase.
6. **Register the exit** — which points may flip, and why.

## Shapes

| shape | what it asserts | typical domain | degenerate failure |
| --- | --- | --- | --- |
| existence | the point is in the measured set | every account has it | everything true, nothing guarded |
| bounded band | a value stays inside a declared band | counts with natural variation | band so wide it never alarms |
| point value | the value equals a computed expectation | exact arithmetic, config keys | false red wherever nature varies |
| hard equality | two sides are equal | exact mirrors, hashes | false red on every asymmetric point |
| ordinal | the order between two values holds | rankings, ratchets | noisy when the gap is small |
| share | a proportion clears a threshold | composition, majority rules | threshold picked by taste |

## Band width provenance

| provenance | example | what it buys |
| --- | --- | --- |
| design tolerance | ±30% chosen and declared by the designer | reproducible, never measured |
| same-data quantile | width derived from the dataset's own spread | self-consistency only — the low false-red rate is by construction |
| external anchor | published cross-dataset variation | transferable, costs a citation |

If the width and the data come from the same source, say so in the record. A low false-red
rate is then evidence of self-consistency, not of generalization.

## Preregistration record

Keep it with the case (for example in its corpus manifest): claim key, shape, band width,
provenance kind, allowed flips with a reason each, and who reviewed it. Without this record a
tuning session can always be re-read as a success after the fact.

## The error-mode ladder

Before a gate depends on the claim, run the same data through bounded, point-value and
hard-equality shapes, and freeze the resulting staircase as a regression test. If the ladder
does not move when the strength changes, the claim's strength is decorative.

## Boundaries

- Strength cannot rescue a domain with no observable window: if nothing can be measured, no
  band width helps — fix the domain first.
- The domain's caliber is part of the strength: a wider comparison domain (extra sides, extra
  categories) manufactures false red on its own.
- The band width is not unique. Changing it moves the readout, and that is the point: a band
  whose readout does not move is decoration.

## Worked case

The measured staircase and the registered exits are in `casestudy/TEACHING-malecns.md`; the
three error-mode fingerprints are frozen in that case's test.

Re-run the ladder with `scripts/strength_calibration.py`; its test carries the malecns
fixture (12 / 2,720 / 4,354 / 241) and skips with a named reason when the corpus is absent.

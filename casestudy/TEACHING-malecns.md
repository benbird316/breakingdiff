# Claim strength

> This is not a report on "what the tool can do". It is a lesson in **how strong your claims need to be**.
> The data is good; the claims read it red — this lesson walks that road once, all measured readouts, not statements.
>
> Scripts:
> - `malecns/aligned.py` — the selection where the accounts are aligned **and the strength is right**: three bounded bands + an existence baseline
> - `malecns/misaligned.py` — three **strength error modes**, each with its measured false-red surface
> - `malecns/test_aligned.py` — 24 assertions over frozen criteria (corpus anchors + fingerprints + readout reconciliation + two-read-path reconciliation)
> - `malecns/fetch_corpus.py` — downloads the corpus (GCS direct link, resumable, about 56 MB)
>
> ★ The directory is movable: the scripts search **upward** for `scripts/breakingdiff.py` (same reason as in the pdg lesson).
>
> How to run:
> ```
> cd malecns
> python fetch_corpus.py       # once
> python aligned.py
> python misaligned.py
> python test_aligned.py      # 24 assertions, all should be green
> ```

---

## 0. Why this deserves a lesson of its own

The pdg lesson teaches the **data-extraction layer** (whether the accounts are aligned); the llama lesson teaches the **probe layer** (what a degenerate readout looks like).
This lesson is the third pit: the **strength layer** — even with the accounts selected right, the domain enumerated right, and the predicate bivalent-decidable,
everything can still be wrong, and wrong in **a strength shape that does not match the data's occurrence pattern**.

Same batch of true data, same comparison domain, only the claim strength changes:

| Claim shape | Points flagged false | Share | How the readout looks |
|---|---|---|---|
| bounded (P1 ±30% count band) | **12** / 22,176 | 0.05% | 12 suspicious points worth a human look |
| point-value (n = type total // 2) | 2,720 / 22,176 | 12.3% | true data looks like bad data |
| strict equality (nL = nR) | 4,354 / 22,176 | 19.6% | one fifth of the domain is alarming |

**Did anything raise an error? Not one.** All three gates (provenance / self-test / discriminating power) pass and the readout shape is entirely normal.
A strength error mode is perfectly legal in the verdict logic — what is broken is the claim shape, not the execution.
That is why it is quieter than a data-extraction error mode: there is not even an abnormal share like "58% judged false" (pdg's error mode 1),
only a field of red that "looks strict".

---

## 1. The corpus: why MaleCNS

The public MaleCNS v0.9 release from Janelia flyem (GCS direct link, no authentication):
**211,743 body-annotation rows (the official proofread neuron account is 166,691 — Cell 2026, main issue;
annotation rows include fragments, glia, and unannotated segments) + 1,836,293 rows of transmitter predictions**,
and every feather carries a type label and a somaSide (L/R/M) side. It is the perfect shape for the strength layer:

| N-account element | Counterpart in MaleCNS |
|---|---|
| Surface under test | Neuron counts across type × hemisphere, and the transmitter composition of a type |
| N accounts | P1 count band / P2 symmetry band / P3 composition band / Q existence (+ three error modes) |
| Parameter points | The (type, somaSide) existence points, 22,176 of them, sorted |
| Predicate | Count / difference / share against a band |
| Occurrence pattern | Drosophila hemisphere development: most types mirror exactly, a few are left-right unequal (true within the data, cause to be adjudicated) |

The key property: **"most points ought to pass" has a biological basis** (mirror development), and **"the points that ought to flip" really exist**
(2,030 types with unequal sides, 16 types whose main transmitter does not reach half). That is exactly what makes it a touchstone for strength:
get the claim strength slightly wrong and the false-red surface grows by a block — and the staircase can be recomputed mechanically.

### The read path (including one premise that was disproved, worth recording)

Both feather files are ARROW1 (Feather V2). **Measured on pyarrow 25.0.1, both tables read directly** —
an early probe reported "Lz4 compressed input contains more than one frame" and on that basis wrote
"all three paths rejected"; a reviewer's retest disproved it (the transmitter table is in fact one buffer with exactly one frame, plus block-dependent lz4).
The lesson stands: **retest the premises of a read path; do not write a one-off environment failure down as a data fact.**

`aligned.py` still parses Arrow IPC itself (hand-decoding the footer/schema flatbuffer — a field slot is two indirections away;
lz4 blocks need frame decoding, with the first 64 KB of output serving as the history window). The reason is not that pyarrow cannot read it
but **read-path autonomy**: the readout does not hang on a third-party library's version behavior, it runs with zero dependencies,
and it checks the decompressed length buffer by buffer, blowing up on the spot if it reads wrong. The decoder and pyarrow reconcile
cell by cell on every column of both tables (the reconciliation cases in test_aligned.py); the two read paths are each other's reconciliation.

★ The hash-anchor lesson: computing SHA256 mid-download captures an incomplete state (the first probe run recorded one false anchor).
`fetch_corpus.py` accepts only the double condition "byte count matches + per-chunk SHA256 matches";
otherwise it keeps the `.part` file for resuming and exits explicitly.

---

## 2. How to select: bounded

`malecns/aligned.py`, four accounts:

### Step 1: take existence points for the domain; do not make "absence" the object of a claim

```python
CRITERIA = sorted(existence points of (type, side))   # 22,176 of them
```

Domain = non-empty type in the annotation table × somaSide ∈ {L,R} × count > 0. The M side (392 bodies) and
the side-less rows (60,748 bodies) do not enter the domain — hemisphere symmetry is undefined for them.
**The domain account is itself part of the strength**: mix the M side into the comparison domain and
R1-R6 (the photoreceptor type with 3,364 M-side bodies) gains a whole block of false red out of nowhere.

### Step 2: Q is the existence baseline; being always true is the design

```python
predicate=lambda x: x in load_counts()
```

An anchor that is always true on the domain. Whether it holds is computed by the predicate on the real domain, not guaranteed by a gate
(the boundary statement in SKILL, verbatim). The error-mode scripts use it as the control arm: under N=2, the number of points
where "Q alone is true and the error mode alone is false" is the false-red surface.

### Step 3: three bands, each with its own sourced width

| Account | Rule | Where the band comes from |
|---|---|---|
| P1 count band | \|n − n0\| ≤ max(1, ceil(0.30×n0)); for two-sided types n0=(nL+nR)/2, for one-sided types n0 = the full complement | **design tolerance** (dimension = the within-dataset left-right difference distribution) ∩ data self-report (median count 3 / maximum 3,377, so the width must be relative). Note this is not Schlegel 2024's ~30% — that is cross-dataset individual variation between FlyWire and hemibrain, a different dimension that cannot be cited. For two-sided types \|nL−n0\|=\|nL−nR\|/2; P1 and P2 are the coarse and fine grades of the same statistic, and this band is three times looser than P2 with only 0.05% false red — conservative and harmless |
| P2 symmetry band | \|nL − nR\| ≤ max(2, ceil(0.10×(nL+nR))) | a band floor of 2 absorbs small-sample counting noise; the 10% relative band lets a small proportional difference in a large type through |
| P3 composition band | the voted main transmitter's share ≥ 0.5 | a "main" transmitter must cover more than half the members; the voting account = per-body votes on predicted_nt (unclear counts as a vote, a tie takes the lexicographically largest — 136 tied-vote types make that rule discriminating) |

Three details decide whether the band is "built right":

- **Do not force "half" onto one-sided types**: a one-sided type is not a two-sided one; its expectation is the full complement,
  and forcing half only manufactures 294 false reds (their left-right difference belongs to P2, not P1).
- **Keep the M side out of the baseline**: one root cause of error mode ① is taking a type's total body count (M side and side-less included)
  as the expectation for half of a two-sided type.
- **Do not judge a type false when it has no transmitter row**: P3 lets types without evidence through — no evidence ≠ a violation.

All three gates actually run: source-test self-check P1 3/3, P2 2/2, P3 3/3, Q 2/2; in the discriminating-power gate each band
carries one "reading variant" (P1 point-valued / P2 strict-equality / P3 unclear dropped), with 2 / 1 / 1 points of measured discrimination —
the variants are not decoration, they are proof that "change the reading and the readout changes"; on coverage, out_of_domain is 0.

---

## 3. How not to select: three strength error modes

`malecns/misaligned.py`. **Each one comes with its measured readout.**

### Error mode ①: point-value claim — the band width pressed to zero

```python
predicate=lambda x: counts[x] == totals[x[0]] // 2   # ✗ exactly matching "half of the type's total body count"
```

Two diseases stacked: **the baseline is contaminated** (R1-R6's 3,364 M-side bodies push the expectation to 1,688,
while its L side has only 4 bodies); **the baseline is a point** (left-right counts generally sit away from half of a two-sided total —
12.3% of the true data points miss the exact value).

Measured: all_true 19,456 / pioneer {Q: 2,720} — **false-red surface 2,720 points (12.3%)**.

### Error mode ②: left-right strict equality — the most deceptive

```python
predicate=lambda x: counts[(x[0], "L")] == counts[(x[0], "R")]   # ✗
```

Drosophila hemispheres are indeed highly mirrored (8,911 types with equal sides; strict equality passes 80% of the points) —
that is exactly its deceptiveness: most of it comes out green and looks "basically right". But counting noise of ±1–2
and the 2,030 left-right unequal types make it flag 4,354 points false, and its largest |L−R|=189 (KCab-s
L=234/R=423) is **alarmed exactly like** ±1 noise — the signal drowns in the noise.
KCab-s's difference is recomputable within the data and its cause awaits adjudication: pooled across the four KCab* subtypes,
L=885/R=925 is near-symmetric while the subtypes are inversely unbalanced among themselves (s: R≫L; m/c: L≫R); FAFB KCab
is symmetric at 844L/799R, and KC has no known asymmetric type — the subtyping/annotation-artifact explanation dominates.

Measured: all_true 17,822 / pioneer {Q: 4,354} — **false-red surface 4,354 points (19.6%)**.

### Error mode ③: neuron-level top-1 written straight into the type level — account-granularity confusion

```python
predicate=lambda x: fr[x[0]][0] == fr[x[0]][2]   # ✗ voted top-1 == the data's self-reported type-level label
```

The transmitter prediction is **neuron-level**: per-body votes aggregate into a top-1 (unclear counts as a vote and pushes it out —
R1-R6 votes unclear 2,627/3,377 while its self-report is **histamine**, and photoreceptors are histaminergic to begin with),
whereas `celltype_predicted_nt` is the data's self-reported **type-level** label. Both granularities have their uses,
but set them equal and you get 138 types in disagreement and 241 domain points flagged false.

Measured: all_true 21,935 / pioneer {Q: 241} — **false-red surface 241 points (1.1%)**.

### The strength staircase (mechanically recomputable)

```
account confusion 241  <  point-value 2,720  <  strict equality 4,354     (three error modes)
bounded 12 / 110 / 20                                                     (the three aligned bands)
```

The staircase itself is a **strength gauge**: the size of the false-red surface = how far the claim strength exceeds the data's occurrence pattern.
test_aligned.py pins all three values and every pairwise inequality, so the document and the code cannot drift.

---

## 4. Diagnostic moves (the reusable part)

Strength error modes raise no error; you must recognize them from the readout shape yourself:

| Readout shape | Meaning |
|---|---|
| false-red surface share >5%, out_of_domain 0, no error | strength mismatch (point-value / strict equality) — first check whether the band width is 0 |
| changing the band width on the same domain changes the false-red surface a lot | the band is doing work; if it does not move, the band is decoration |
| every failure point of the band lands on a point with real structure | the band is built right (all 110 of P2's points are left-right unequal types) |
| the band's failure points land on structurally normal points | the band is not built right — check baseline contamination (error mode ①'s M-side disease) |
| the three error modes' staircase is pairwise unequal | the strength gauge works; equal or inverted = some error modes are actually equivalent |

**Baseline comparison (memorize this)**:
- aligned three bands: 12 / 110 / 20 (each failure point can be named down to real structure)
- point-value: 2,720; strict equality: 4,354; account confusion: 241

P2's 110 failure points break down as 92 points of two-sided unequal types + 18 points of one-sided types (one-sided =
maximal asymmetry, R=0, and falling outside the band is a real readout). The two largest: KCab-s (189),
KCab-m (84) — the left-right count difference is true within the data and its cause awaits adjudication (see §3); this is exactly what this
account is meant to send to a human.

Among P1's 12 failure points is a run of `*_unclear` types (LO_unclear L=11/R=3,
ME_unclear L=22/R=4, LoVP_unclear L=10/R=2) — these types' left-right counts are extreme in themselves
(whether that is a tissue abnormality is for a domain expert to adjudicate); the band singles them out
instead of drowning them among two thousand false reds.

P3's 20 failure points fall on 10 types, of which MeVP5 (votes unclear 0.41,
self-report acetylcholine) and TmY14 (votes glutamate 0.44, self-report unclear) hit
both "below half" and "account disagreement" at once — a double witness.

---

## 5. Final readout

### aligned.py (N=4, domain 22,176 points)

```
account                                    pass   false red  verdict
P1 count band (two-sided half ±30%)      22,164        12  narrowed to a readout (AVLP120.L, ER3w_a.R…)
P2 hemisphere symmetry band (≤max(2, 10% two-sided complement))  22,066  110  narrowed to a readout (AN05B078.L, KCab-s…)
P3 composition band (voted main transmitter ≥0.5)  22,156  20  narrowed to a readout (AVLP548_b, CB3013…)
Q existence baseline                     22,176         0  existence anchor (always-true is the design)

Shape statistics: all_true 22,048 / all_false 0 / split 10
  outlier ← P2 (98 points flagged false by it alone)   outlier ← P3 (18 points)   pioneer ← Q (2 points false on all of P1/P2/P3)
out_of_domain skipped 0
```

all_false 0 = the bounded bands did not read the whole true data as red; all_true < total = the bands are not decoration.
Outlier attribution means "this band alone flags this point false" — the 98 points only P2 flags false are
**medium asymmetry** (P1's ±30% tolerates them, P2's 10% does not):
two rulers of different coarseness measure different depths of the same phenomenon.

### Representative types, cell by cell (frozen by the tests, reconciled cell by cell by the implementation)

| Type | nL | nR | Voted main transmitter | Share | Data self-report |
|---|---|---|---|---|---|
| KCab-s | 234 | 423 | dopamine | 656/657 ≈ 0.9985 | dopamine |
| R1-R6 | 4 | 9 | unclear | 2,627/3,377 ≈ 0.7779 | **histamine** |

KCab-s is P2's best witness (|Δ|=189); R1-R6 is account confusion's best witness
(the vote's unclear displaces the true main transmitter histamine — whether unclear counts as a vote is made
explicit by P3's reading variant: unclear counted vs dropped, the two accounts disagree on 22 domain points
(11 types × 2 sides); all 20 points the main account flags false are rescued by the variant (FS4A 0.49→0.82,
LHAV4a4 0.41→0.58), and the variant alone flags 2 points false (Pleural remotor/abductor MN,
unclear 0.79 passes the band, dropped it gives histamine 1/3) — there are live witnesses in both directions).

★ Read the dopamine row for KCab-s with a warning: KC is textbook cholinergic (VFB/FAFB explorer ACh@100%),
and the official v1.0 curation layer's consensus_nt has already changed the whole KC line to acetylcholine — the
`celltype_predicted_nt` this table reads is the **model layer**, so "votes = self-report" ≠ "= biology". When the model layer, the curation layer,
and the textbook disagree across three layers, the outlier is the signal: a deeper layer of this case's account lesson.

### Mutation evidence in `test_aligned.py`: 24 assertions, all green

| Assertion class | Behavior pinned down |
|---|---|
| corpus anchors, 6 | independent recomputation with pyarrow: row count / column names / SHA256 / somaSide distribution / domain facts / the w1 false-red point |
| fetch + manifest, 6 | the download set is exactly two feather files (tbar is barred); the four-field manifest discipline; hash / row count / every cell of the readout table anchored to a measured value |
| aligned invariants, 4 | exactly 4 accounts; out_of_domain 0; all_false 0 (the bands do not read the data as red wholesale); all_true < total (the bands are not decoration); Q always true; every P2 failure point lands on a real asymmetric point |
| error-mode fingerprints, 4 | the three error modes have exactly 2 accounts, Q in place, false-red surface = the frozen value; the staircase 241 < 2,720 < 4,354 reconciles with the manifest |
| readout tables, 5 | load_counts equals the test's full recomputation item by item; the representative types cell by cell; the two NT accounts' readouts anchored (138/16); the transmitter table's in-house reader vs pyarrow, all 10 columns cell-for-cell equal |

---

## 6. Conclusion

### 6.1 What holds

**On a real external corpus, the bounded account shrinks the false-red surface by two orders of magnitude, and the failure points
it narrows down to can each be named against real structure.** The strength staircase (241 < 2,720 < 4,354) is mechanically recomputable;
"bounded fits the occurrence pattern (band width is a design choice)" rests on that staircase, not on a statement.

### 6.2 What does not hold (and must be said in the same breath)

| What the measurements prove | What they do **not** prove |
|---|---|
| the bounded readout shape is healthy (not false red all over, not decoration) | that the band parameters (30%/10%/0.5/floor 2) are the only correct values |
| the three error modes' staircase is recomputable | that the staircase order holds for other datasets |
| points outside the band deserve human review | outside the band = bad data (divergence ≠ better) |

The band parameters are a **design choice**: their sources are written into the account declarations (the §2 table), and what the source-test self-check
and the discriminating-power gate pin down is the **shape** — "the band narrows down to a readout and its failure points land on real structure" —
not the parameter values themselves. Change the parameters and the readout changes — and that is precisely the point: **when the parameters change, the readout must
change with them; a band whose readout does not move with its parameters is a decorative band** (diagnostic move 2).

### 6.3 Boundary statements

- **Outside the band ≠ bad data.** An outlier only says "this account does not hold at this point".
  KCab-s's 189 is true within the data (the left-right count difference is recomputable); it is not a read error, and
  the cause awaits adjudication — pooled across the four KCab* subtypes L=885/R=925 is near-symmetric, the subtypes are
  inversely unbalanced among themselves, FAFB KCab is symmetric at 844L/799R, and KC has no known asymmetric type;
  the subtyping/annotation-artifact explanation dominates.
- **The tool does not know whether the vote or the self-report is right.** R1-R6's histamine (self-report) and
  unclear (vote) disagree in 138 places; this case only reports where they disagree, and the right to adjudicate belongs to a domain expert.
- **The domain account is a human judgment.** The M side stays out of the domain; a one-sided type expects the full complement —
  get either decision wrong and the readout is wrong with it, while the tool stays all green.
- **The reason for the in-house read path is read-path autonomy, not that pyarrow cannot read it** (measured on pyarrow 25.0.1,
  both tables read directly; the early "all three paths rejected" premise has been disproved by a reviewer and is on record);
  the decoder has been reconciled cell by cell with pyarrow on every column of both tables, but "the in-house reader has no bugs"
  holds only for the columns that were reconciled.

### 6.4 In one sentence

> The engine is responsible for "what value your predicate takes at each parameter point".
> How strong the predicate needs to be is your job — **when claim strength exceeds the data's occurrence pattern, true data is
> read as bad data; a band width is not slack, it is how you "declare what normal is".**

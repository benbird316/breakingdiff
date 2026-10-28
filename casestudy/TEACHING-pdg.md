# Account alignment

> This is not a report on "what the tool can do". It is a lesson in **how you make N accounts line up**.
> Every conclusion comes with two runnable scripts, and what they output is a measured readout, not a statement.
>
> Scripts:
> - `pdg/aligned.py` — how to select when the accounts **are aligned**
> - `pdg/misaligned.py` — four ways the accounts can be **misaligned**, each with its measured readout
> - `pdg/test_aligned.py` — breaking the aligned sample must turn the tests red (34 assertions)
> - `pdg/fetch_data.py` — verifies/recovers the corpus (pinned PDG 2024, 7,593,984 bytes; **never downloads**)

★ The directory is movable: the scripts search **upward** for `scripts/breakingdiff.py`,
they do not hard-code "how many levels up". This rule came out of an actual migration —
the code first sat one level deeper and moved to `casestudy/`, one level up,
and a hard-coded depth immediately became a ModuleNotFoundError; the last thing a case study
can afford is "it won't run somewhere else and you can't find out why". When the file is missing, the script exits explicitly and states what it requires.

How to run it:
```
cd pdg
python fetch_data.py        # verify the corpus identity (edition/schema/rows/bytes/SHA256; missing → recovery steps)
python aligned.py
python misaligned.py
python test_aligned.py     # 34 assertions, all should be green
```

---

## 0. Why this deserves a lesson of its own

What an N-account diff engine does is easy to misread as "throw N claims in and compare them".
What actually decides how much information you get is **whether the N claims you picked are answering the same question** — that is, **whether the accounts are aligned**.

In code this comes down to four characters: **P1** (every account covers the same purpose), **P2** (the accounts can be enumerated into a finite set of parameter points).
They are where all the value lives, and they are **the one thing the tool cannot verify for you**.

This lesson uses a real corpus (PDG 2024 SQLite, 18064 measurements) to turn that into a reproducible controlled experiment:
same engine, same batch of criteria; the only thing that differs is whether the accounts are aligned — and that alone makes one run give a meaningful attribution and the other give all green.

---

## 1. The corpus: why PDG

The authoritative compilation that the Particle Data Group publishes every year contains a class of data like this:
**the same physical quantity, measured independently by dozens of different experimental groups**, each with its own uncertainty.

That is close to the perfect shape for N accounts:

| N-account element | Counterpart in PDG |
|---|---|
| Surface under test | The real part of a nuclide level energy (`description = 'REAL PART'`) |
| N accounts | The independent measurements of each experimental group (17 of them, each with a `pdgid`) |
| Parameter points | Statistical criteria 1σ / 2σ / 3σ / 4σ / 8σ |
| Predicate | Whether the difference between that measurement and the baseline is ≤ its own error × nσ |
| External anchor | The row with the smallest error (a proxy for the value PDG adopts) |

The key property: **the criterion is anchored externally; this skill does not define it**.
That sidesteps the self-justifying loop of setting your own question and answering it — the only reason this case study is worth doing.

### 1.1 Corpus version: pin PDG 2024, do not drift with upstream

Every readout in this case was measured on the **PDG 2024 sqlite that ships with the case**, and `fetch_data.py` pins that identity:

| Field | Pinned value |
|---|---|
| edition | `2024` |
| citation | S. Navas et al. (Particle Data Group), Phys. Rev. D 110, 030001 (2024) |
| schema_version | `0.2` |
| pdgdata rows | 18,064 |
| file size | 7,593,984 bytes (about 7.59 MB / 7.24 MiB) |
| SHA256 | `a925777f…fd532e` (full value in `fetch_data.py`) |

`python fetch_data.py` performs **verification/recovery**, not download: if the file is
present it checks every fact (edition / citation / schema / rows / bytes / SHA256) and
exits non-zero on any mismatch; if it is missing it prints the recovery steps and the
SHA256 anchor, then exits. `aligned.py` / `misaligned.py` run the same structural guard
(edition/schema/citation/rows) before reading data, so bypassing `fetch_data.py` directly is
still blocked.

**Why not fetch 2026:** the online upstream edition is now 2026 (edition=2026, schema 0.3,
19,587 pdgdata rows, about 25.75 MB), and the 2024/2025 URLs now return 404.
2026 is not a new snapshot of this corpus; it is **different data** — the assertions and
the 17-account table below were all measured on 2024. Silently swapping the corpus would
swap the conclusions, and no script would raise. Migrating to 2026 is a **future item**:
it has to change the assertions, the readout table and the teaching narrative together,
which a fetch script cannot decide on its own.

> The old doc's "about 7.6 MB" was once attached to the 2026 download URL and was wrong:
> 7.6 MB is **this 2024 file**; the 2026 edition is about 25.75 MB. The numbers are now
> the exact byte count plus both unit bases, so the two cannot be confused again.

---

## 2. How to select: align the accounts

`pdg/aligned.py`, in three steps:

### Step 1: Converge on the **physical quantity**, not on the database structure

```python
TARGET_DESC = "REAL PART"
```

This is the most important line in the whole script. `REAL PART` matches 17 records in PDG, all independent measurements of **the same real part of a nuclide level energy**,
spanning 1517–2234 MeV, each with a different error.

### Step 2: Take the smallest-error row as the baseline, and **exclude the baseline itself**

```python
rows = con.execute("""... ORDER BY (d.error_positive + d.error_negative), d.pdgid LIMIT ?""")
base_val = rows[0][1]
```

The baseline must be an **external anchor** (P6); it cannot be one you picked yourself — "the smallest error" is PDG's adoption preference,
not my own manual judgment.

★ But note a pit that was actually stepped in: **the baseline row cannot also serve as the object of the criterion**.
Its difference from itself is always 0, and `0 <= any positive threshold` is always true, so as long as it stays in the set, the all_false readout is mathematically unreachable.
`test_mut_4b` pins this down from the other side.

### Step 3: The criteria must straddle real differences

```python
CRITERIA = [("1s", 1.0), ("2s", 2.0), ("3s", 3.0), ("4s", 6.0), ("8s", 8.0)]
```

This is not about "giving the criteria good names" — **the criteria must span a wide enough range** for the verdict to actually flip.
This matters as much as Step 1; see error mode 3 below.

---

## 3. How not to select: leave the accounts misaligned

`pdg/misaligned.py`, four error modes that were really stepped in. **Each one comes with its measured readout.**

### Error mode 1: select by parent node, not by physical quantity → violates P1 (accounts misaligned)

```python
WHERE i.parent_pdgid = 'M070'    # ✗ assuming "same parent node" = "repeated measurements of the same thing"
```

Reality: the 544 measurements under `M070` (J/ψ decays) are **different decay channels**,
and their branching ratios are inherently different.

Measured:
```
[Error mode 1] select accounts by parent node instead of by physical quantity
  selected 40 accounts, baseline 8.2e-07
  accounts differing from the baseline by >2σ: 23/40 = 58%
  readout: all_true 0 / all_false 0 / split 3 / out_of_domain 0
  outlier attribution none  pioneers none
  diagnosis: these measurements are **different decay channels**; their branching ratios are supposed to differ.
        treating them as repeated measurements of one physical quantity = violating P1; all 23 are pseudo-outliers.
        (across all 544 accounts the false rate is 88%; here we take the 40 with the smallest errors, hence 58%)
        ★ Did it raise? No. out-of-domain skips 0, all green. **This is the most dangerous class.**
```

58% judged false, **not one of them is reported**. (Across all 544 accounts the false rate is 88%; the script takes the 40 with the smallest errors.)
This is the most dangerous class: the format looks normal, everything is green, and there is no attribution.

### Error mode 2: the predicate ignores the parameter point

```python
predicate=lambda x, r=r: abs(r[1] - base) <= max(r[2], r[3]) * 2.0
#                                                      ^^^ x is hard-coded to 2.0
```

So every account gives the same answer at every parameter point.

Measured:
```
[Error mode 2] the predicate ignores the parameter point (x is hard-coded)
  comparison domain 4 points | all_true 0 / all_false 0 / split 0
  outlier attribution none  pioneers {0: 4}
  diagnosis: the 4 parameter points give **the same** verdict vector.
        pioneer counts 4/4 all fall on account 0 — because the verdict does not depend on x,
        it is not 'only it holds under some criterion' but 'the same result under every criterion'.
        ★ Key: compared with aligned's 3/5, here it is 4/4 —
          a share close to 100% is the fingerprint of 'the verdict does not change with the parameter point'.
        ★ Did it raise? No. out-of-domain skips 0, the readout is 'all green'.
```

### Error mode 3: decorative criteria

```python
domain = [("tight", 1.9), ("nominal", 2.0), ("loose", 2.1),
          ("very_loose", 2.2), ("extreme", 2.3)]        # ✗ a span of only 1.9–2.3
```

The names look carefully designed, but the threshold span cannot straddle any real difference.

Measured:
```
[Error mode 3] decorative criteria (professional names, verdict never flips)
  5 criteria: ['tight', 'nominal', 'loose', 'very_loose', 'extreme']
  comparison domain 5 points | all_true 0 / all_false 0 / split 0 / out_of_domain 0
  outliers none  pioneers {0: 5}
  diagnosis: ★ this is **the same disease** as error mode 2 — a constant verdict vector,
        the only difference is that the criteria were renamed to sound professional (tight/nominal/...),
        while the threshold span is only 1.9~2.3σ, which straddles no real difference.
        measured: the verdict is completely identical under all 5 criteria (the baseline is True, the other 16 are False),
        so pioneers 5/5 = 100%. This is more hidden than error mode 2 —
        because the criterion names look carefully designed.
        diagnostic move: print the verdict vector point by point; identical points mean you have hit this pit.
  ★ Did it raise? No. out-of-domain skips 0, the readout is 'all green'.
```

★ **Error modes 2 and 3 are the same disease**: a constant verdict vector. The only difference is whether the criteria names sound intimidating,
which is why error mode 3 is the more hidden one.

### Appendix: error mode 4 — quote and quote_source are not same-source → **the tool stops it**

```
  ProvenanceError: [BD:QUOTE_NOT_LITERAL] [B038RE] quote is not inside quote_source (verbatim check failed)
```

★ This is **not a selection problem**; it is a provenance problem, so it stands alone as an appendix and does not count as part of the "account alignment" discussion.

The first three are not stopped by the tool (they are perfectly legal in the verdict logic; they just ask the wrong question). Only provenance-class error modes are stopped mechanically.

---

## 4. Diagnostic moves (this is the reusable part)

The three error modes above never raise an error, so you have to recognize them from the **readout shape** yourself. Four diagnostic rules:

| Readout shape | Meaning |
|---|---|
| The fraction judged false is unusually high (>50%) and there is no attribution | Suspect error mode 1 first: the accounts are not same-source, violating P1 |
| A pioneer covering ≈100% of the accounts | The verdict does not change with the parameter point → error mode 2 or 3 |
| Print the verdict vector point by point: every point is identical | Same as above; this is the direct diagnosis |
| out_of_domain skips > 0 | Some account was silently skipped; check `applies` first |

**Baseline comparison (memorize this)**:
- aligned: pioneer `3/5= 60%`
- error mode 2: `4/4 = 100%`
- error mode 3: `5/5 = 100%`

A share close to 100% is the fingerprint of "the verdict does not change with the parameter point."
This is already written as the assertion `test_pioneer_fraction_is_not_degenerate`; a constant vector turns it red on the spot.

### Degenerate readout fingerprint table (all measured, all pinned into assertions)

None of the error modes above is recognized by "looking at the conclusion"; each is recognized by the **readout shape**. Every row below is checked mechanically by
`TestDegenerateFingerprint` (7 assertions), so the document and the code cannot drift:

| Symptom | total | all_true | all_false | split | pioneer | Cause |
|---|---|---|---|---|---|---|
| **Normal baseline** | 5 | 0 | 0 | 2 | `{0:3}` = 60% | Verdict flips with the criteria |
| all_true = total | 5 | 5 | 0 | 0 | none | Predicate always true (never reads x) |
| all zeros, total = 0 | 0 | 0 | 0 | 0 | none | `applies` always false |
| all zeros, total > 0, split = 0 | 4 / 5 | 0 | 0 | 0 | 100% | Constant verdict vector (error mode 2/3) |
| all zeros, split = total | 3 | 0 | 0 | 3 | none | Accounts not same-source (error mode 1) |

★ **A pit specific to this case: all three diseases read as "all zeros."**
The `all_true 0 / all_false 0` columns are identical in four of the rows; looking at them alone, you will treat three diseases as one.
You need the other three columns to tell them apart:

- `total = 0` → not a single parameter point was compared (`applies` always false)
- `total > 0` and `split = 0` → comparisons happened, but every account gives the same answer at every point (constant verdict)
- `split = total` → every point splits, but **the split credits nobody** (accounts not same-source; the most dangerous case)

Note the last row: `split = total` looks like "a lot of information," but it is the worst kind —
error mode 1 measures exactly this (58% of the 40 accounts judged false, yet zero outliers and zero pioneers).

---

## 5. Final readout

### The aligned sample, `aligned.py`

```
  points 5 | all_true 0 / all_false 0 / split 2 / out_of_domain 0
  pioneer → B038RE (the only one that holds on 3 criteria)
          = 1517.5 MeV, error 0.398
          next-smallest error is 5.92, an order of magnitude larger → the mechanical readout points the same way as human judgment
```

The 17 accounts that come out:

| pdgid | Value (MeV) | Error |
|---|---|---|
| **B038RE** | **1517.5** | **0.398** ← pioneer |
| B101RE | 1546.22 | 5.92 |
| B060RE | 1872 | 5 |
| B077RE | 1773 | 7 |
| B032RE | 1680 | 8 |
| B036RE | 1809 | 9 |
| B035RE | 2048 | 10 |
| B167A11 | 1936 | 10 |
| B057RE | 1689 | 11 |
| B002RE | 1995 | 12 |
| B041RE | 2040 | 14 |
| B191RE | 2070 | 15 |
| B026RE | 2093 | 16 |
| B079RE | 1585 | 20 |
| B190RE | 2044 | 20 |
| B183RE | 2158 | 25 |
| B184RE | 2234 | 25 |

### Mutation evidence in `test_aligned.py`: 34 assertions, all green

It covers **two directions of breakage** (a hard rule in this project: a passing positive run proves nothing):

| Direction | Mutation | Behavior pinned down |
|---|---|---|
| Too loose | Swap the baseline to a middle row | The pioneer count must change |
| Too loose | Loosen all criteria to 100σ | Must read as all_true |
| Too loose | `applies` always false | out_of_domain skips + `coverage_guard` must stop it |
| Too tight | Tighten the criteria to 0.001σ (baseline excluded) | Must read as all_false |
| Both | Too loose vs too tight must give different readouts | Guards against decorative parameter points |
| Both | The baseline itself is always true under any positive threshold | Records a capability boundary |
| Provenance | Inconsistent quote wording | Must raise `ProvenanceError` |
| Provenance | quote missing a few digits of precision | Records the substring granularity limit (capability ceiling) |
| Fingerprint | The 5 rows of the §4 fingerprint table + telling the three all-zero cases apart | The document table must not drift from the code |
| Corpus pin | Forged edition=2026 / schema=0.3 / rows=19,587 / changed citation | Must raise `PinError`; a missing file only gets recovery steps, no 2026 download |
| Corpus pin | Structure all right but content changed (bytes padded to the pinned size) | Must be caught by SHA256, not by size/row count alone |
| Corpus pin | The fetch script must contain no network download mechanism | A human "don't download 2026" convention is not enough |
| Corpus pin | `aligned.py` / `misaligned.py` must reject a wrong edition on the read path | Bypassing `fetch_data.py` is still blocked |
| Portable | `_ROOT` must not hard-code the number of levels to walk up | Must still run after the directory moves |
| Guard | Missing data / empty database | Must `SystemExit`; must not quietly run an empty report |

★ The missing-data guard stepped in a pit: `os.path.exists` is not enough — `sqlite3.connect` will **create out of thin air** a 0-byte empty database,
after which exists is true, and the check is fooled by the file it created itself. You must also check the size. Fixed, and pinned down in both directions.

---

## 6. Conclusion

### 6.1 What holds

**On a real external corpus, N-account diffing produces an interpretable attribution, and that attribution points the same way as human judgment.**

`B038RE` is identified as the pioneer independently, and its error really is 1/15 that of the next smallest.
This is one instance of a mechanical readout matching domain judgment — but only **once**.

### 6.2 What does not hold (and must be said in the same breath)

**All-green mutation evidence ≠ the core function "is usable as a scientific instrument."** That inference skips a logical step:

| What mutation evidence proves | What mutation evidence does **not** prove |
|---|---|
| The tests have discriminating power (break something and they turn red) | High `precision` (a low false-positive rate) |
| The construction has no obvious self-contradiction | Scientific validity |
| Both directions of breakage are detectable | That the accounts **are aligned** — P1/P2 are a human judgment |

On the same engine, misaligned accounts produce an all-green readout with no attribution (error mode 1 measures 58% false outliers, zero errors).
So between "it runs and produces an attribution" and "it can be trusted" sits the human judgment of P1/P2,
and **the tool is not responsible for that judgment**. It lives in the case study, in review, and at the moment you select accounts.

### 6.3 Boundary statements

- **Divergence ≠ better.** A pioneer/outlier only says "who differs from whom". It can also mean one experiment underestimated its error.
- **Consistency ≠ verification.** A consistent readout across same-source accounts is self-consistency, not cross-verification (P6). In this case,
  the 17 accounts come from different experimental groups but share one database as their source; the attestation tier is still only `self-attested`,
  not `git-object`.
- **Capability ceiling: the verbatim check only guarantees "the quoted string appears in the source"; it does not guarantee "the quoted string expresses what the source means."**
  A value with a few digits missing still counts as a substring and is let through (`"value=1517"` ⊂ `"value=1517.5"`).
  Only changed wording is stopped.
- **The four quadrants carry limited information at N=2**; the layering of "consensus region + split region" only appears at N=17.

### 6.4 In one sentence

> The engine is responsible for "what value your predicate takes at each parameter point".
> Whether the accounts are aligned is your job — **the whole of this lesson is: don't let the engine do that job for you.**

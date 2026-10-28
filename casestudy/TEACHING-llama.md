# Industrial case: official announcement vs actual artifact

> The first case (PDG) asks "are these measurements consistent with each other".
> This case asks a real question: **is what the vendor says true?**
>
> Scripts:
> - `llama/aligned.py` — how to take the values once the accounts are aligned
> - `llama/misaligned.py` — the four failure modes of the **probe layer**, each with its measured readout
> - `llama/test_aligned.py` — break it and it must go red (45 assertions)
> - `llama/official_ledger.json` — verbatim ledger of the official notes (the only source for the **Q account**)
> - `llama/corpus_manifest.json` — artifact-side ledger (**measured record**, including exact asset bytes/SHA256 and corpus status)
> - `llama/fetch_corpus.py` — downloads and unpacks the three official builds; `--links` prints the asset list
> - `llama/DOWNLOAD.md` — the corpus asset list (URL/bytes/SHA256) and manual download steps
>
> Corpus: **llama.cpp (ggml-org)** official nightly builds — not Meta's Llama model
> weights; a `llama-b<number>/` directory is an inference engine, not a model.
> b10472 (2026-08-17) / b10595 (2026-08-23) / b11681 (2026-10-16)
>
> ### Where the corpus comes from: run fetch_corpus.py
>
> Unpacked, the three builds total about **2.1 GB**; they cannot go into git and cannot be distributed with the repository.
> So "data included" has to work differently here: **bundle the way to fetch it, not the data itself**.
>
> ```bash
> cd llama
> python fetch_corpus.py            # download + unpack into this directory, 447,813,339 bytes (about 427 MiB)
> python fetch_corpus.py --links    # print the asset URLs/bytes/SHA256 only; no download
> ```
>
> Asset names, exact bytes and SHA256 are not written into the script; they are pinned in `asset_pins` in `corpus_manifest.json`.
> This came out of an actual run: **b10472/b10595 are cuda-13.3, b11681 is cuda-13.4**
> — the minor version changes over time, so hard-coding a generic "CUDA 13" points at a URL that does not exist,
> and a failed download usually looks like a "network problem", which rarely makes you think of the version number.
> The exact bytes matter for the same reason: the page shows "140 MB" as a 1024-based rounding, while
> b10472's asset measured **146,707,438 bytes**, and only that number can tell whether a download is the same asset.
> Every zip is checked against bytes + SHA256 before unpacking; a mismatch deletes the bad file and refuses to unpack.
>
> CUDA has two layers of evidence of different strength: the "CUDA 13 family" is **inferred from the DLLs shipped
> inside the artifacts** (`cublas64_13.dll` / `ggml-cuda.dll`); the exact minor version is anchored by the
> official release asset name. Writing only "Windows x64 (CUDA 13)" loses the distinction — and that is exactly
> how the wrong asset gets downloaded.
>
> To save bandwidth you can use `--asset cpu` (17.3–18.7 MiB each, 8 times smaller than the cuda build),
> but **nobody has verified that the cpu build gives the same probe readout as the cuda build** — every cpu
> asset in the ledger is marked `readings_unverified: true`; check it yourself before relying on it.
>
> ### ★ Corpus status: b10472 / b10595 have been deleted
>
> After the readout ran clean, these two earlier builds were deleted, so **the cross-version conclusion can no longer be re-run**.
>
> This fact is recorded honestly in `corpus_status` in `corpus_manifest.json`
> (`state: PARTIAL` + `missing` + `impact`) rather than worked around.
> For why, see the three levels of silence in §4b: **if a missing corpus is not recorded, later readers will assume all three builds were always there,
> and when a re-run fails to produce the conclusion they will not know what to blame.**
>
> To restore: `python fetch_corpus.py` (the official release is still there; the archives can be downloaded again)
>
> How to run it (the corpus root is given by an environment variable, not hard-coded in the code):
> ```
> cd llama
> # Windows
> set BREAKINGDIFF_LLAMA_ROOT=<your corpus root>
> # macOS / Linux
> export BREAKINGDIFF_LLAMA_ROOT=<your corpus root>
>
> python aligned.py
> python misaligned.py
> python test_aligned.py      # 45 assertions (all green when the corpus is complete; the relevant ones skip when it is missing)
> ```
>
> `python aligned.py --llama-root <path>` is also supported,
> or you can drop the `llama-b*` directories directly beside this script.

---

## 1. Why this case is closer to industrial production than the PDG one

| | PDG case | This case |
|---|---|---|
| Q account | independent measurements in a database | **verbatim statements in the official release notes** |
| P account | another set of measurements in the same database | **the actual behavior of the unpacked binaries** |
| What is independent | different experimental groups | **the vendor cannot have written its notes from my binary** |
| Question answered | are the measurements consistent with each other | **do the announcement and the artifact match** |

P6 holds more strongly here. And this is **a real scenario that happens every day** —
every CI run does "the vendor says it upgraded, I upgraded, but did it actually change on my machine".

### 1.1 A precondition that must be stated first

The official `docs/release.md` says, verbatim:

> Currently releases are not published to github releases, only
> nightly/development builds are available there.

That is, **every bXXXXX is a nightly/development build**.
So this case does not test "whether the official release notes are right", it tests
"**whether the promises in the nightly announcement match the actual artifact**".

This precondition matters: a nightly announcement is minimal by design (one line of
commit summary per build), and expectations for it should differ from those for official
release notes. But **minimal does not mean breaking changes may go unreported**.

---

## 2. How to extract: account alignment

Three accounts = **three official statements**, N = three build numbers.

```python
CLAIMS = [
    {"name": "C1 server adds SLOTS_N_DIFF", "claimed_at": "b10595", ...},
    {"name": "C2 MELLUM precision handling", "claimed_at": "b11681", ...},
    {"name": "C3 template-analysis not removed", "claimed_at": None,  ...},
]
```

### 2.1 The parameter point is "where the change happened"

This is a P3 boundary specific to industrial settings, different in kind from the
"statistical criterion nσ" in PDG:

- parameter point = build number, in ascending time order
- predicate reads x: only require the official statement to hold when `x >= claimed_at`
- **"the change is legal and non-erroring"**: one exe fewer, one environment variable more — the program still runs and nothing stops it

### 2.2 order_key is not a detail

The warning the tool raises on its own (quoted in full):

> Order is not determined by order_key; the caller's list order is taken as time order.
> The ratchet direction ("present in the old version, dropped in the new one") depends on this assumption; if the list order is not time order,
> the direction of ratchet violations flips entirely, **while the readout looks perfectly normal**.

That last half-sentence is the most valuable part: get it wrong and **you cannot tell**.

A build number is itself time order, so order_key can be determined **mechanically**,
with no human judgment. That is this case's structural advantage over the previous one:
**parameter points come with natural labels**.

### 2.3 Redaction: no local paths in code or docs

This is a hard requirement, backed by assertions (`TestNoPathLeak`, 3 of them).

**Rule**: do not write any local absolute path in code or docs. The corpus root is specified in one of three ways:

| Way | Form |
|---|---|
| Environment variable | `BREAKINGDIFF_LLAMA_ROOT=<path>` |
| Command line | `python aligned.py --llama-root <path>` |
| Default | copy the `llama-b*` directories beside the script |

The criterion for "corpus root" is: **both the `b10472` and `b10595` build directories can be recognized under it**.

> The path `D:/a/llama.cpp/...` is kept — it appears inside the official binary as part
> of the evidence for the upstream build, is public information, and has nothing to do with a local path.

### 2.4 A missing corpus must exit explicitly

```
[FATAL] cannot find a complete llama.cpp corpus.
       Need a root containing llama-b10472, llama-b10595, llama-b11681.
       Three ways to specify it (pick one):
         1) environment variable: set BREAKINGDIFF_LLAMA_ROOT=<path>
         2) command line:         python aligned.py --llama-root <path>
         3) or copy the llama-b* directories beside this script
       The artifacts come from the official llama.cpp nightly releases; unpack them by build number.
       Or run python fetch_corpus.py to download them automatically.
```

★ This is the exact opposite of the mistake this case must never make:
**if the corpus is absent and the run quietly produces an empty readout, "did not run" gets read as "it ran, and the official announcement is fine".**

So the exit message must **say what to do**, not just say "it failed".
This is written as an assertion (`test_missing_root_exits_nonzero_with_guidance`),
which checks that the message really contains those key strings.

### 2.5 The Q account must be verbatim, and must have an external anchor

`official_ledger.json` stores the original text of the `<details open>` section of the official body.
The mechanical external-anchor check (`test_self_reported_sha_is_prefix_of_ledger_sha`):

```
b10472  self-reported 60eeeb608   official sha 60eeeb6082c1126b...  ✓ prefix matches
b10595  self-reported e8eed4525   official sha e8eed4525aaca00a...  ✓ prefix matches
b11681  self-reported 5e03a1ff4   official sha 5e03a1ff450cae37...  ✓ prefix matches
```

The self-reported commit matches the official sha character for character → mismatched attribution in the ledger is ruled out.

---

## 3. Final readout

```
[Shape statistics]  3 accounts, 3 points in the comparison domain
  all_true        2    66.7%
  all_false       0     0.0%
  split           0     0.0%
  outlier ← C3 template-analysis not removed   1   33.3%
  out_of_domain skipped                     0

[Witnesses]
  ⚠️ 2 ratchet violations: present in the old version, dropped in the new one — a cross-version regression
     C1→C3 @b11681
     C2→C3 @b11681
  ▸ outlier: this account is missing points all the other accounts cover (candidate suspect, not a verdict)
```

**P-account measurement matrix**:

```
probe                             b10472    b10595    b11681
------------------------------------------------------------------------------
  server has SLOTS_N_DIFF              —       yes       yes
  has MELLUM implementation          yes       yes       yes
  has template-analysis.exe          yes       yes         —
```

### Judging each account in turn

**① C1 SLOTS_N_DIFF — the official statement [holds], and the introduction point can be located**

Official b10595, verbatim:
```
server : add LLAMA_SERVER_SLOTS_N_DIFF (#27600)
```
Measured: absent in b10472, present in b10595, present in b11681 → the introduction point matches the statement exactly.

**② C2 MELLUM — the official statement [holds in wording, unverifiable in substance]**

Official b11681, verbatim:
```
graph : add precision handling for MELLUM architecture (#30584)
```
Measured: all three builds **do** contain the MELLUM implementation (the same 8 strings, including
`D:/a/llama.cpp/llama.cpp/src/models/mellum.cpp`).

→ What the official says is "adds **precision handling**", not "adds MELLUM support".
→ MELLUM support was already present in b10472.
→ So this account **cannot measure what the official claims**; it can only measure "MELLUM exists".

**This is the tool's capability boundary, not an official error.** This case records it honestly as
"weak evidence", not as "pass" — weaken that and "cannot measure" disguises itself as "passed".

**③ C3 template-analysis — ★ the official statement [missing], measured [a real gap]**

Across the three versions, the official notes mention only 3 things, **all of them "additions"**.
And `llama-template-analysis.exe`:

- b10472: **present**
- b10595: **present**
- b11681 (latest): **missing**

→ Removal is the most breaking kind of change, and **not one word mentions it**.
→ Root cause: the official notes are per-commit summaries (add / fix / update),
and a deletion commit has no announcement slot.

This reads as **an outlier plus 2 cross-version ratchet violations**, all at b11681.
The tool points this out on its own:

> Adjacent pairwise diffs are blind to this kind of cross-version regression; the readout here follows the chain check.

This is exactly the difference between a pairwise diff and a chain check — do only pairwise diffs, and this gap is completely invisible.

---

## 4. Four traps (all genuinely hit)

### Trap 1: the `strings` command does not exist, disguised as a factual conclusion

Early on I ran `strings llama-server-impl.dll | grep -c SLOTS_N_DIFF`,
and read the resulting `0` as "the official statement does not hold".

The truth: `which strings` → the command does not exist; what the shell returned was a
"command not found" error, and `grep -c` counted **zero lines of output**.

> **A missing tool disguises itself as a factual conclusion.**
> This is the most insidious trap in this case, more dangerous than the "predicate does not
> read x" trap in PDG, because the latter at least has an abnormal readout shape, while here the readout looks perfectly normal.

Fix: implement string extraction myself (`aligned._strings`), keyed by
`(path, mtime_ns, size)` — when the file changes the entry expires, so a stale readout cannot be read.

### Trap 2: `llama-server.exe` is just a stub

It is only a few KB; the real code is in `llama-server-impl.dll` (about 9–10 MB).
Check the wrong file and the false readout is all `False`.

### Trap 3: `order_key` orders accounts, not parameter points

The contract is `order_key(index, claim)`.
At first I wanted to sort by build number, but then the three builds under one probe
get interleaved with same-named builds from other probes.
The correct key must carry a grouping dimension — this case uses `(probe name, build number)`.

### Trap 4: materializing every string in memory → MemoryError

Initially `_strings()` turned every printable run of length ≥ 4 in the binary into a Python object:
millions of `str` per build, and scanning three builds ended in a straight `MemoryError`.

The fix was not "add a cap" but **change the algorithm**: a probe only answers
"does this file contain the needle", so it became `_file_has()` —
a regex search over the raw bytes, **returning on the first hit and materializing no strings at all**.

The cost is rescanning the file on every call, so I added **boolean** memoization on
`(path, mtime_ns, size, needle)` — what is cached is `True`/`False`, not millions of objects.

> This trap is recorded here because its lesson is not just "save memory":
> **the abstraction of the probe layer must be designed against the question**. I wanted "is it there",
> but built a tool that "lists all the content" — the question had been overstepped,
> and the memory problem was only its first symptom.

---

## 4b. The probe layer: failure modes unique to industrial settings

`misaligned.py` teaches the **probe layer** — the PDG case has no such layer,
because it reads data straight from a database; industrial settings cannot do that,
and nobody can treat a 700 MB binary as evidence directly.

All four failure modes **raise no error**:

**Error mode 1: checking the wrong file (the most dangerous)**

`llama-server.exe` is only **9216 bytes**, a stub;
the real code is in `llama-server-impl.dll` (8851968 bytes, a factor of 960).

| Build | Stub size | Stub hits | Impl size | Impl hits |
|---|---|---|---|---|
| b10472 | 9216 | 0 | 9979392 | 0 |
| b10595 | 9216 | 0 | 8851968 | **1** |
| b11681 | 9216 | 0 | 9259520 | **1** |

Check the stub → all three builds give 0 → the conclusion becomes
"the official says SLOTS_N_DIFF was added, the measurement finds it in none of the three versions, so the vendor is lying".

**The truth is that the probe checked the wrong file.**

★ Checking the wrong file does **not** make the readout look strange; it only leads you to a **reversed** wrong conclusion.

**Error mode 2: a silent probe**

When the probe fails it returns `False` silently, with no explanation. So on the readout these two kinds of False
**look exactly the same**:

- "this build does not have this feature" ← it really is absent (fact)
- "my probe did not find the file" ← my tool is broken (tool)

★ The essential difference from the first case: **in PDG you read a database, and a failed read raises a SQL error,
so failure is "loud". Here failure is "quiet"** — so quiet that it cannot be told apart from "the fact is false".

Fix: a probe must return `(bool, explanation)`, and a `False` must carry a reason.
All three probes in `aligned.py` follow this.

**Error mode 3: dimensions mixed**

This is the reason `aligned.py` was reworked (see §5). The measured symptom **differs from the first case**:

```
Measurement of the three probe classes on each build:
  b10472  —  yes  yes
  b10595  yes  yes  yes
  b11681  yes  yes  —

Verdict vectors after mixing dimensions:
  b10472/mixed  [False, False, False]
  b10595/mixed  [True, True, True]
  b11681/mixed  [True, True, True]

Readout: all_true 0 / all_false 0 / split 0 / out_of_domain 0
```

Every account's verdict vector is **constant**, so the three accounts split into two camps
with **not a single point of agreement**.

★ **All-zero is more dangerous than all-true**: all-true at least looks self-consistent; all-zero looks like "nothing was measured".

**Appendix · Error mode 4: a forged anchor** (ledger layer, not probe layer)

Passing b10595's original text off as b10472's raises `ProvenanceError` on the spot.
**The tool catches this one**; it does not catch the first three.

### Degenerate-readout fingerprint table (measured, pinned into assertions)

This table is written as 4 assertions
(`TestDegenerateFingerprint`), so the docs and the code cannot drift apart.

| Symptom | all_true | all_false | total | Cause |
|---|---|---|---|---|
| all_true = total | 3 | 0 | 3 | predicate constantly true (does not read x) |
| all zero but total = 0 | 0 | 0 | 0 | `applies` constantly false |
| all zero but total > 0 | 0 | 0 | 3 | account split: dimensions mixed |
| readout normal but conclusion reversed | — | — | — | probe checked the wrong file |

★ **Key point: the middle two rows both show "all zero"; only `total` separates them.**

- `total = 0` = not a single point was compared
- `total > 0` and all zero = points were compared, but there is no region of agreement

**Neither is a "pass".**

---

## 5. This script was reworked once

**The first version read out "all_true 3/3 = 100%", and the tool raised no error at all.**

The cause: I packed **"artifact facts" and "official promises" into the same account** (9 of them),
the predicate degenerated into a constant → all 9 accounts had the verdict vector `[True, True, True]`.

The root cause was **mixed dimensions**:

> "does the file exist" and "has the official promise been honored" are not the same thing.

The right shape: **one account = one official statement**,
asking at each parameter point (build number) "was this statement honored in this build",
with artifact facts appearing only as evidence inside the predicate.

This trap is the same disease as "error mode 2" in the first case,
but **industrial settings step in it more easily** — because there "fact" and "promise" are naturally entangled:
code, comments, logs, and announcements all describe the same thing.

Written as assertions `test_reading_is_not_degenerate` + `test_verdicts_actually_vary`,
to keep it from coming back.

---

## 6. Mutation evidence: 45 items, all green

Covers **both directions of breakage** (a hard discipline in this project: a passing positive run proves nothing):

| Direction | Mutation | Behavior pinned |
|---|---|---|
| too loose | predicate constantly true | reads as all_true 100% + ratchet goes to zero |
| too loose | probe always returns True | the real gap is masked |
| too loose | `applies` constantly false | out-of-domain skips + `coverage_guard` blocks it |
| too tight | predicate constantly false | reads as all_false |
| both directions | loose and tight readouts must differ | catches verdicts insensitive to input |
| ledger | all three build numbers present | Q account source complete |
| ledger | **the self-reported sha is a prefix of the official sha** | ★ P6 external anchor |
| ledger | `claims_verbatim` appears verbatim in `body_details_verbatim` | stops the ledger storing a summary as the original text |
| provenance | quote not in quote_source | `ProvenanceError` |
| provenance | **cross-build quotation** | stops another build's statement being quoted as this build's |
| guard | missing ledger | `SystemExit` |
| guard | probe cannot find the file | returns False + explanation, **must not raise and must not count as a pass** |
| fingerprint | shape of the four degenerate readouts | see the §4b quick table; **must be measured, never written from memory** |
| fingerprint | `applies` always false vs. mixed dimensions, told apart by `total` | both show all zero |
| redaction | no local paths in code/docs | `TestNoPathLeak` |
| redaction | corpus root must not be hard-coded | uses env var / CLI / sibling directory |
| redaction | missing-corpus exit message includes usage | must not just say "failed" |
| relocatable | `_ROOT` must not hard-code a number of parent levels | must still run after the directory moves |
| ledger | `corpus_manifest` covers all three builds | artifact-side facts can be checked |
| ledger | asset names must contain the real CUDA minor version | stops downloads from a nonexistent URL |
| ledger | every used asset has exact bytes + SHA256 | a download can be checked against the same asset |
| ledger | `verify_asset` checks bytes first, then SHA256 | a half zip / a same-size zip with swapped bytes must be rejected |
| ledger | the CPU build is marked `readings_unverified` | an unverified readout must not impersonate an equivalent one |
| ledger | `_what_this_is` says llama.cpp nightly, not a Meta model | stops the directory name from misleading |
| ledger | the ledger must say of itself "does not replace re-running the probes" | stops it being taken as the evidence itself |
| ledger | corpus status must be recorded honestly and self-consistently | ★ a gap must not be worked around |
| ledger | the C3 verdict direction matches the core finding | stops ledger and conclusion drifting apart |
| guard | the exit message must point to `fetch_corpus.py` | saying only "not found" without a way out is not acceptable |
| guard | an **incomplete** corpus must state that the cross-version conclusion is invalid | ★ the tool does not error when a build is missing |

### What mutation evidence proves, and what it does not

| Proves | Does not prove |
|---|---|
| the tests discriminate (breaking it goes red) | high `precision` (low false-positive rate) |
| the ledger matches the artifact | the **completeness** of the official announcement |
| the construction has no self-contradiction | that C2 can verify "precision handling was added" — **it cannot measure that at all** |

**All-green mutation evidence ≠ the official announcement is right.**
It proves only that "the readout shape is pinned down".
The real finding (the C3 gap) came from measuring the P account, not from mutation evidence.

---

## 7. Conclusion

### 7.1 What holds

**On a real industrial artifact, an N-account differential produces an actionable attribution of divergence,
and the tool itself states its severity tier.**

Concretely:
- C1 the official statement **holds**; the introduction point is pinned to b10595
- C3 the official statement is **missing**, and the artifact **really did change** (the exe was removed)
- the tool judges C3 an **outlier** and additionally reports **2 cross-version ratchet violations**,
  pointing out on its own that "adjacent pairwise diffs are blind to this kind of regression"

### 7.2 What does not hold (and must be said in the same breath)

- **This is not "the official announcement was wrong".** Official nightly notes are minimal by design;
  **not mentioning** a deletion is not the same as **deliberately hiding** it. This case reports readouts; it does not adjudicate.
- **C2 cannot be measured.** The official says "adds precision handling"; this case can only measure "MELLUM exists".
  Calling that "verified" is self-deception.
- **The attestation tier is still `self-attested`.** The sha prefix check makes the ledger credible,
  but the artifact itself has no git-object-level anchor (that belongs to the upstream repository; it is not obtainable from a release archive).

### 7.3 In one sentence

> The engine answers "what value does the predicate you supplied take on each build".
> What the official says, what the artifact is, and **whether the two match** — the differential gives you a readout,
> but "should this gap be reported, is it actually wrong" is **your judgment**.

---

## 8. Relation to the first case

Together the two cases cover two ways an N-account differential lands in practice:

| | First (PDG) | Second (llama.cpp) |
|---|---|---|
| Theme | consistency among multiple external sources | **the differential between promise and fact** |
| Distinctive value | a genuine external anchor (P6) | **Q/P naturally independent** |
| Layer taught | data-extraction layer: **how to take P/Q** | **probe layer + ledger layer: how evidence is extracted** |
| Shared conclusion | **the tool cannot verify P1/P2** | same |

### 8.1 They do not hit the same trap (I got this wrong at first)

I once thought the two cases hit variants of the same trap ("predicate does not read x" vs. "dimensions mixed"),
but **measurement shows the symptoms are not the same**:

| | Which layer the construction broke | Symptom |
|---|---|---|
| PDG | predicate does not read x | verdict constant → **all_true = total** |
| llama | dimensions mixed (account split) | verdict constant → **all zero, total > 0** |

What they share is that "the verdict does not vary with the parameter point", but the **readout shapes differ**:
PDG at least reads out all_true, llama reads out all zero — and all zero looks like "nothing was measured",
which is easier to misread as "there is nothing to measure" than all_true is.

Which leads to a more general conclusion:

> **A degenerate readout has more than one shape; do not remember only one fingerprint.**
> You must look at `total` as well — `total = 0` and `total > 0 with all zero`
> are two entirely different diseases, and the cure differs too.

### 8.2 Industrial settings add a whole layer over academic ones

| | Academic setting (PDG) | Industrial setting (llama) |
|---|---|---|
| Evidence source | a database, one row is one row | a 700 MB binary that must be extracted |
| When extraction fails | SQL error, **loud** | silent False, **quiet** |
| Layer that breaks | data-extraction layer (when you write the predicate) | **probe layer (when extracting) + ledger layer (when recording)** |
| Who wrote it | you | possibly you, three months ago |

**The extra layer is the genuinely new risk of industrial settings.**
Every conclusion from the first case still holds here,
but none of them reaches the probe layer — and the probe layer fails more quietly and more easily produces a reversed conclusion.

---

## 9. After the corpus was deleted: a worked example of "recording a gap"

This section was not designed; it was stumbled into.

### 9.1 What happened

After the readout ran clean and 27 assertions were all green, the two builds `b10472` and `b10595` were deleted,
leaving only `b11681`. So the case's **core conclusion can no longer be re-run** —

The disappearance of `template-analysis` is a **cross-version comparison** (present in the first two versions, absent in the latest).
With only the after and no before, the `C3` account has lost its comparison object.

### 9.2 The most dangerous part: the tool will not tell you

This is the third level of silence from §4b showing up again, and this time it is more extreme:

| Situation | What the tool does |
|---|---|
| all three builds present | readout normal, conclusion holds |
| **only one build left** | **a readout still comes out, just with fewer comparison points** |
| no build at all | explicit exit (the missing-corpus guard blocks it) |

The middle row is the genuinely dangerous tier: **there is no error anywhere between "incomplete corpus" and "normal readout"**.
`C3` goes from "1 missing out of 3 versions" to "1 missing out of 1 version" —
the outlier share goes from 33% to 100%, and the tool says not a word.

So a gap must be **checked explicitly**, not guessed at from the readout shape.

### 9.3 What to leave behind: a record, not a workaround

The handling is written into `corpus_status` in `corpus_manifest.json`:

```json
"corpus_status": {
  "state": "PARTIAL",
  "present": ["b11681"],
  "missing": ["b10472", "b10595"],
  "reason": "the two older builds were deleted after the verification run passed",
  "impact": "★ **the cross-version conclusion cannot be re-run**. The disappearance of template-analysis is a cross-version comparison (present in b10472/b10595 → absent in b11681); with only after and no before, the `C3` account loses its comparison object.",
  "recoverable": true,
  "how": "python fetch_corpus.py (re-download from the official release, see asset_pins; each zip is checked against its exact bytes + SHA256 before unpacking)"
}
```

All three fields are required:

- **`state` + `missing`** — show at a glance what is missing
- **`impact`** — ★ the most important. **It must state exactly which conclusion goes invalid because of the gap.**
  Writing only "b10472 is missing" is useless; writing "the cross-version conclusion cannot be re-run" is what helps.
- **`recoverable` + `how`** — if it can be restored, do not leave only a note saying "gone"

### 9.4 Another discipline this exposed: the ledger must not be a dead record

The biggest risk for a ledger is **becoming a record that never changes and may be out of date**.
So `fetch_corpus.py --manifest` can **rescan and overwrite** it when the corpus is present —
the machine refreshes the ledger; the author's memory does not maintain it.

There is also a **line that must not be crossed**, and the ledger states it itself:

> ★ This file is a **measured record**, not the evidence itself.
> It lets a reader check readout consistency, but **it cannot replace re-running the probes** —
> only a run against the real binary counts as verification.

This is written as the assertion `test_manifest_states_honesty_boundary`.
Otherwise the ledger slowly gets treated as "the evidence has been archived", which is exactly the third level of silence.

### 9.5 In one sentence

> **A missing corpus is not a documentation problem; it is a readout problem.**
> If something is missing, say exactly "which conclusion goes invalid because of it" —
> write only "the data is gone", and the next person will still use the old readout as new evidence.

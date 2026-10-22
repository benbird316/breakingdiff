# case study

Cases are not found by "what the directory is called" but by **what you have in hand right now**. Look at the first column first; on a hit, read only the material that row points to — the four columns answer, in order: what to do, what to learn, where to look, and what it teaches.

| What you want to do | What to learn | Where to look | What it teaches |
|---|---|---|---|
| Write an account as claims for the first time: several independent measurements of the same physical quantity, unsure how to choose P and Q | **data-extraction layer**: when the accounts are not aligned, the readout is 100% all_true or entirely split | [`pdg/`](pdg/) + [`TEACHING-pdg.md`](TEACHING-pdg.md) | 22 assertions; of the four error modes **only the provenance one is blocked mechanically** (`ProvenanceError`); the selection error modes come out all green with no attribution |
| Industrial evidence does not line up: the official release notes say one thing and the artifact another, or the corpus is still missing | **probe layer + ledger layer**: when the evidence is extracted wrong the readout is **all zeros**, quieter than the data-extraction layer | [`llama/`](llama/) + [`TEACHING-llama.md`](TEACHING-llama.md) | 36 assertions; the four `corpus_manifest` fields (state/missing/impact/how); what to leave behind when the corpus is absent |
| Claims keep going red although the data is fine: large individual variation, or unsure what granularity to make the claim at | **strength layer**: point-value claims on data with 30% variation produce **false red all over** — on the same data, bounded bands flag 12 points and point-value claims 2,720; pick the wrong strength shape and true data reads as bad data | [`malecns/`](malecns/) + [`TEACHING-malecns.md`](TEACHING-malecns.md) | 24 assertions; a public connectome of 45.6M synapses; three accounts (synapse level / neuron level / type level) carry natural outliers; the real-world shape of preregistered criteria plus registration at the exit |
| Rewrite an implementation: Python to Rust/Go, or the same tool rewritten in another language, and you need to confirm behavior did not drift | **port layer**: a claim is an asset, the implementation can be replaced; only three matching readouts count as equivalent | [`port/`](port/) + [`TEACHING-port.md`](TEACHING-port.md) | 12 assertions; `claims.json` read by all three implementations; the `--mutant boundary` shift is predictable (common 8→7); zero crates on the Rust side |
| Audit a cross-version API change and you need to know exactly what a client will stop being able to call | **quadrant reading + the programming domain**: on an existence baseline the removals land in **`divergence`**, not `dominance` — the product column follows the baseline, not the data; and a criterion the domain cannot support is **refused by the gate** rather than reported as zero | [`k8s/`](k8s/) + [`TEACHING-k8s.md`](TEACHING-k8s.md) | 33 assertions; two official OpenAPI snapshots, 2,049 request dimensions; 193 removals collapsing to three API groups; the type-fingerprint account is blocked with `READING_DISCRIMINATION_ZERO` |
| You only want to see what the engine looks like on a real domain and do not plan to read the lesson | — (reference only) | [`hubble/case_study.py`](hubble/case_study.py) | A zero-outlier prototype: the same engine produces attribution when the selection changes, proving that "zero outliers ≠ a broken engine" |

---

## The five cases do not fall into the same pit

Side by side:

| | PDG | llama | malecns | port | **k8s** |
|---|---|---|---|---|---|
| Which layer is broken | data-extraction layer (accounts not aligned) | probe layer (evidence extracted wrong) | **strength layer** (the claim is stronger than the data's occurrence pattern) | **port layer** (implementation replaced, the account drifts with it) | **scope layer** (the surface under test is smaller than the change) |
| Degenerate readout | all_true 100% / entirely split | **all zeros** (`total>0`) | **false red all over** (true data read as bad data) | **three readouts diverge** (each self-consistent on its own) | **a clean one-point readout** (218 scoped, 1 common, 0 differences) |
| Is failure loud or quiet? | quiet (no error, out_of_domain 0) | **quieter** (reading the database raises an SQL error; probing the binary does not) | loud (it goes red loudly, but the red is on true data) | quiet (all three implementations run, all formats correct) | **loudest of all** — the gate raises `READING_DISCRIMINATION_ZERO` and refuses to produce a readout at all |

When the PDG layer breaks, you still have a chance to see it; when the llama layer breaks, the readout looks perfectly normal;
the port layer is more hidden — **each implementation is correct on its own, and only a point-by-point comparison shows which one drifted**;
the malecns layer is the other way round — **the failure is loud, but what it is loud about is true data**: with the wrong strength,
fixing the data does not help; what needs fixing is the strength shape of the claim.
The **k8s** layer is the only one that can refuse outright: a criterion the domain
cannot support does not report zero, it reports that it could not be certified —
which is strictly more informative than a zero and strictly less convenient.

---

## How to run

No case hard-codes any path; they search upward for `scripts/breakingdiff.py`, so the directory can be moved anywhere.

### pdg (about 7.6 MB of corpus, download first)

```bash
cd pdg
python fetch_data.py        # once, the server is slow
python aligned.py           # positive case: the readout when the accounts are aligned
python misaligned.py        # negative case: four error modes, each with its measured readout
python test_aligned.py      # 22 assertions, all should be green
```

### llama (bring your own three official nightly builds)

Corpus: three builds from the official llama.cpp nightly releases:
`b10472` (2026-08-17) / `b10595` (2026-08-23) / `b11681` (2026-10-16).

Where the corpus comes from: each build number maps to an official release; download the
Windows x64 (CUDA 13) archive for your platform and unpack it to get a `llama-b<build number>/` directory.
Put the three directories under one root directory.

The unpacked corpus is about 2.1 GB in total and cannot go into git, so **each case ships its own fetch method**:

```bash
cd llama
python fetch_corpus.py            # download and unpack the three official builds, about 450 MB of traffic
```

```bash
# three ways to point at the corpus root, pick one
export BREAKINGDIFF_LLAMA_ROOT=<path>   # 1) environment variable
python aligned.py --llama-root <path>   # 2) command line
# 3) or copy the llama-b* directories next to this directory
python aligned.py
python misaligned.py
python test_aligned.py      # 36 assertions (all green with the corpus; related items skipped when it is absent)
```

> **★ Corpus status at writing time: `PARTIAL` (a snapshot of the author's machine).**
> At writing time `b10472` / `b10595` had already been deleted, leaving only `b11681`,
> so **the cross-version conclusion could not be rerun at the time**. A clean checkout starts with all three missing (0/3);
> restore them with `python fetch_corpus.py`.
> Details in `TEACHING-llama.md` §9 — that section is exactly about "what to leave behind when the corpus is gone".

### port (needs the Go and Rust toolchains)

```bash
cd port
python reference.py        # Python reference implementation: read claims.json, run the repository's real core, reconcile against expect
python test_port.py        # 12 assertions: three matching readouts + a wrong port shifting as predicted
```

Run the two ports directly (`claims.json` is the single source of truth read by all three implementations):

```bash
go run impl_go/main.go -spec claims.json
.\impl_rust\port_rust.exe --spec claims.json   # the first run of test_port.py compiles it on the spot
```

**Toolchain discipline**: when `go` / `rustc` is absent, the related cases in `test_port.py` are skipped and named in the output —
missing is not "passed", it is "this conclusion is invalid" (following llama's corpus discipline).

Wrong-port demo (the same flag name in both languages, readouts directly comparable):

```bash
go run impl_go/main.go -spec claims.json -mutant boundary
.\impl_rust\port_rust.exe --spec claims.json --mutant boundary
```

> The contract and readout table are in `TEACHING-port.md` §4/§5; the proposition is "a claim is an asset, the implementation can be replaced".
> Go / Rust build artifacts (`port_rust.exe` and the like) do not go into git.

### k8s (about 6.2 MB of corpus, download first)

Corpus: `api/openapi-spec/swagger.json` from two official release tags of
kubernetes/kubernetes, unmodified. SHA256 for both is pinned in
`fetch_data.py` and re-verified in `test_aligned.py`.

```bash
cd k8s
python fetch_data.py            # download both, SHA256-verified before writing
python fetch_data.py --check    # verify what is on disk, no network
python fetch_data.py --manifest # rescan and rewrite corpus_manifest.json
python aligned.py               # positive case: the existence readout + the refused account
python misaligned.py            # negative case: baseline flip / single-group false green / $ref-blind drift
python test_aligned.py          # 33 assertions (all green with the corpus; skips and says why without it)
```

> **★ Corpus state when written: `PRESENT` (both files, hashes verified).**
> But the fetch path is partially broken — jsDelivr returns **HTTP 403 for
> release-1.31** ("Package size exceeded the configured limit of 50 MB") while
> 1.28 succeeds from cache. A clean checkout starts with 0/2 files, and on this
> network the fallback mirrors are unreachable without the local proxy. Details in
> `TEACHING-k8s.md` §1.1 — and `corpus_manifest.json` names which conclusion dies
> if either file is missing (it does: the whole cross-version finding is a
> present→absent comparison, so one side alone yields no conclusion at all).

> The teaching proposition is in `TEACHING-k8s.md` §3: **on an existence baseline
> the removals land in `divergence`**, so a reader who assumes the dominance
> column is the product column reports the additions and misses every breaking change.

### malecns (about 56 MB of corpus, download first)

Corpus: the official MaleCNS v0.9 release (Janelia flyem, public GCS direct link, no authentication):
body-annotations (13 MB, type/class/side annotations) + body-neurotransmitters
(42 MB, neuron-level transmitter aggregation). The SHA256 anchor is in `test_aligned.py`, and all four manifest fields are present.

```bash
cd malecns
python fetch_corpus.py      # download the two feather files, double-checked by SHA256 and row count, resumable
python aligned.py           # positive case: bounded claims + the point-value negative control (false red 12 vs 2,720)
python misaligned.py        # negative case: the degenerate fingerprints of the three error modes (point-value / strict equality / account confusion)
python test_aligned.py      # 24 assertions (all green with the corpus plus pyarrow; related items skip when the corpus is absent)
```

> The strength staircase and the criteria design are in `TEACHING-malecns.md`; the proposition is
> "claim strength must follow the data's occurrence pattern — point-value claims on counts that deviate from the baseline go false red en masse
> (12.3% measured); only what the bounded band narrows down to is signal (band width is a design choice)".

---

## Four disciplines that cannot be skipped

**One: whether the accounts are aligned is a human judgment; the tool is not responsible for it.**
Of the three error modes, only the provenance class is blocked mechanically (`ProvenanceError`);
the selection error modes all produce readouts that are **well-formed, all green, and have no attribution**.
P1/P2 are what the tool cannot do for you.

**Two: an absent corpus must be recorded, not worked around.**
`llama/` is missing two builds right now. That fact is written into `corpus_manifest.json`
(all four fields `state` / `missing` / `impact` / `how`), rather than left unsaid —
because **just writing "the data is gone" is useless; you must state which conclusion becomes invalid without it**.
See `TEACHING-llama.md` §9. The same applies to a missing toolchain: the skip in `port/` must name which conclusion is missing.

**Three: every readout table in the docs must be backed by a claim.**
The degenerate fingerprint shapes are pinned into assertions (pdg's `TestDegenerateFingerprint`, llama's corresponding fingerprint assertions);
port's readout table is backed by `*_reads_same_as_reference` and
`*_mutant_boundary_shifts_exactly_one_point` in `test_port.py`; malecns's three error-mode fingerprints
(point-value 2,720 / strict equality 4,354 / account confusion 241) are backed by frozen assertions in `test_aligned.py`;
every cell of a readout table is reconciled by an actual run —
the commands under "How to run" above are the checking commands, and a rerun matches them line by line.
It is not "the document is right", it is "the code must come out exactly like this".
While writing the docs I once made up a readout, and an assertion caught it on the spot — which is why this table is worth having.

**Four: claim strength must follow the data's occurrence pattern.**
`malecns/` measured: on the same batch of true data, bounded claims flag only 12 points false, point-value claims
2,720. When strength exceeds the occurrence pattern, the failure goes red loudly and falsely — **fixing the data does not help;
what needs fixing is the strength shape of the claim**. This one points the opposite way from the first three: they guard against "bad data that looks
good", this one against "good data that looks bad".

---

## hubble/

`hubble/case_study.py` is a prototype of the Hubble tension (disagreement over H₀ measurements);
its conclusion is **zero outliers**.

That is not a defect; it is a control: zero outliers ≠ a broken engine.
The same engine produces pioneer attribution on `pdg/aligned.py`;
the only difference is the selection. Kept as a reference, not one of the formal cases.

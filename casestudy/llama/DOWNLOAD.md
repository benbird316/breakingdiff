# llama corpus: download and verify (this case's only entry point)

> **The corpus is not committed to git.** The three `used` zips total
> **447,813,339 bytes (about 427.1 MiB)**, about **2.1 GB** once unpacked.
> Download them into a local directory and **do not commit them** — `.gitignore`
> already blocks `llama/llama-b*/`, `llama/downloads/` and `*.zip`.
>
> This file is the asset list and the manual-download instructions. The **single
> source of truth for the pins** is
> [corpus_manifest.json](corpus_manifest.json) (this page's tables are generated
> from it). The executable printout of the same list:
> `python fetch_corpus.py --links`.

## 0. What to download

The corpus is **official release assets of llama.cpp (ggml-org)** — Windows x64
binaries — **not Meta's Llama model weights**. A `llama-b<number>/` directory is an
inference engine, not a model.

| Asset category | Purpose | Total for the three builds | Note |
|---|---|---|---|
| **used** (cuda-13.3 / cuda-13.4) | reproduce this case's original readout | 447,813,339 B (about 427.1 MiB) | default; **use these to reproduce the readout** |
| cpu | just run the flow / save bandwidth | 56,172,043 B (about 53.6 MiB) | about 8x smaller, **readout equivalence unverified** |
| cuda-12.4 | alternative CUDA runtime | 767,942,847 B (about 732.4 MiB) | not used for this case's readout |

Each zip unpacks into one `llama-b<build number>/` directory; put the three
directories under one corpus root.

## 1. used assets (default, matches the original readout)

★ Do not write a vague "CUDA 13": b10472/b10595 are **13.3**, b11681 is **13.4**.
The "CUDA 13 family" is inferred from the DLLs shipped inside the artifacts
(`cublas64_13.dll` / `ggml-cuda.dll`); the exact minor version is anchored by the
official release asset name.

### b10472 — published 2026-08-17; CUDA 13.3

| Item | Value |
|---|---|
| Asset | `llama-b10472-bin-win-cuda-13.3-x64.zip` |
| Bytes | `146,707,438` (139.9 MiB) |
| SHA256 | `ce7ca842c1400a85457e6c7ce844f21e52f187e6f0364b7daf3d2fd1ccf6db3b` |
| Download URL | <https://github.com/ggml-org/llama.cpp/releases/download/b10472/llama-b10472-bin-win-cuda-13.3-x64.zip> |

### b10595 — published 2026-08-23; CUDA 13.3

| Item | Value |
|---|---|
| Asset | `llama-b10595-bin-win-cuda-13.3-x64.zip` |
| Bytes | `146,496,057` (139.7 MiB) |
| SHA256 | `20a73e56341dd43aaf9d3f53daad14e1bd362eac6ad5b3a31f36854aa9340889` |
| Download URL | <https://github.com/ggml-org/llama.cpp/releases/download/b10595/llama-b10595-bin-win-cuda-13.3-x64.zip> |

### b11681 — published 2026-10-16; CUDA 13.4

| Item | Value |
|---|---|
| Asset | `llama-b11681-bin-win-cuda-13.4-x64.zip` |
| Bytes | `154,609,844` (147.4 MiB) |
| SHA256 | `56e2f75b9ce69952b613ea95c6d54f4bf30c7261f4cda1ae954c7bcad3a114e5` |
| Download URL | <https://github.com/ggml-org/llama.cpp/releases/download/b11681/llama-b11681-bin-win-cuda-13.4-x64.zip> |

## 2. cpu assets (8 times smaller, **readout equivalence unverified**)

★ The probe readout was measured on the cuda builds; a cpu build may trim the
relevant symbols, so every cpu asset in the manifest carries
`readings_unverified: true`. Use it to run the flow, not to reproduce the readout.

| build | Asset | Bytes | SHA256 | Download URL |
|---|---|---|---|---|
| b10472 | `llama-b10472-bin-win-cpu-x64.zip` | `18,470,168` (17.6 MiB) | `ef495329c85c171991972fd3226a179c1900368cab66e2ebba8b21a7471a74e5` | <https://github.com/ggml-org/llama.cpp/releases/download/b10472/llama-b10472-bin-win-cpu-x64.zip> |
| b10595 | `llama-b10595-bin-win-cpu-x64.zip` | `18,136,128` (17.3 MiB) | `b217d938baa442aac2808c0cb4b440fbd74882cc19ec8c2d3105e6c1d9cac4a8` | <https://github.com/ggml-org/llama.cpp/releases/download/b10595/llama-b10595-bin-win-cpu-x64.zip> |
| b11681 | `llama-b11681-bin-win-cpu-x64.zip` | `19,565,747` (18.7 MiB) | `07006066db26ba20863785ec8fdd55028226c8eafcdb8db5a1484e98ebf01676` | <https://github.com/ggml-org/llama.cpp/releases/download/b11681/llama-b11681-bin-win-cpu-x64.zip> |

## 3. cuda-12.4 assets (alternative runtime, not used for the readout)

| build | Asset | Bytes | SHA256 | Download URL |
|---|---|---|---|---|
| b10472 | `llama-b10472-bin-win-cuda-12.4-x64.zip` | `250,798,945` (239.2 MiB) | `aadc171ddb4ed1822bc1730bff447068b529718cef886437866e3bd536eda143` | <https://github.com/ggml-org/llama.cpp/releases/download/b10472/llama-b10472-bin-win-cuda-12.4-x64.zip> |
| b10595 | `llama-b10595-bin-win-cuda-12.4-x64.zip` | `250,534,432` (238.9 MiB) | `ba4204aa8a04f752e605dcefda77ba553c75e0e2c2c8cdab2597a7ac22570167` | <https://github.com/ggml-org/llama.cpp/releases/download/b10595/llama-b10595-bin-win-cuda-12.4-x64.zip> |
| b11681 | `llama-b11681-bin-win-cuda-12.4-x64.zip` | `266,609,470` (254.3 MiB) | `c3b9605f70f53beafd1a36fa360d32a22f8d5a0c6dcb1276f2d8b69a3db777ca` | <https://github.com/ggml-org/llama.cpp/releases/download/b11681/llama-b11681-bin-win-cuda-12.4-x64.zip> |

## 4. How to download (recommended: let the script download and verify)

From `casestudy/llama/`:

```bash
python fetch_corpus.py                 # the three used assets -> ./llama-b<tag>/ (about 448 MB of traffic)
python fetch_corpus.py --asset cpu     # the three cpu assets (flow only; readout unverified)
python fetch_corpus.py --root D:/somewhere   # download into another corpus root
python fetch_corpus.py --links         # print this file's links/bytes/SHA256 only; no download
python fetch_corpus.py --manifest      # corpus present: rescan and update corpus_manifest.json
```

After one download + unpack, `python aligned.py` / `python test_aligned.py` use the corpus.

## 5. Manual download (when the network is restricted)

1. Download the zips in the tables above, **keeping the file names unchanged**, and
   put them under `<corpus root>/downloads/`;
2. Run `python fetch_corpus.py --root <corpus root>`: the script verifies them, skips
   the download and unpacks directly;

Manual check (PowerShell):

```powershell
(Get-Item .\downloads\llama-b10472-bin-win-cuda-13.3-x64.zip).Length   # should equal 146,707,438
Get-FileHash .\downloads\llama-b10472-bin-win-cuda-13.3-x64.zip -Algorithm SHA256
```

The unpacked layout should be `<corpus root>/llama-b10472/`, `llama-b10595/`, `llama-b11681/`.

## 6. Verification behaviour (what the script does for you)

- A download is written to `.part`, then checked against **bytes + SHA256**; only
  after it passes is it atomically renamed;
- An existing zip is verified first: pass → skip the download; fail → delete and re-download;
- A failed check **refuses to unpack**, exits explicitly and prints the expected bytes/SHA256;
- Unpack completeness criterion: the target directory must contain
  `llama-server-impl.dll` (a half-unpacked directory counts as missing);
- `--asset cpu` goes through the same verification, but its readout is unverified (see §2).

## 7. When the corpus is absent: 16 skips are an environment fact, not a failure

- `python test_aligned.py` → `Ran 45 tests ... OK (skipped=16)`: the 29 tests that do
  not need the corpus still run; the 16 corpus-dependent ones skip with the reason;
- `aligned.py` / `misaligned.py` exit explicitly with `[FATAL]` when the corpus is
  missing and say how to restore it; they never quietly produce an empty readout;
- `C3` (template-analysis disappeared across versions) **cannot be re-run** until all
  three builds are present; the author's machine snapshot is recorded in
  `corpus_status` (`PARTIAL`, see the manifest);
- How to read the gate: `OK (skipped=16)` means "the runnable part is green + 16
  conclusions are invalid", **not** "everything verified".

## 8. Provenance and strength

- Bytes: the asset download URL's **HEAD `Content-Length`** (collected 2026-10-28; the
  body was not downloaded);
- SHA256: GitHub release asset metadata (the REST API was rate-limited, so the
  `sha256:` badge on the release page was used);
- The page's "140 MB" is a 1024-based rounding; **the exact bytes in this file are the
  measured HEAD values** — do not check them against the page's approximation;
- Source details are recorded in `_pin_source` and `_pin_api_fallback` in
  [corpus_manifest.json](corpus_manifest.json).

## 9. Consistency

Every line printed by `python fetch_corpus.py --links` must match this file item by
item — both are same-source (the same `asset_pins`). If they disagree, the ledger and
the doc have drifted: the ledger wins, and re-run `python fetch_corpus.py --links` to
reconcile.

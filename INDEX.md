# index — file navigation

One line per file: what it is, and when to read it. The per-file notes are for people looking for a file;
when you cannot tell which one to read, start here — you do not need to walk the whole tree.

Maintenance discipline: **rules go in SKILL.md, methods go in references/, evidence goes in CHANGELOG.md, navigation goes in this file**.
SKILL.md is what an agent reads on every trigger, so its length converts straight into trigger precision cost. This file holds itself to the same minimalism —
if it bloats, it defeats the reason it exists. For the argument, see README.md, "how the layering works".

## scripts/

| File | What it is · When to read it |
|---|---|
| `scripts/breakingdiff.py` | Core engine: compare / compare_n / render / render_n. Import it when you run a diff; do not read it on its own |
| `scripts/coverage_guard.py` | Coverage gate for the surface under test (three-level silence defense). Run it before compare |
| `scripts/delivery_gate.py` | Delivery gate for writing code. Before delivery it blocks the case where the spec made the commitment and the tests did not uphold it |
| `scripts/predicate_alignment.py` | Dual-calibration-point predicate-distortion self-check. Before compare, to catch P/Q all-false distortion after key-shape drift |
| `scripts/symbol_isolation.py` | Static warning for production symbols shared by P and Q. Read the intersection report when you suspect two accounts are same-source |
| `scripts/receipt.py` | Deterministic JSON receipt + blind-written expectation. Write the receipt after a compare run; when auditing, re-execute via rerun_cmd |
| `scripts/provenance.py` | Provenance tier verification (self-attested / git-object). When you need to verify that a quote really sits in some commit's blob |
| `scripts/q_ledger_check.py` | Exact gap detection for the Q ledger. Checks "is everything that should be listed actually listed" when spec commitments carry stable IDs (R-xxx) |
| `scripts/reanchor.py` | Re-anchor report for the quote ledger (alive / dead / suspect new site). When ledger line numbers drift after a spec revision |
| `scripts/hook_entry.py` | Host Stop hook entry point (artifact state machine). When installing the host hook; for the config snippet, see references/hooks.md |
| `scripts/refs_guard.py` | Static reference-integrity gate: dead links / orphans / cross-links / TOC / pointer form / pointer commitments / navigation table. Run it after any change to SKILL.md or references/ |
| `scripts/refs_guard_test.py` | Regression lock for the above (mostly fixture-driven, plus live-repo acceptance checks: a live-repo all-green anchor, an AGENTS.md structure anchor, SPEC_FILES reconciliation, and pointer commitments honored in the live repo) |
| `scripts/strength_calibration.py` | Measures the false-red ladder of candidate claim shapes and records the strength decision (shape, band, provenance, preregistration). When claims keep going red on data that is fine, or before a gate is enabled on a new claim |
| `scripts/hooks_contract_test.py` | Contract for consistency across the three copies of the hook decision order: SKILL.md / references/hooks.md / hook_entry.py docstring, checked against the frozen anchor table and exit-code mapping. Run it after changing the decision order or any of its documentation copies |
| `scripts/bd_paths.py` | Four-level bd_home resolution (BD_HOME → CLAUDE_SKILL_DIR → CLAUDE_PLUGIN_ROOT → file_relative); when set explicitly but the candidate is unusable, it raises instead of falling back. When you copy the module outside the repo and need to find the way back to the repo root |
| `scripts/dist_layout.py` | Install-layout build/verify: copy SKILL.md + scripts + references + examples from the repo root into an installable layout; verify reconciles the file sets of the three directories against the source repo in both directions. When packaging an install layout, or checking whether the copied artifacts are complete |
| `scripts/version_stamp.py` | Single source of truth for the version, sync/check: the repo-root VERSION is the source, and derived sites are compared field by field, site by site (compare first, then write). When bumping the version for a release, or checking whether derived sites are in sync |
| `scripts/leak_guard.py` | Blind-run leak guard: scans `SKILL.md` + `references/*.md` for test-assertion fingerprints (test function names, long assert messages) and grading keywords, so a context-free agent that reads only the skill learns usage rather than the grading account. Run it after editing `SKILL.md` or any reference |

Each gate module has a same-named `*_test.py`: a mutation-evidence regression lock — break it and it must go red. The core engine (`breakingdiff.py`) is covered by the `examples/` suite instead. After changing the decision logic, rerun everything (see README.md, "install and verify").

## references/

| File | What it is · When to read it |
|---|---|
| `references/writing-claims.md` | Six-step method for writing a new instance + gate-error lookup table + list of common ways to die. Read it before writing a new instance |
| `references/test-alignment.md` | Test-alignment scenario: where Q comes from and how to read it. When reconciling "test assertions vs spec commitments" |
| `references/phase-transition.md` | Phase-transition recipe: turn a red-first baseline into a regression lock. When a temporary verification script becomes a permanent test |
| `references/domain-mapping.md` | Per-domain decision table and the Q source for each domain. In cross-domain scenarios, or when unsure whether it should trigger |
| `references/receipt-format.md` | Receipt JSON field contract. Before auditing or consuming a receipt |
| `references/hooks.md` | Hook installation snippet and Windows PowerShell wrapper. When installing the host hook |
| `references/strength.md` | Strength-layer method: shape, band width provenance, preregistration and the error-mode ladder. When claims keep going red although the data is fine |
| `references/iglossary.md` | Frozen term decisions from the English rewrite (source term → English). When a term choice looks arbitrary and you want the recorded reason |

## examples/

| File | What it is · When to read it |
|---|---|
| `examples/value_type_fingerprint.py` | Starter instance: a type-fingerprint criterion, one pass and one reject. Read it on your first contact with the engine |
| `examples/iteration_chain.py` | N-account chain check in contrast: pairwise diffs vs the readout difference under chain=True. In multi-version iteration-chain scenarios |
| `examples/test_alignment_bootstrap.py` | Bootstrap reconciliation: Q = SKILL.md commitments vs P = test assertions. Must run after changing SKILL.md |
| `examples/trigger_conditions_test.py` | Regression lock for trigger conditions and the coverage gate |
| `examples/casestudy_test.py` | Casestudy instance gate: existence / count anchors / pure-script assertions. After changing any file under casestudy/ |
| `examples/forgery_poc.py` | Forgery-capability baseline (permanent; not in TEST_FILES_ALL). When checking "effective against sloppiness ≠ effective against forgery" |
| `examples/data/` | Instance corpus snapshot |

Each `*_test.py` is equivalent to the instance it belongs to: break the instance and it must go red.

| `examples/docaudit/` | Promise-vs-behavior fixture: four agent-produced CLI tools probed by context-free blind testers; 11 findings (9 promise-not-upheld, 3 silent high-severity), tiers and mechanical metrics. When a detector needs a real promise-vs-behavior target |
## casestudy/

| File | What it is · When to read it |
|---|---|
| `casestudy/README.md` | Casestudy entry point: pick a case using the four columns "what you want to do → what you learn → where to look → key teaching" + how to run + discipline for an absent corpus or toolchain. Read this first if you want to run a case |
| `casestudy/TEACHING-pdg.md` | PDG account-alignment lesson (how the data-extraction layer picks P/Q). When learning the data-extraction-layer paradigm |
| `casestudy/TEACHING-llama.md` | Industrial-scenario lesson (probe layer + ledger layer: what remains when the corpus is absent). When learning the evidence-extraction paradigm |
| `casestudy/TEACHING-malecns.md` | Strength-layer lesson (assertion strength vs the data's own occurrence pattern; the false-red staircase). When learning why true data reads as bad data |
| `casestudy/TEACHING-port.md` | Port-layer lesson (one claim, spec-driven, three implementations; the readout shape of a wrong port). When learning "a claim is an asset" |
| `casestudy/TEACHING-k8s.md` | Quadrant-reading lesson (on an existence baseline the removals land in `divergence`; a criterion the domain cannot support is refused by the gate rather than reported as zero). When learning how to read the four-quadrant table, or why a gate refusal beats a zero readout |
| `casestudy/` subdirectories: [pdg/](casestudy/pdg/), [llama/](casestudy/llama/), [malecns/](casestudy/malecns/), [port/](casestudy/port/), [hubble/](casestudy/hubble/), [k8s/](casestudy/k8s/) | Six-domain instance corpus (all but `hubble/` carry claims; hubble is a pure script). Entry points under port/ are reference.py and test_port.py; malecns/ holds the strength-layer case and its corpus manifest; k8s/ is the programming-domain case and the only one whose main account is a gate refusal |
| `casestudy/k8s/fetch_data.py` | Fetches the two official Kubernetes OpenAPI snapshots (SHA256-pinned, verified before writing). Run when the corpus is missing; note that jsDelivr currently 403s on release-1.31 |
| `casestudy/k8s/aligned.py` | Positive case: the existence readout over 2,049 request dimensions, plus the type-fingerprint account the discrimination gate refuses. Read when running the k8s case |
| `casestudy/k8s/misaligned.py` | Negative case: baseline flip / single-group false green / `$ref`-blind invented drift. Read when learning the three degenerate shapes |
| `casestudy/k8s/test_aligned.py` | 33 assertions: corpus hashes, frozen quadrant counts, the baseline flip in both orientations, the gate refusal, the degenerate fingerprints, and mutation evidence. Run when changing any of the four files above |
| `casestudy/k8s/corpus_manifest.json` | Measured ledger for the two snapshots (hashes, sizes, mirror order, which conclusion dies if a file is absent, which fetch path is broken). A record, not the evidence — re-fetch rather than trusting it |

## Root

| File | What it is · When to read it |
|---|---|
| SKILL.md | Rules and usage. An agent reads it on every trigger |
| VERSION | Single source of truth for the version, one semver line. Both the receipt's version field and version_stamp read from here |
| README.md | Project positioning, how to run it, design rationale. When a person first encounters the project |
| ORCHESTRATION.md | Multi-agent orchestration manual. Read by whoever is dispatching work |
| AGENTS.md | Repository navigation map: to change X, which file to read first and which command to run. When you do not know where to start |
| CHANGELOG.md | Incident log and mutation ledger. When tracing how a lesson came about |

# AGENTS.md — repository navigation

This file is a map: it answers only "to change X, which file do I read and which
command do I run" — it does not teach how. [SKILL.md](SKILL.md) is the source of
truth for rules and usage; this file does not restate it.

**Gate — before you write an assertion, verify one, or hand a batch to another agent, read
[`ORCHESTRATION.md`](ORCHESTRATION.md) §2.5 and §3.** Those rules bind executors, not only
dispatchers, and they are the one thing in this repository that cannot be learned by reading
code. Everything below is navigation.

## Start here

1. Decide whether the tool fits the task at hand → [SKILL.md](SKILL.md) "when to use, when not to use"
2. Writing a new instance or a new Claim → [references/writing-claims.md](references/writing-claims.md)
3. Before touching decision logic → [SKILL.md](SKILL.md) "mutation evidence" plus [README.md](README.md) "when changing this tool"
4. Tracing a lesson or an incident end to end → [CHANGELOG.md](CHANGELOG.md)
5. Not sure what a file is for → [INDEX.md](INDEX.md)
6. About to write an assertion, verify one, or split one batch across agents → [ORCHESTRATION.md](ORCHESTRATION.md) §2.5 and §3 (see the gate above; this is not optional reading for executors)

## Repository map

| Area | Location | Read when |
| --- | --- | --- |
| Rules and usage (the agent's source of truth) | `SKILL.md` | every trigger, to decide whether to use the tool |
| File navigation | `INDEX.md` | you know you need a file but not where it is |
| Design rationale and how to run | `README.md` | first time taking over, or wondering why it looks like this |
| Incident and mutation ledger | `CHANGELOG.md` | checking whether a defense line was ever proven, or tracing a decision |
| Multi-agent orchestration rules | `ORCHESTRATION.md` | before writing or verifying an assertion, or handing work to another agent — binds executors, not only dispatchers |
| Six-step method for writing instances | `references/writing-claims.md` | before writing a new Claim |
| Test alignment | `references/test-alignment.md` | reconciling "assertions vs spec claims" |
| Receipt field contract | `references/receipt-format.md` | before producing or checking a receipt |
| Red-first to regression lock | `references/phase-transition.md` | turning a temporary check into a permanent test |
| Domain mapping table | `references/domain-mapping.md` | unsure whether a cross-domain scenario should trigger |
| Host hook installation | `references/hooks.md` | before installing a Stop hook |
| Claim strength | `references/strength.md` | when claims keep going red on good data |
| Term decisions | `references/iglossary.md` | when a term choice looks arbitrary |

## Runtime entry points

| What you want to change | Entry file |
| --- | --- |
| Four-quadrant / compare_n algorithm | `scripts/breakingdiff.py` |
| Surface-under-test coverage gate | `scripts/coverage_guard.py` |
| Delivery gate | `scripts/delivery_gate.py` |
| Receipt and blind-written expectations | `scripts/receipt.py` plus `references/receipt-format.md` |
| Provenance verification | `scripts/provenance.py` |
| Hook decision entry | `scripts/hook_entry.py` plus `references/hooks.md` |
| Reference-integrity gate | `scripts/refs_guard.py` |
| Leak / local-residue guard | `scripts/leak_guard.py` |
| Claim-strength calibration | `scripts/strength_calibration.py` |

Other modules (predicate self-check, shared-symbol warning, Q-ledger gaps, quote
re-anchoring) are in the scripts/ table of `INDEX.md`.

## Source-of-truth rules

- Promises go in `SKILL.md`, methods in `references/`, evidence in
  `CHANGELOG.md`, per-file navigation in `INDEX.md`.
- `references/` articles never cross-link; the entry point is always SKILL.md
  and this file.
- Every instance under `examples/` is self-contained: script, same-named test,
  and corpus travel together; missing one means it cannot run.
- Every line here is treated as something an agent will read: test-assertion
  details and grading-side material locations do not belong here, and every
  path that appears must really exist.
- This file only maps "item → location"; steps and workflows belong to
  SKILL.md, and neither side copies the other's words.

## Verification

After changing decision logic, rerun everything, not only the file you touched:

    python scripts/ci_gate.py               # every test (28 files)

`python scripts/ci_gate.py --list` shows what would run; `--only <substring>` narrows to
one file or group while iterating. The gate discovers tests by name — a file counts if its
name starts with `test_` or ends with `_test` — so a new test is covered without being
registered: there is no second list to keep in sync, and a gate that ran nothing exits 2
rather than reporting green.

This is the same script the pre-commit hook and the GitHub workflow call, so local and CI
runs execute the same set of files. Without a corpus a case-study test takes its
no-corpus path instead of failing, which keeps a fresh clone green — and also means CI
cannot vouch for the corpus-anchored assertions. `casestudy/port` needs `go` and `rustc`;
`casestudy/malecns` needs `pyarrow` (`requirements.txt`).

Setup, the hook install, and the corpus fetch commands are in `README.md` under
"Install and verify".

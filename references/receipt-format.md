# Receipt format contract (schema v2)

Implementation source of truth: `scripts/receipt.py` (`SCHEMA_VERSION = 2`); this document is the human-readable field table. When the field table changes, bump the version and update this document in the same batch — every field in every table has a test in `receipt_test.py` pinning it, so documentation/implementation drift goes red in the tests first.

## Positioning: a receipt is self-attestation, re-execution is verification

The receipt is produced by the same party that runs compare. Someone who does not run compare can hand-write an all-green receipt that is equally green, so a receipt is in essence one more layer of self-attestation. Its value rests on exactly two things:

- Determinism: the same input necessarily produces the same bytes (the acceptance matrix is at the end);
- Field completeness: nothing the auditor needs for re-execution and comparison is missing.

The auditor's standard action is not "read the receipt" but to re-execute and compare byte for byte from `rerun_cmd`. The field table structurally follows the envelope/payload layering of in-toto/SLSA attestation (analogous structure, not analogous format); this receipt does not sign anything — when the same party controls everything on the client side, signing for yourself cannot prevent self-deception; real external evidence goes through git history (provenance tiers) and re-execution.

## The envelope (who ran this, how it is replayed)

| Field | Type | Semantics and source |
| --- | --- | --- |
| schema_version | int | Contract version; bumped when the field table changes, currently 2 |
| run_kind | "pairwise" \| "nway" | Four-quadrant 4-counter and N-account shapes are two readout families; without this key reconcile has no key to compare. A hard-wired enum; mixing them raises ReceiptError |
| claims_identity | list[{name, predicate, applies}] | The identity reconciliation key (see next section); pairwise keeps the P,Q semantic order (swapping them swaps the divergence/dominance columns), nway follows the final post-reorder order of result.names |
| domain_digest | {size, first, last} | Partial digest of the comparison domain, capturing only "did the domain change", not pretending to be a completeness proof; domain must be an already-materialized list/tuple — a generator is rejected at receipt time with `ReceiptError [RC:DOMAIN_NOT_MATERIALIZED]` (a size-0 digest would look normal, which is why it raises instead) |
| rerun_cmd | str | Replay command; structurally rejects absolute paths (drive letter/UNC/leading single slash), because an absolute path becomes a lie after changing machines or directories |
| bd_home | str | Absolute path of the skill repository root for this run. Distribution diagnostic metadata; not in reconcile's reconciliation key set (see the iron rules section at the end for the exemption) |
| bd_source | str | Resolution level of bd_home; the enum source of truth is `bd_paths.SOURCES` (env/skill_dir/plugin_root/file_relative) |
| version | str | Version number, read from `{bd_home}/VERSION`; semver single source of truth (same file and same regex as version_stamp.py) |

## The payload (readout and provenance counts)

| Field | Type | Semantics and source |
| --- | --- | --- |
| counters | dict | The key set is pinned by COUNTER_SCHEMA per run_kind: pairwise = common/divergence/dominance/neither/out_of_domain/total; nway = all_true/all_false/split/out_of_domain/total/outliers (account name → count, sparse, zero entries omitted)/pioneers (same)/ratchet_total/ratchet_trusted/anchor |
| witnesses | dict[list[str]] | Witness list (stringified); subject to max_witness truncation and discovery order, so only soft reconciliation |
| max_witness | int | Witness truncation threshold — reading witnesses requires knowing it |
| provenance_summary | dict[str, int] | Provenance tier counts, bucketed by source_kind as-is; keys are not narrowed by an allowlist, and unknown tiers also appear explicitly (enumeration complete) |
| expected | object \| null | Blind-write reconciliation block (see "Blind-written expectations"); **null = never reconciled, not reconciled successfully** — never having reconciled and having reconciled are not the same thing, so this key must not be omitted |

## claims_identity is an identity reconciliation key, not a completeness proof

The identity string = `module name.qualname`. Two closures built by the same factory can behave differently with the same identity — so it can only reconcile "did the function change / did the order change"; its tamper resistance is zero. Tamper resistance goes through external evidence (provenance's git-object tier): add `source_obj` to a Claim ("full 40-char lowercase hex sha:path inside the repo", forward slashes) and it is upgraded to git-object, with git object content addressing as the backstop. Do not use this field as a hash.

## Reconciliation context = a single delivery window

claims_identity changing during reconciliation has only two possible causes, and diffs names which one:

1. the input changed: the account function/name/order differs from the blind write — expectation expired; this is a correct signal, not a false alarm (even if behavior is unchanged and the counters all match, it still surprises);
2. the readout is wrong: the identity is unchanged while counters changed — this is the usual "result does not match the expectation".

Both enter the gate. Cross-session reconciliation is not done here: cross-session reconciliation goes through rerun_cmd replay and third-party audit; a call order inside a single window cannot be proven once it leaves this process.

## Provenance tiers: the verification mechanism

Product meaning (Claim.source_kind has only two tiers, self-attested ≈ SLSA L1, git-object ≈ SLSA L2, does not defend against source forgery, adding source_obj upgrades it) is in the "Provenance tiers" section of SKILL.md; here we record the verification mechanism itself. Verification goes through `provenance.verify(claim, repo_root=...)`: **repo_root is injected explicitly**, never guessed from the working directory — "verified" against the wrong repository is worse than no verification. quote is compared verbatim in the blob of that commit: **a blob over the limit raises** rather than truncating (truncated comparison would let a prefix forgery through); line endings are normalized on both sides **CRLF**→LF before matching and recorded. Failure at any step is a ProvenanceError, and the "verified" label is given only after it passes.

## Three exit-code tiers and the hook-layer mapping

| Code | Semantics | How it is produced |
| --- | --- | --- |
| 0 | pass (including: no blind-written expectation to reconcile — no expectation, no gate) | gate_exit_code(receipt) |
| 1 | gate failed; the only source = reconcile surprise | gate_exit_code(receipt) |
| 2 | runtime error (no receipt produced) | carried by ReceiptError and other exceptions |

The cost of mixing tiers is concrete: the hook receives one code and cannot tell "should block" from "should fix the tool". The hook-layer convention: **1 maps to 2** (the report goes to stderr, borrowing the host's stderr feedback channel), 2 passes through. The mapping lives in the hook layer, not in receipt — receipt reports 0/1/2 faithfully to the caller, and how to present it to the host is the adapter layer's decision.

## Blind-written expectations

Write the expectation before running the readout, to prevent "writing the expectation after seeing the result". The expected file (`write_expected` writes it to disk) schema:

| Field | Notes |
| --- | --- |
| schema_version / run_kind / claims_identity / domain_digest | Same meaning as the receipt envelope, for reconcile to hard-compare key by key |
| expected_counters | Complete per COUNTER_SCHEMA: missing keys, extra keys (including misspelled ones), and type impersonation (bool posing as int) are all rejected at write time — a partial expectation leaves room for "comparing selectively", and a misspelled key is silently skipped during reconciliation |
| expected_witnesses | Optional; key set pairwise = divergence/dominance, nway = split/ratchet |
| written_marker | Content addressing: the sha256 of the canonical bytes of all fields after removing the marker itself (the witness list is in scope too); if the file is touched after the blind write, **editing the expectation afterwards fails the check on the spot**, and reconciliation goes red on the spot |

Call-order main semantics: `write_expected → compare → reconcile(expected, receipt)`, and the reconciliation result block is assigned to receipt["expected"]. reconcile accepts only the handle from write_expected in this process (token check) — no json on disk can prove the "write first, then run" call order; this check guards against "forgot to write first", not against forgery.

**mtime is reference information, not evidence**: one `os.utime` call can forge it, and clone/checkout resets it. It enters the receipt only as a sloppiness guard (field name expected_file_mtime, the only time-typed field in the allowlist) — **mtime is downgraded to reference information only**; it guards against sloppiness, not forgery. Real external evidence is third-party auditability: the expected file and the receipt land in git history one after the other, and an expectation added afterwards leaves a trace; audit (third-party pure comparison, call_order=external-load) checks the marker recorded in the receipt against the current hash of the expected file — a mismatch means the expectation was touched after reconciliation.

Two tiers of reconciliation: **hard counter reconciliation** and **soft witness-list reconciliation**. The boundary and why:

- hard counter reconciliation (enters the gate): run_kind, claims_identity, domain_digest, counters, written_marker compared key by key; a missing key, an extra key, or any inequality sets surprise=true, and the difference list carries field names and both values (bare numbers cannot be reconciled).
- soft witness-list reconciliation (does not enter the gate, only witness_notes): witnesses. Reason: witnesses are subject to max_witness truncation and discovery order, and the witness list of even the same readout is not stable bytes; a hard comparison necessarily produces false positives — with enough false positives, the gate gets switched off as noise.

## Determinism iron rules and the acceptance matrix

Iron rules: sort_keys fixes key order, ensure_ascii=False, UTF-8 without BOM, a single trailing newline, read-back comparison after writing ("written" is defined by the read-back result), reconciliation keys contain no timestamps and no absolute paths.

v2 narrowing boundary: `bd_home/bd_source/version` are distribution diagnostic metadata, not reconciliation keys — reconcile's hard key set does not include them, and the expected file does not contain them either (the blind write precedes the run, so there is no path to record). Among them bd_home is the running machine's absolute path, and **cross-machine byte identity is not promised**: this is honest degradation, not an exception leak; when cross-machine comparable bytes are needed, strip these three fields before comparing. The absolute-path prohibition narrows accordingly to "apart from the bd_home key value, no drive letter/UNC anywhere in the text"; the exemption covers this one key only.

| Acceptance item | Action | The test that pins it |
| --- | --- | --- |
| delete the receipt and rerun, byte-identical | write → delete → rewrite, compare bytes | receipt_test.test_delete_receipt_and_rerun_is_byte_identical |
| rerun from a different CWD, byte-identical | rewrite after chdir, compare bytes | receipt_test.test_cwd_change_is_byte_identical |
| no timestamps, no absolute paths | serialized text forbids ISO dates and time-like keys (allowlist: expected_file_mtime) + structural rejection in rerun_cmd | receipt_test.test_receipt_json_has_no_timestamp_and_no_absolute_path, test_rerun_cmd_with_absolute_path_is_refused |
| UTF-8 without BOM, write and read back | byte-level assertion + verify_receipt_file must go red after tampering | receipt_test.test_receipt_write_is_utf8_no_bom_and_readback_is_enforced |

Auditor review entry points: `verify_receipt_file(receipt, path)` (disk bytes == canonical bytes) and `audit(load_expected(path), receipt_path)` (pure expectation × receipt comparison, no gate semantics).

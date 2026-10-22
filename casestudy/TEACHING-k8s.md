# Baseline, and which column the product lands in

## 0. Why this case is in the portfolio

The other four cases teach **how to write a claim**: how to align accounts (pdg),
how to extract evidence (llama), how strong a claim may be (malecns), how to
replace an implementation without moving the claim (port). All four are about the
input side.

This case teaches **how to read a quadrant** — and it is the only case in the
portfolio sitting in the programming domain, which is also the domain the core
engine was written for.

Its proposition, stated once:

> **On an existence baseline, a removal lands in the `divergence` column, not the
> `dominance` column. The product column is a function of the baseline, not of
> the data.**

That sounds like a naming quibble. It is not: removals are the entire reason
anyone runs a breaking-change audit, and a tool (or a reader) that has
internalised "the dominance column is the product column" reports the *additions*
and calls it a day.

---

## 1. The corpus

Two official OpenAPI snapshots, unmodified:

| | version tag | size | SHA256 (first 16) |
|---|---|---:|---|
| old | `kubernetes/kubernetes@release-1.28` | 2,955,128 B | `44ff3c98bb011964` |
| new | `kubernetes/kubernetes@release-1.31` | 3,277,085 B | `ddcb3d5c3d85849f` |

Both under `api/openapi-spec/swagger.json` in the repository, fetched by
`fetch_data.py`. They do not go into git — `casestudy/.gitignore` excludes them —
so the fetch script ships with pinned hashes. **A readout computed over the wrong
bytes is still a readout**, so `test_aligned.py` verifies both hashes before it
verifies anything else.

1.31 is a *minor* bump. Everything below is what that minor bump did.

### 1.1 A fetch path that rotted, recorded rather than papered over

Measured 2026-10-21: the jsDelivr path returns **HTTP 200 for 1.28** and
**HTTP 403 for 1.31**, with the body

```
Package size exceeded the configured limit of 50 MB. Try
https://github.com/kubernetes/kubernetes/tree/release-1.31/... instead.
```

Three things worth taking from that, all of which generalise past this case:

1. **It is not an outage.** It is a per-package size policy applied at pack time.
   1.28 succeeds only because a cached package exists; 1.31 has never been packed,
   so serving it has to build it and hits the ceiling. **A path that works for one
   asset and fails for the next is not flaky — it is order-dependent**, and "retry"
   is the wrong reflex.
2. **The remediation it suggests is a trap.** That URL is a GitHub **HTML tree
   page**, not a raw file. Follow it verbatim and you save HTML into a `.json`
   slot. A size check will not catch it, and neither will "does it start with
   `{`" if you are unlucky about what the error page contains. The **SHA256 check
   is the only thing that catches it mechanically**, which is why
   `fetch_data.py` verifies before it writes and why the hashes are pinned in the
   script rather than only in the manifest.
3. **This is llama's failure class one level worse.** llama lost the data. This
   lost the road to the data. Both belong in the same place — the manifest's
   `corpus_status`, naming **which conclusion dies**, not merely that something
   is gone.

---

## 2. The parameter space

One **request dimension** = `(path, method, param_name)`.

* An operation with no declared path/query/body/formData parameters contributes
  one point at `param_name = ""`. Operation-level and parameter-level points live
  in the same space on purpose: a removal is a removal whichever level it
  happened at, and keeping them apart would split the count for no analytical gain.
* Methods are restricted to the seven HTTP verbs. A swagger `paths` object also
  carries non-operation keys; those are skipped, not treated as methods.
* `in` is restricted to `path` / `query` / `body` / `formData` — the four places a
  client actually supplies something.

| | points |
|---|---:|
| union (the comparison domain) | **2,049** |
| common to both | 1,499 |
| only 1.28 | **193** |
| only 1.31 | 357 |
| neither | 0 |

---

## 3. Account 1 — existence, and the column flip

```
P  "this dimension exists in release-1.28"
Q  "this dimension exists in release-1.31"
```

| quadrant | reading | count | share |
|---|---|---:|---:|
| common | in both | 1,499 | 73.2% |
| **divergence** | **only 1.28 — the removals** | **193** | 9.4% |
| dominance | only 1.31 — the additions | 357 | 17.4% |
| neither | — | 0 | 0.0% |

**193 points is a breaking-change list.** A client that calls any of them gets a
404 on 1.31+. And it sits in `divergence`, because P is the *old* account:
"present in the old one, absent from the new one" is exactly `P ∧ ¬Q`.

Swap the two accounts and nothing about the data changes — only the column:

| orientation | divergence | dominance |
|---|---:|---:|
| P = old spec | **193** (removals) | 357 (additions) |
| P = new spec | 357 | **193** |

`test_aligned.py` asserts **both orientations**. An assertion suite that only
ever ran one would still pass if the quadrant mapping were transposed — which is
the exact failure this case exists to make impossible to miss.

### 3.1 193 points → three rows

The count is useless to a person; the group is not.

| API group | removed in 1.31 | added in 1.31 |
|---|---:|---:|
| `resource.k8s.io` | **99** | 118 |
| `flowcontrol.apiserver.k8s.io` | **55** | 55 |
| `networking.k8s.io` | **39** | 47 |
| `admissionregistration.k8s.io` | — | 46 |
| `storage.k8s.io` | — | 40 |

Three groups account for all 193 removals — `v1alpha2`, `v1beta2` and
`v1alpha1` paths respectively. The aggregation is not a summary of the
four-quadrant table; it is **the product**, and it is a different kind of object
from the count. `TestRemovalGroupAggregation` pins all three numbers and their sum.

---

## 4. Account 2 — a criterion the gate refuses, and why that is louder than zero

The second account is a type fingerprint: "this parameter's declared type is
unchanged between the two specs". It does not produce a readout. It produces a
**refusal**:

```
BLOCKED  [BD:READING_DISCRIMINATION_ZERO]
2 interpretations share the same value as this claim at all 3 test points
→ the test set cannot detect formalization drift and is treated as invalid
```

### 4.1 Why

727 common parameter dimensions. Across them the declared type takes exactly two
values: `string` in 571, undeclared in 156. It never changes. So the body (type
fingerprint) and both of its looser readings (value equality, repr equality)
return the same value at every test point.

A test set on which **nothing can separate the body from its own approximations**
cannot detect formalisation drift. Rather than pass it, the gate declares the
source tests invalid.

### 4.2 Why this is better than "zero differences"

This is the part worth carrying to another domain.

| outcome | what it invites you to conclude |
|---|---|
| readout says 0 differences | "the criterion found nothing, fine" — conversation over |
| gate refuses the claim | "is this criterion applicable here **at all**?" — conversation starts |

The refusal is not a smaller result. It is a **categorically different** one, and
it is the one that carries information: a criterion with no purchase in a domain
should be removed from the registry for that domain, not left in place reporting
zeros forever.

It also reproduces, from a **gate refusal** rather than from a count, the entry in
`references/writing-claims.md`'s criterion-selection table that reads "type
fingerprint: only effective where value types have freedom; zero hits in a
strongly-typed contract domain (K8s)". A claim in this repository that was
previously asserted is now re-derived.

---

## 5. Three degenerate readouts

All measured, all pinned into assertions.

### 5.1 M1 — the baseline flip (see §3)

Same data, same total, product column moves. Reported by `misaligned.py`.

### 5.2 M2 — scoping to one group manufactures a false green

Restrict the comparison to `resource.k8s.io`:

| | points |
|---|---:|
| comparison domain | 218 |
| common to both | **1** |
| removed | 99 |
| added | 118 |

A reviewer who scopes to one group and then reads the common set sees **one
dimension and zero differences** — while 217 dimensions inside the scope they
chose go unread. The readout is complete, correctly formatted, and silent.
Nothing in the four-quadrant table flags it.

This is level-2 silence (incomplete extraction producing a false zero). The only
thing that catches it is the coverage guard in front of `compare`, asking the
question from SKILL.md §"Three-level silence":

> **If this change were wrong, would the readout move? No → it is not on the
> surface under test.**

### 5.3 M3 — not dereferencing `$ref` invents drift

In release-1.28, 2,089 of 2,916 declared parameters are `$ref`; only 827 are
inline. In 1.31 it is 2,318 of 3,230, with 912 inline.

An extractor that reads `type` directly sees 827 and 912 — a difference of **85**.
That 85 is not a change in the Kubernetes API. It is the extractor failing to
resolve references, reported in the same column as real drift.

Before believing any zero, print three lines: the empty-scalar rate, the number
of distinct values, and the most common values. A real green and a fake green
separate at a glance.

---

## 6. A bug this case caught, kept because it is instructive

While writing `aligned.py` the group aggregator produced

```
TypeError: unsupported format string passed to tuple.__format__
```

Root cause: `api_group()` was handed the whole `(path, method, param)` dimension
instead of its path component. `"/apis/" in p` then tested **tuple membership**,
not substring — always `False` — so every group label silently degraded to the
dimension itself.

The uncomfortable part, and the reason `TestMutationEvidence` keeps both halves:

* **The four-quadrant readout did not notice at all.** Counts identical before
  and after. `test_mutation_a_is_invisible_to_the_four_quadrant_readout` pins
  that blindness explicitly — it is a fact about the tool, not a defect to fix.
* **Only the aggregation broke**, and it broke at the first format string rather
  than producing wrong labels.

Had the aggregation happened to stringify a tuple without complaint, this would
have shipped as a table of 193 unique "groups". The mutation assertions now check
that the broken version explodes the label set from 3 entries to 193 while the
totals stay correct — a failure with a *shape*, which is what actually gets caught.

---

## 7. Readout summary

| | |
|---|---|
| comparison domain | 2,049 |
| common / divergence / dominance / neither | 1,499 / **193** / 357 / 0 |
| out-of-domain skips | 0 |
| removals by group | `resource.k8s.io` 99 · `flowcontrol.apiserver.k8s.io` 55 · `networking.k8s.io` 39 |
| type-fingerprint account | **refused by the discrimination gate** (`READING_DISCRIMINATION_ZERO`) |
| verdict | parallel — neither account contains the other |
| attestation tier | `self-attested` (supply `source_obj` to promote to `git-object`) |

**Attestation, stated plainly.** The two corpora are official unmodified
snapshots and their hashes are pinned — that part is verifiable. But the claims
built on them are `self-attested`: the tool confirms the accounts are internally
consistent, not that they are true. Anyone can check the hashes; nobody can check
the accounts without reading the code.

---

## 8. What holds

1. **The product column follows the baseline.** On an existence baseline the
   removals are in `divergence`. Both orientations are asserted so the mapping
   cannot be transposed silently.
2. **A gate refusal carries more information than a zero readout**, and the two
   must not be reported in the same voice.
3. **Scoping can manufacture a clean readout.** One group, one common dimension,
   217 unread — with nothing in the table objecting.
4. **Incomplete extraction shows up as drift, not as absence.** 85 points of it,
   here.
5. **A fetch path can rot while the corpus is still perfectly downloadable from
   somewhere else**, and the error message it prints can point at a file of the
   wrong kind.

## 9. What does not hold

1. The parameter space is `(path, method, param_name)`. A different but equally
   defensible definition — one that dereferences `$ref`, or one that groups
   operations rather than parameters — produces **different counts on the same
   bytes**. The numbers in this file are pinned to *this* definition and are not
   a property of Kubernetes.
2. Nothing here says anything about what an upgrade should cost. The tool reports
   where two accounts disagree; it does not rank them.
3. The corpus covers two versions. Multi-version chains want `compare_n` with
   `chain=True` for ratchet violations across more than two points, which this
   case does not exercise.

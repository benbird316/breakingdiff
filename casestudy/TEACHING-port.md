# Port layer: claims are assets, implementations can be replaced

> The first two lessons cover "how to extract P/Q" (the data-extraction layer) and "how to extract evidence" (the probe layer).
> This lesson turns to a different axis: **replace the entire implementation, but the account must not change**.
> How to read it: read the proposition below, run `python test_port.py` once, then come back to the readout table.

---

## 1. What this lesson teaches

The most dangerous class of change in real engineering is not "getting it wrong" — it is **a legal rewrite**:

- Rewriting a piece of Python as Rust / Go (AI translation made this cheap);
- Rewriting the same tool in another language, where external behavior should not change;
- But nothing enforces that "should" — the tests may have been rewritten along with it, and the green is meaningless.

This case shrinks the problem to a reproducible scale: port only the **computation core** of
`scripts/breakingdiff.py` (the pairwise four quadrants + verdict, the decision part of its 402 lines), **change only the language, not the account**.

The proposition in one sentence:

> **Claims are assets; implementations can be replaced.** The same `port/claims.json` goes to the real Python core,
> the Go port, and the Rust port: the three readouts must match point by point; a deliberately wrong port must be caught by the differential in a predictable shape.

---

## 2. The contract: `port/claims.json`

The single source of truth for all three implementations. Its shape (excerpt):

```json
{
  "schema_version": 1,
  "domain": [{"n": 0}, {"n": 1}, "..."],
  "pairs": [{
    "id": "band-vs-ge",
    "P": {"name": "P: n >= 12",
          "applies":   {"op": "always"},
          "predicate": {"op": "ge", "field": "n", "value": 12},
          "source": "casestudy/port/claims.json#band-vs-ge.P",
          "quote": "P: n >= 12",
          "source_tests": [{"point": {"n": 11}, "expected": false},
                           {"point": {"n": 12}, "expected": true}]},
    "Q": {"...": "..."},
    "expect": {"common": 8, "divergence": 4, "dominance": 2, "neither": 10,
               "out_of_domain": 1, "verdict": "parallel",
               "divergence_witness": [20, 21, 22, 23],
               "dominance_witness": [10, 11]}
  }]
}
```

Two design decisions run as an undercurrent through this lesson:

1. **verdict uses keys, not prose.** The five keys `parallel` / `equivalent` / `p_strict_contains_q` /
   `q_strict_contains_p` / `disjoint` are a cross-language contract; the human-readable rendering is generated only
   on the Python side and **never enters reconciliation**. Prose can change; keys cannot — this is the smallest example of "prose is not a contract".
2. **There are only four operators**: `always` / `ge` / `gt` / `band`. Four are enough to express the decision chain;
   if they are not, do not add more. That is why the Rust side can **hand-write JSON parsing with zero crates**: when the contract is small, zero dependencies is an option, not a sacrifice.

---

## 3. How the three implementations divide the work

| Implementation | Path | Responsibility | Dependency |
|---|---|---|---|
| Python reference | `port/reference.py` | Read JSON → construct the real `breakingdiff.Claim` → run `compare()` → compare against expect | Repository core |
| Go port | `port/impl_go/main.go` | Independent implementation of operator evaluation + four quadrants + verdict keys + witness points | Standard library `encoding/json` |
| Rust port | `port/impl_rust/main.rs` | Same as above, with a hand-written minimal JSON parser | **zero crates** |

The reference implementation deliberately **reuses** none of the port code: it runs the repository's real
core and is the comparison baseline for the other two. If all three copied the same implementation, consistency would just be the same code running three times.

---

## 4. Readout table (normal path, measured)

```
[band-vs-ge] common=8 divergence=4 dominance=2 neither=10 out_of_domain=1 verdict=parallel
        rendered: Parallel: neither contains the other (P: n >= 12 has 4 unique point(s), Q: 10 <= n < 20 has 2 unique point(s))
[equivalent] common=13 divergence=0 dominance=0 neither=12 out_of_domain=0 verdict=equivalent
        rendered: Equivalent over the comparison domain
[strict-contains] common=10 divergence=3 dominance=0 neither=12 out_of_domain=0 verdict=p_strict_contains_q
        rendered: P: n >= 12 strictly contains Q: n >= 15

Reference implementation matches claims.json expect item by item (3 pairs)
```

All three implementations match point by point (the `*_reads_same_as_reference` assertions in `port/test_port.py` hold this).
Every readout table has an assertion behind it: it is not "the document says so", it is "the code must come out exactly like this".

---

## 5. A wrong port: `--mutant boundary`

The most common bug during a port is **a boundary that is off by one**. Both ports keep a wrong path of the same
name: implement `ge` as `>` (instead of `>=`). It is deliberately kept, off the main path:

```bash
go run main.go -spec ../claims.json -mutant boundary      # or
.\port_rust.exe --spec ../claims.json --mutant boundary
```

Readout changes (measured, consistent with the assertions):

| pair | field | normal | mutant | note |
|---|---|---|---|---|
| band-vs-ge | common | 8 | **7** | n=12 drops out of the common domain |
| band-vs-ge | dominance | 2 | **3** | n=12 falls into the dominance domain (witness `[10,11]` → `[10,11,12]`) |
| equivalent | verdict | equivalent | **q_strict_contains_p** | `n>11` and `n>12` are no longer equivalent; n=12 becomes a dominance point |
| strict-contains | divergence | 3 | **3** | but the witness changes from `[12,13,14]` to `[13,14,15]` — the points change, the count does not |

The last row is the most valuable part of this case: **same count, different witness points**.
A gate that compares only totals would let it pass; the claim differential tells you "which point".

`TestMutantAgreement` pins one more thing: Go and Rust, written wrong independently in the same way → identical readouts.
This is the reverse proof that "the account does not depend on the implementation": **even the bug has its shape pinned by the spec**.

---

## 6. Boundaries and gaps (registered honestly)

| Item | Status | What is missing, and which conclusion becomes invalid |
|---|---|---|
| pairwise four quadrants | covered | — |
| N-way classification (`compare_n`: outliers / ratchet / split) | **not ported** | The conclusion "drift across multiple accounts" is outside this case's range; `order_key` is a callback and needs the next layer of design |
| `render` prose layout | not ported | Cross-language comparison covers structure only; prose correctness still belongs to the Python side |
| Go / Rust toolchain | external dependency | Without the toolchain the related cases are skipped: **the Go/Rust consistency conclusion is invalid and must not be read as a pass** (following llama's corpus discipline) |
| semantic-level N-way | see above | — |

---

## 7. Rerun and verify

```bash
python reference.py          # reference readout + reconciliation against expect
python test_port.py          # 12 items; all green with the toolchain, related items skipped and named when missing
go run impl_go/main.go -spec claims.json
.\impl_rust\port_rust.exe --spec claims.json
```

`port/test_port.py` compiles on the spot with `rustc` when needed (the artifact `port/impl_rust/port_rust.exe` is already in `.gitignore`).

---

## 8. What this lesson generalizes to

- **The acceptance slot for AI translation**: translation made "rewriting" cheap, but it did not make
  "equivalence" cheap. A claim spec is a more portable acceptance surface than a test suite — tests bind to a language, claims do not.
- **Adjudication reports only divergence**: this case never says "Go is right or Rust is right", only "which
  point differs between the two accounts". Right and wrong are judged by whoever holds the spec — the cross-language form of "report divergence, do not adjudicate".
- **A wrong port is also an account**: each of the two languages is wrong in its own way, and the readout
  still has the same shape. That is exactly the behavior the tool should have: it does not lean on approximation, it leans on both sides being constrained by the same spec.

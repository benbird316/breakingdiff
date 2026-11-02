# Downstream evidence hand-off

The four quadrants and the shape counts are the readout. Some consumers need more than
the readout: an attribution lab wants the per-point verdicts to locate *where* two
accounts diverge; an evidence gate wants to re-derive a claim over the same parameter
points before trusting it. `compare_n` already computes a verdict vector at every
in-domain point; by default it discards each vector after classifying it. This article
describes the opt-in that keeps them, and the anchor that makes them reproducible —
without ever widening the gate.

## The opt-in: keep_vectors

`compare_n(claims, domain, ..., keep_vectors=True)` fills, on the returned result:

- `vectors`: one `(point, verdict-tuple)` per in-domain point. The tuple's column order
  is the account order **after** any `order_key` re-sort, not the order the caller passed
  in. Read `result.names` alongside it; attributing a column to the wrong account is the
  same class of mistake as a mis-anchored baseline.
- `outlier_witnesses` / `pioneer_witnesses`: account index -> located witness points,
  capped at `max_witness`. These add *location* to the existing outlier/pioneer counts.
- `ratchet_points`: the number of **distinct points** carrying at least one ratchet
  violation. `ratchet_total` counts (old,new) pairs, so one point can contribute several
  pairs; `ratchet_points` counts it once. Both need `chain=True`; the distinct-point form
  additionally needs the opt-in.

The default is `keep_vectors=False`. On the default path every new field is empty or zero
and every pre-existing field is unchanged, byte for byte. The flag does not alter any
count, witness, verdict or the ratchet check itself; it only decides whether the
per-point material is retained. Treat it as a read-only switch over the same computation.

## The anchor: vector_digest

`vector_digest(result.vectors)` returns `sha256:<64 hex>` over the full sequence. Three
properties make it usable as evidence:

1. **Full, not capped.** Every row in `vectors` is hashed. Witness lists are capped for
   display; the digest is not, so a truncated witness cannot masquerade as the whole.
2. **Order-independent.** Rows are sorted by a serialized point key before hashing, so
   the result does not depend on the order the domain was iterated. Reordering the input
   and recomputing yields the same anchor.
3. **Fail-loud.** A point that cannot be serialized to a stable key raises immediately.
   Pass `key=` (a callable mapping a point to a stable identity) for domain points that
   are not directly JSON-serializable. Silently dropping an unserializable row would hash
   a shorter sequence while looking identical.

An empty `vectors` hashes to a fixed constant. Check `in_domain > 0` before reading a
digest as proof that any points were compared — a zero domain is a zero readout, not a
pass.

## Replay recipe

1. Run `compare_n(claims, domain, keep_vectors=True, order_key=...)` and store
   `result.vectors` plus `vector_digest(result.vectors)` alongside the run's inputs.
2. To verify, re-run the identical call from the same claims and domain, recompute the
   digest, and compare the two strings. Equal digests mean the per-point verdicts were
   reproduced exactly; the predicates are pure, so this is a mechanical check.
3. Keep the digest with the material that cites it, not inside the gate that judges it.

## Discipline: evidence is not a gate input

This is the boundary that keeps the feature from manufacturing false alarms. The
receipt's hard reconciliation compares aggregate counters; per-point data (witnesses,
and now vectors) depends on discovery order and truncation and is therefore reconciled
softly, or not at all. Toggling `keep_vectors` must not move a single byte of the receipt.
A hard comparison over per-point data would misfire the moment witness ordering or the
`max_witness` cap changed, or the moment a replay omitted the flag — a false red that
looks exactly like a real discrepancy.

So: **retain the vectors and the digest as evidence for a downstream consumer or a human;
never promote either into the receipt's blocking comparison.** The digest is a
reproducibility anchor you can re-derive, not a verdict the tool renders. A verdict on
which account is right still belongs to an external anchor or a human — the opt-in changes
where the evidence lives, not who adjudicates it.

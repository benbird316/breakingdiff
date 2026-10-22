# -*- coding: utf-8 -*-
"""The assertion surface of the port-layer case: three implementations agree + a wrong port shifts as predicted.

[What this file guards]
The teaching proposition of this case is "claims are assets, implementations can be
replaced". So the assertion surface is not "the script runs" but three harder things:

  1. The Python reference implementation (running the repository's real core
     `breakingdiff.compare`) matches `claims.json` expect item by item;
  2. The Go / Rust ports match the reference implementation **point by point** — one
     bit off is port drift;
  3. A deliberately wrong port (`--mutant boundary`: ge implemented as gt) must produce
     a **predictable** readout shift, and the two languages must be wrong in exactly the
     same way (a wrong port can also be differentially compared).

When a toolchain is absent the related cases skip and the output states what is
missing — following llama's corpus discipline: missing is not "pass", it is "this
conclusion is invalid".

How to run: python test_port.py
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _find_scripts_root():
    """Search upward for breakingdiff.py without hard-coding the level — moving the
    directory should not change the failure mode."""
    cur = _HERE
    while True:
        if os.path.isfile(os.path.join(cur, "scripts", "breakingdiff.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit(
                "[FATAL] cannot find scripts/breakingdiff.py walking upward. "
                "       This case must run inside the breakingdiff repository")
        cur = parent


_ROOT = _find_scripts_root()
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, _HERE)

import reference  # noqa: E402

SPEC = os.path.join(_HERE, "claims.json")
GO_DIR = os.path.join(_HERE, "impl_go")
RUST_DIR = os.path.join(_HERE, "impl_rust")
RUST_BIN = os.path.join(RUST_DIR, "port_rust" + (".exe" if os.name == "nt" else ""))

HAS_GO = shutil.which("go") is not None
HAS_RUSTC = shutil.which("rustc") is not None

VERDICT_KEYS = {"parallel", "equivalent", "p_strict_contains_q",
                "q_strict_contains_p", "disjoint"}
ALLOWED_OPS = {"always", "ge", "gt", "band"}


def _load_spec():
    with open(SPEC, encoding="utf-8") as f:
        return json.load(f)


def _run(cmd, cwd, timeout=180):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    return proc.returncode, out, err


def _parse_payload(out):
    """Take the last JSON object on the command line: go run may print build noise in front."""
    for line in reversed([line for line in out.splitlines() if line.strip()]):
        if line.lstrip().startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON payload in the output: {out[:400]!r}")


def _reference_results():
    return [{k: v for k, v in r.items() if k != "rendered"}
            for r in reference.run(_load_spec())]


def _go_results(mutant=None):
    cmd = ["go", "run", "main.go", "-spec", SPEC]
    if mutant:
        cmd += ["-mutant", mutant]
    code, out, err = _run(cmd, GO_DIR)
    return code, _parse_payload(out), err


def _ensure_rust_bin():
    """Build the Rust binary when it is missing **or older than its source**.

    The binary is gitignored and built on the spot, so a checkout that carries an
    older build is a real case. Reusing it because "the file exists" makes the Rust
    side pass against code that is no longer in the tree — a green that tests nothing
    shipped here. Compare mtimes; a same-second build is treated as current.
    """
    src = os.path.join(RUST_DIR, "main.rs")
    if os.path.isfile(RUST_BIN) and os.path.getmtime(RUST_BIN) >= os.path.getmtime(src):
        return
    code, out, err = _run(["rustc", "-O", "main.rs", "-o", RUST_BIN], RUST_DIR)
    if code != 0:
        raise AssertionError(f"rustc compilation failed ({code}): {err or out}")


def _rust_results(mutant=None):
    _ensure_rust_bin()
    cmd = [RUST_BIN, "--spec", SPEC]
    if mutant:
        cmd += ["--mutant", mutant]
    code, out, err = _run(cmd, RUST_DIR)
    return code, _parse_payload(out), err


class TestClaimSpecContract(unittest.TestCase):
    """claims.json is the contract all three sides read; pin the contract shape before talking about readouts."""

    def test_schema_version_and_domain(self):
        spec = _load_spec()
        self.assertEqual(spec["schema_version"], 1,
                         f"schema_version drifted: {spec['schema_version']}")
        self.assertEqual(len(spec["domain"]), 25,
                         f"the parameter-point count changed: got {len(spec['domain'])}")
        self.assertEqual([p["n"] for p in spec["domain"]], list(range(25)),
                         "the parameter points must be the consecutive integers n=0..24, or the witness assertions are meaningless")

    def test_claim_ops_stay_inside_declared_set(self):
        for pair in _load_spec()["pairs"]:
            for side in ("P", "Q"):
                claim = pair[side]
                for face in ("applies", "predicate"):
                    op = claim[face]["op"]
                    self.assertIn(op, ALLOWED_OPS,
                                  f"{pair['id']}.{side}.{face} used an out-of-domain operator {op!r}")

    def test_every_claim_binds_provenance(self):
        for pair in _load_spec()["pairs"]:
            for side in ("P", "Q"):
                claim = pair[side]
                self.assertTrue(claim["source"].strip(), f"{pair['id']}.{side} is missing source")
                self.assertTrue(claim["quote"].strip(), f"{pair['id']}.{side} is missing quote")
                self.assertTrue(claim["source_tests"], f"{pair['id']}.{side} is missing source_tests")

    def test_verdict_vocabulary_is_closed(self):
        for pair in _load_spec()["pairs"]:
            self.assertIn(pair["expect"]["verdict"], VERDICT_KEYS,
                          f"{pair['id']}'s expect.verdict is not in the closed set")


class TestReference(unittest.TestCase):
    """The reference implementation = repository core + JSON spec; it is the comparison baseline for the other two ports."""

    def test_reference_matches_expect(self):
        spec = _load_spec()
        results = reference.run(spec)
        diffs = reference.compare_against_expect(spec, results)
        self.assertEqual(diffs, [], "the reference implementation does not match claims.json: " + "; ".join(diffs))

    def test_reference_witnesses_are_pointwise(self):
        band = _reference_results()[0]
        self.assertEqual(band["divergence_witness"], [20, 21, 22, 23],
                         f"divergence witness drifted: got {band['divergence_witness']}")
        self.assertEqual(band["dominance_witness"], [10, 11],
                         f"dominance witness drifted: got {band['dominance_witness']}")

    def test_verdict_key_matches_rendered_text(self):
        """The key and the rendered wording must derive from the same source: changing
        the wording must not move the key, and a wrong key cannot be saved by the wording."""
        spec = _load_spec()
        results = reference.run(spec)
        for pair, got in zip(spec["pairs"], results):
            want_key = pair["expect"]["verdict"]
            self.assertEqual(got["verdict"], want_key,
                             f"{pair['id']} key mismatch: {got['verdict']} vs {want_key}")
            self.assertTrue(got["rendered"].strip(),
                            f"{pair['id']} rendered empty — the rendered wording is outside the cross-language contract, but it must not be empty")


@unittest.skipUnless(HAS_GO, "the go toolchain is missing: the two Go port conclusions are invalid, not a pass")
class TestGoParity(unittest.TestCase):
    def test_go_reads_same_as_reference(self):
        code, payload, err = _go_results()
        self.assertEqual(code, 0, f"the Go normal path should exit 0, got {code}; stderr={err!r}")
        self.assertEqual(payload["results"], _reference_results(),
                         "Go and the Python reference implementation disagree — port drift")
        self.assertTrue(payload["match_expect"], "Go itself thinks it does not match expect")

    def test_go_mutant_boundary_shifts_exactly_one_point(self):
        code, payload, err = _go_results(mutant="boundary")
        self.assertEqual(code, 1, f"the wrong port should exit 1, got {code}; stderr={err!r}")
        self.assertFalse(payload["match_expect"], "the wrong port was accepted as a pass — the mutant did not take effect")
        band = payload["results"][0]
        self.assertEqual((band["common"], band["dominance"]), (7, 3),
                         f"a boundary off by one should move the common domain 8→7 and the dominance domain 2→3, got "
                         f"({band['common']}, {band['dominance']})")
        self.assertIn(12, band["dominance_witness"],
                      f"n=12 should fall from the common domain into the dominance domain, but the witness does not name it: {band['dominance_witness']}")


@unittest.skipUnless(HAS_RUSTC, "the rustc toolchain is missing: the two Rust port conclusions are invalid, not a pass")
class TestRustParity(unittest.TestCase):
    def test_rust_reads_same_as_reference(self):
        code, payload, err = _rust_results()
        self.assertEqual(code, 0, f"the Rust normal path should exit 0, got {code}; stderr={err!r}")
        self.assertEqual(payload["results"], _reference_results(),
                         "Rust and the Python reference implementation disagree — port drift")
        self.assertTrue(payload["match_expect"], "Rust itself thinks it does not match expect")

    def test_rust_mutant_boundary_shifts_exactly_one_point(self):
        code, payload, err = _rust_results(mutant="boundary")
        self.assertEqual(code, 1, f"the wrong port should exit 1, got {code}; stderr={err!r}")
        self.assertFalse(payload["match_expect"], "the wrong port was accepted as a pass — the mutant did not take effect")
        band = payload["results"][0]
        self.assertEqual((band["common"], band["dominance"]), (7, 3),
                         f"a boundary off by one should move the common domain 8→7 and the dominance domain 2→3, got "
                         f"({band['common']}, {band['dominance']})")


@unittest.skipUnless(HAS_GO and HAS_RUSTC, "both toolchains are needed to differentially compare the wrong ports")
class TestMutantAgreement(unittest.TestCase):
    def test_two_wrong_ports_agree_with_each_other(self):
        """Two languages independently wrong in the same way → the readouts must be identical.

        This is the reverse proof that "the account does not depend on the implementation":
        even the bug has its shape pinned by the spec.
        """
        _, go_payload, _ = _go_results(mutant="boundary")
        _, rust_payload, _ = _rust_results(mutant="boundary")
        self.assertEqual(go_payload["results"], rust_payload["results"],
                         "the same wrong port reads differently in Go / Rust — the drift is not in the spec")


if __name__ == "__main__":
    if not HAS_GO:
        print("  NOTE go is missing: TestGoParity / TestMutantAgreement will skip (conclusion invalid, not a pass)")
    if not HAS_RUSTC:
        print("  NOTE rustc is missing: TestRustParity / TestMutantAgreement will skip (conclusion invalid, not a pass)")
    unittest.main(verbosity=2)

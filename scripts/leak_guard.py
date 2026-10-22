# -*- coding: utf-8 -*-
"""
leak_guard — blind-run leak guard (B12 lightweight version, two rules)
====================================================================
The blind-run payload (probes/blind_run/, invisible to the skill itself) accepts the
question "can a context-free agent that reads only SKILL.md run the tool on its own".
The premise is that SKILL.md and references/ must not retain any grading-side
information, or the agent learns the grading account instead of how to use the tool.

This script statically scans SKILL.md + references/*.md with two rules:

  Rule one (test-assertion fingerprints): the test_ function names in scripts/*_test.py
      and long assert/raise message literals (≥16 characters and containing a space)
      must not appear verbatim.
      — function names are the strongest fingerprint (the P11 discipline already
      forbids SKILL prose from naming assertion functions by name); assertion messages
      are the second strongest.
  Rule two (grading keywords): the built-in word list LEAK_WORDS must not appear.
      — the list picks "the minimal characteristic words of the grading activity";
      normal SKILL/references prose does not need them. The skill being invisible to
      the blind run is the intent of the B12 constraint; if a future legitimate
      discussion needs these words, going red is a correct interception, not a false
      positive.

Exemption for legitimately shared phrases (to avoid self-harm): the CATALOG phrase
bridge in examples/test_alignment_bootstrap.py — it is the reconciliation bridge between
"SKILL commitments ↔ test assertions", so those phrases appearing in SKILL.md are the
**design** of bootstrap reconciliation rather than a leak, and the whole table is
excluded when collecting the corpus.

Known boundaries (lightweight-version declaration): verbatim match within a line, so a
long phrase broken across lines is not caught; assertion messages assembled by f-strings
are not collected at all (their static fragments look like noise on their own, and the
full message does not exist verbatim in the source); docstrings are not part of the
corpus (they are narrative, not assertions). Stronger semantic-level leak detection is
the original v3 plan and is out of scope for this version.

Usage:
    python leak_guard.py             # scan the live repository; exit 0 = clean / 1 = leaks
    python leak_guard.py --self-check  # scanner self-proof (a red sample must be red, a green sample must be green)
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Rule-two word list: the minimal characteristic words of the grading activity. The duty
# to reconcile this with the blind-run grading table by hand belongs to the grading-table
# maintainer — when changing that table's wording, check whether this list still covers
# its characteristic words.
#
# Why "blind-run task sheet" and not the glossary's settled term "blind-run brief": the
# glossary sits in references/, which is inside the scan surface, and its row defines that
# term in one line. Naming the term as a leak word would red the glossary itself — measured
# on 2026-10-22, the build went to exit 1 for exactly that line. A leak word has to be a
# phrase that only appears when someone is *describing* the harness, not a phrase the
# repository legitimately defines.
LEAK_WORDS = ("blind-run task sheet", "grading table")

# Inclusion threshold for long assertion-message literals: ordinary words shorter than
# this are too many, and scanning them yields only noise.
_MIN_LITERAL_LEN = 16

# Legitimate existing-reference exemptions (registered from B12 measurements; the
# baseline after fixing the live repository's 16 reds): SKILL.md / references citing test
# function names in existing shapes serves bootstrap reconciliation narrative ("that test
# pins that behavior/field" is legitimate document content), not a grading leak. The list
# may only shrink, never grow: a new hit is either deleted (a real leak) or registered
# with a reason (a new legitimate shape must be explicitly reviewed).
_EXEMPT_FUNCS = frozenset({
    # SKILL.md "Reconciliation between the delivery gate and the PoC" section: narrates
    # how the PoC supplies material and the test asserts the mechanism
    "test_gate_blocks_forgery_poc_move_five",
    # references/receipt-format.md receipt field contract table: each field names the test pinning it
    "test_cwd_change_is_byte_identical",
    "test_delete_receipt_and_rerun_is_byte_identical",
    "test_receipt_json_has_no_timestamp_and_no_absolute_path",
    "test_receipt_write_is_utf8_no_bom_and_readback_is_enforced",
    "test_rerun_cmd_with_absolute_path_is_refused",
    # references/writing-claims.md gate-error lookup table: error rows cite the corresponding test
    "test_divergence_does_not_block",
})

# Bridge phrase extraction: CATALOG entries' phrase="..." / phrase='...' (the fixed form
# in the bootstrap catalog)
_BRIDGE_RE = re.compile(r"""phrase=["']([^"']+)["']""")


def _read(path):
    """Read UTF-8 (no BOM) text; exceptions propagate and main handles them uniformly as
    runtime errors."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _collect_from_test_source(text, func_names, literals):
    """Extract both kinds of fingerprint from a single test file's source and merge them
    into the sets in place.

    Function names cover every def test_*; message literals cover string constants inside
    assert/raise nodes (messages assembled by f-strings are not collected at all, see
    below), and anything shorter than the threshold is skipped."""
    tree = ast.parse(text)
    # First record the ids of constant nodes inside f-strings: the static fragments of an
    # assembled message are noise on their own, and the full message does not exist
    # verbatim in the source, so collecting fragments only manufactures false
    # fingerprints.
    fstring_const_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant):
                    fstring_const_ids.add(id(sub))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            func_names.add(node.name)
        if isinstance(node, (ast.Assert, ast.Raise)):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Constant)
                        and isinstance(sub.value, str)
                        and id(sub) not in fstring_const_ids
                        and len(sub.value) >= _MIN_LITERAL_LEN
                        and " " in sub.value):
                    # Narrowing criterion: collect only natural-language phrases
                    # containing a space. Measurements (B12) show that every ≥16
                    # space-free string is a path/field name/identifier — repository-wide
                    # tokens that references legitimately describe, not leaks; the leak
                    # shape of grading content is a sentence, and sentences have spaces.
                    literals.add(sub.value)


def collect_test_fingerprints(root):
    """Corpus collection: root/scripts/*_test.py → (function-name set, long
    assertion-message literal set).

    Per the task-sheet account the corpus covers only the tests under scripts/; tests on
    the examples/ side and SKILL's legitimately shared phrases go through the bootstrap
    bridge exemption and do not widen the corpus here."""
    func_names, literals = set(), set()
    scripts_dir = os.path.join(root, "scripts")
    if not os.path.isdir(scripts_dir):
        return func_names, literals
    for name in sorted(os.listdir(scripts_dir)):
        if name.endswith("_test.py"):
            _collect_from_test_source(
                _read(os.path.join(scripts_dir, name)), func_names, literals)
    return func_names, literals


def load_catalog_phrases(root):
    """Read the bootstrap catalog's phrase bridge (the allowlist of phrases legitimately
    shared between SKILL and the tests)."""
    bridge = os.path.join(root, "examples", "test_alignment_bootstrap.py")
    if not os.path.isfile(bridge):
        return set()
    return set(_BRIDGE_RE.findall(_read(bridge)))


def scan_text(text, func_names, literals, leak_words=LEAK_WORDS):
    """Scan a piece of text with both rules; return the hit list [(kind, word), ...].

    kind: "func" test function name / "literal" assertion message / "word" grading
    keyword. Verbatim match within a line; line-crossing is not caught (a known
    lightweight-version boundary, see the module docstring)."""
    hits = []
    for kind, words in (("func", func_names), ("literal", literals),
                        ("word", leak_words)):
        for word in sorted(words):
            if word in text:
                hits.append((kind, word))
    return hits


def _iter_targets(root):
    """Scan surface: SKILL.md + references/*.md (per the task-sheet account; do not widen)."""
    skill = os.path.join(root, "SKILL.md")
    if os.path.isfile(skill):
        yield skill
    refs = os.path.join(root, "references")
    if os.path.isdir(refs):
        for name in sorted(os.listdir(refs)):
            if name.endswith(".md"):
                yield os.path.join(refs, name)


def scan_repo(root):
    """Full scan of the live repository (or any isomorphic directory); return hits
    [(file, lineno, kind, word), ...].

    The bridge exemption applies only to rule one's literals (phrase-level allowlist);
    the exempt function list is _EXEMPT_FUNCS in the module header; grading words are
    never exempt."""
    func_names, literals = collect_test_fingerprints(root)
    literals -= load_catalog_phrases(root)
    func_names -= _EXEMPT_FUNCS
    hits = []
    for path in _iter_targets(root):
        text = _read(path)
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        for kind, word in scan_text(text, func_names, literals):
            for lineno, line in enumerate(text.splitlines(), 1):
                if word in line:
                    hits.append((rel, lineno, kind, word))
    return hits


def self_check():
    """Scanner self-proof: a green sample must be green and a red sample must be red;
    only when both directions hold is the scanner alive.

    The red sample's injected words come from the current corpus (not hardcoded) — when
    the corpus is empty the proof does not hold, and it returns False so the caller goes
    red, preventing the false green of "empty corpus, silently all green"."""
    func_names, literals = collect_test_fingerprints(ROOT)
    if not func_names or not literals:
        print("[leak_guard] self-check failed: the corpus is empty (scripts/*_test.py "
              "yielded no function names/assertion messages), cannot build a red sample.", file=sys.stderr)
        return False
    green = "# Sample document\n\nNormal explanatory text with nothing sensitive.\n"
    if scan_text(green, func_names, literals):
        print("[leak_guard] self-check failed: the green sample was falsely reported; the scanner has a false red.",
              file=sys.stderr)
        return False
    sentinel_fn = sorted(func_names)[0]
    sentinel_lit = sorted(literals)[0]
    red = green + f"\nLeak sample: {sentinel_fn} and {sentinel_lit}\n"
    red_hits = scan_text(red, func_names, literals)
    kinds = {kind for kind, _ in red_hits}
    if not {"func", "literal"} <= kinds:
        print(f"[leak_guard] self-check failed: the red sample only caught {sorted(kinds)}; "
              "rule one's fingerprint extraction has a gap.", file=sys.stderr)
        return False
    if not scan_text("The body mentions the grading table and the blind-run task sheet.",
                     func_names, literals):
        print("[leak_guard] self-check failed: the grading-keyword rule two did not go red.",
              file=sys.stderr)
        return False
    return True


def main(argv=None, root=None):
    """Entry point. Exit codes: 0 = clean (or self-proof passed) / 1 = leaks found (or a
    runtime error / self-proof failure).

    root is injected explicitly: tests run a temporary repository through the full main to
    get an exit code without depending on CWD (the same discipline as receipt's "inject
    repo_root explicitly"); the default is the live repository."""
    argv = list(sys.argv[1:] if argv is None else argv)
    root = ROOT if root is None else root
    try:
        if "--self-check" in argv:
            ok = self_check()
            print("[leak_guard] self-check " + ("passed" if ok else "failed"))
            return 0 if ok else 1
        hits = scan_repo(root)
        if hits:
            lines = [f"[leak_guard] found {len(hits)} leaks"
                     " (grading-side information in SKILL.md / references):"]
            lines += [f"    · {f}:{ln} [{kind}] {word[:60]}"
                      for f, ln, kind, word in hits]
            lines += ["", "  The blind-run payload is invisible to the skill itself — delete that content, "
                          "or confirm it really belongs in SKILL prose (that would be a leak-surface breach)."]
            print("\n".join(lines), file=sys.stderr)
            return 1
        print("[leak_guard] SKILL.md + references/*.md are clean: "
              "no test-assertion fingerprints, no grading keywords.")
        return 0
    except Exception as exc:  # runtime errors fold into exit code 1 per the task-sheet account; the message goes to
        # stderr in the same direction as real leaks (FATAL-class is immediately visible),
        # separate from stdout's green message
        print(f"[leak_guard] runtime error (not a leak red): {exc!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

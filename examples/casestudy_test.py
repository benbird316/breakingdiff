# -*- coding: utf-8 -*-
"""
casestudy instance gate — four existence checks + count anchors + hubble pure-script assertion
==============================================================================
The assertion surface under casestudy/ used to sit outside every gate's surface
under test: delete a file, cut tests in bulk, and the regression suite quietly let
it pass. This file pins it into the surface under test (a static gate: it does not
run the cases themselves, does not read the corpus, finishes in seconds). It pins
three things:

  1. Four existence checks: the four files that carry assertions are each checked;
     a missing one raises CoverageError directly (reusing scripts/coverage_guard.py,
     not redefining it locally) — a missing file is reported as missing, because
     both warnings and silent skips would read "file deleted" as "pass".
  2. Count anchors: the pdg and llama test counts are counted statically with a
     line-start-anchored regex; expected values are explicitly named constants, and
     the error text carries "got N / expected M". The count is a lower-bound defense
     against whole-file deletion and bulk shrinkage; anchoring at line start is not
     pedantry — an unanchored count also counts `def` text inside comments (measured
     +8 in the main repo).
  3. hubble pure script: case_study.py must not contain `def test_` (substring test,
     the strictest reading). "It is a pure script" is pinned as an assertion —
     otherwise someone adds an assertion later with nobody counting it, and hubble
     becomes the next directory with an empty domain.
  4. Catalog reconciliation: every .md/.py content file under casestudy/ must be
     mentioned literally by at least one declaration surface (repo-root README
     directory tree / INDEX.md / casestudy/README.md). The three items above guard
     "the file was not deleted"; this one guards "the file was not forgotten" —
     delete TEACHING-pdg.md or drop all of casestudy/ from the directory tree and
     the three above stay green while readers cannot find the entry point in the
     canonical text (three such spots were measured on 2026-10-18, all silent).

Perception boundary: only casestudy/ relative to the repository root is examined
(the path is derived from this file's location, independent of the working
directory); copies inside the repo and same-named files under examples/ are out of
scope, and no whole-repo traversal happens. No special-case bypass branches —
a branch that cannot be triggered by a counterexample does not stay.

Usage: python casestudy_test.py
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
from coverage_guard import CoverageError

ROOT = os.path.dirname(HERE)

# Existence targets: always end in a .py filename, judged by isfile — if a directory
# counted, a path mistyped as the parent directory would only produce a false green
# and a file-level absence would never be caught.
PDG_TESTS = os.path.join(ROOT, 'casestudy', 'pdg', 'test_aligned.py')
LLAMA_TESTS = os.path.join(ROOT, 'casestudy', 'llama', 'test_aligned.py')
PORT_TESTS = os.path.join(ROOT, 'casestudy', 'port', 'test_port.py')
MALECNS_TESTS = os.path.join(ROOT, 'casestudy', 'malecns', 'test_aligned.py')
# The only case in the programming domain, and the only one whose main account is a
# gate refusal. Registered here for the same reason as the other four: an unregistered
# case is level-3 silence — the four-quadrant table would read it as "nothing there".
K8S_TESTS = os.path.join(ROOT, 'casestudy', 'k8s', 'test_aligned.py')
HUBBLE_CASE = os.path.join(ROOT, 'casestudy', 'hubble', 'case_study.py')

# The one counting convention for the whole file: anchor at line start (re.M).
# Indented `def` inside a class is caught by ^\s*; `def` text in a comment does not
# match because the line starts with #. The convention is written once; both sides
# of the ledger use it.
TEST_DEF_RE = re.compile(r'^\s*def\s+test_', re.M)

# Expected constants: named, grep-able, auditable — the count-anchor numbers must not
# scatter into bare literals; when instance assertions change, change these and leave
# a trace in CHANGELOG, never edit the error text in place.
EXPECTED_PDG_TESTS = 34
EXPECTED_LLAMA_TESTS = 45
EXPECTED_PORT_TESTS = 12
EXPECTED_MALECNS_TESTS = 24
EXPECTED_K8S_TESTS = 33


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _require_file(path):
    """Raise CoverageError when the file is absent; the error names the repo-relative
    path.

    Raise instead of printing a warning: silence must carry a non-zero cost, or
    deleting a file gets read as "the gate passes" — the same discipline
    coverage_guard applies to a zero readout.
    """
    if not os.path.isfile(path):
        raise CoverageError(
            f"casestudy assertion file missing: {os.path.relpath(path, ROOT)}")


def _count_tests(path):
    """Line-start-anchored static count: guards against deletion and shrinkage, not
    against "keep the def skeleton, gut the test body" — that is the behavior-level
    defense line's job; this gate does not claim to do it."""
    _require_file(path)
    return len(TEST_DEF_RE.findall(_read(path)))


def _require_count(path, expected):
    """Red when the count drifts from the expectation; the text carries "got N /
    expected M" — without both numbers the drift cannot be located. Equality, not a
    lower bound: an increase is red too, and the change must be booked together with
    the expected constant."""
    got = _count_tests(path)
    if got != expected:
        raise CoverageError(
            f"casestudy count drift: {os.path.relpath(path, ROOT)} "
            f"got {got} / expected {expected} (line-start-anchored convention) — "
            f"assertion changes must update the expected constant and CHANGELOG together")


# ---- Catalog reconciliation (item four) -----------------------------------
# Three declaration surfaces: where readers look when "finding a file". The repo-root
# README directory tree, INDEX.md's per-file navigation, and casestudy/README.md's own
# entry point.
CATALOG_FACES = (
    'README.md',
    'INDEX.md',
    os.path.join('casestudy', 'README.md'),
)
CATALOG_EXTS = ('.md', '.py')
CATALOG_SKIP_DIRS = {'__pycache__', '_grader_local'}
# Word boundary: the name must occur as a whole. A substring convention would count
# aligned.py inside test_aligned.py as "mentioned" (aligned is preceded by an
# underscore, an identifier character), and would also count misaligned.py as
# aligned.py — the same trap was hit once in the exemption mechanism
# (references/writing-claims.md, "substring matching was once taken for an exemption
# mechanism").
_NAME_BOUNDARY = lambda name: (
    r'(?<![\w])' + re.escape(name) + r'(?![\w])')


def _iter_casestudy_files(casestudy_root, root):
    """Walk the surface under test: .md/.py content files, excluding caches and local
    grading material. Yields POSIX paths relative to root, consistent across
    platforms (Windows backslashes would break cross-surface reconciliation)."""
    for dirpath, dirnames, filenames in os.walk(casestudy_root):
        dirnames[:] = [d for d in dirnames if d not in CATALOG_SKIP_DIRS]
        for name in sorted(filenames):
            if name.endswith(CATALOG_EXTS):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                yield rel.replace(os.sep, '/')


def check_catalog(casestudy_root, faces, root=None):
    """Return the content files not mentioned by any declaration surface (POSIX
    relative paths, sorted).

    The criterion uses the basename, not the full path: the run section says
    `python aligned.py` (after `cd pdg`), so the full path `pdg/aligned.py` never
    appears literally; judging by path would misreport an already-mentioned file as
    a gap — a gate that is too tight is as harmful as one that is too loose.

    Same-name cost adds a count guard against "only one is mentioned": mentions of a
    duplicated basename must be ≥ the number of directories holding that basename.
    aligned.py exists in both pdg/ and llama/; mentioning it once is a gap (a reader
    following the docs to the other side finds nothing).

    faces is injectable (for mutation evidence): {declaration-surface relative path:
    full text}.
    """
    root = root if root is not None else ROOT
    files = sorted(_iter_casestudy_files(casestudy_root, root))
    blob = "\n".join(faces.values())
    by_name = {}
    for rel in files:
        by_name.setdefault(os.path.basename(rel), []).append(rel)

    gaps = []
    for name, rels in sorted(by_name.items()):
        hits = len(re.findall(_NAME_BOUNDARY(name), blob))
        if hits == 0 or hits < len(rels):
            gaps.extend(rels)
    return sorted(gaps)


def _require_catalog(casestudy_root):
    """Catalog reconciliation entry point: a non-empty gap set is a CoverageError,
    naming each file and pointing at the declaration surfaces to amend. Raise rather
    than warn — an omission means readers cannot find the entry point, and "cannot
    find" never shows up as a failure on its own."""
    faces = {}
    for rel in CATALOG_FACES:
        path = os.path.join(ROOT, rel)
        _require_file(path)   # if a declaration surface itself is deleted, reconciliation would silently pass (zero readout)
        faces[rel] = _read(path)
    files = sorted(_iter_casestudy_files(casestudy_root, ROOT))
    gaps = check_catalog(casestudy_root, faces)
    if gaps:
        raise CoverageError(
            "casestudy catalog omissions (readers cannot find these entry points in the canonical text): "
            + ", ".join(gaps)
            + " — add a literal mention in at least one declaration surface: "
            + " / ".join(CATALOG_FACES))
    return files


def main():
    # ---- Four existence checks first: a missing file is instantly red, and count
    # items are not evaluated while it is missing — a missing check counts as neither
    # red nor green, only "not run"; after restoring it, every item must go green again.
    for path in (PDG_TESTS, LLAMA_TESTS, PORT_TESTS, MALECNS_TESTS, K8S_TESTS, HUBBLE_CASE):
        _require_file(path)
        print(f"  PASS existence  {os.path.relpath(path, ROOT)}")

    # ---- Count anchors: pdg / llama / port / malecns / k8s
    _require_count(PDG_TESTS, EXPECTED_PDG_TESTS)
    print(f"  PASS count  {os.path.relpath(PDG_TESTS, ROOT)} = {EXPECTED_PDG_TESTS}")
    _require_count(LLAMA_TESTS, EXPECTED_LLAMA_TESTS)
    print(f"  PASS count  {os.path.relpath(LLAMA_TESTS, ROOT)} = {EXPECTED_LLAMA_TESTS}")
    _require_count(PORT_TESTS, EXPECTED_PORT_TESTS)
    print(f"  PASS count  {os.path.relpath(PORT_TESTS, ROOT)} = {EXPECTED_PORT_TESTS}")
    _require_count(MALECNS_TESTS, EXPECTED_MALECNS_TESTS)
    print(f"  PASS count  {os.path.relpath(MALECNS_TESTS, ROOT)} = {EXPECTED_MALECNS_TESTS}")
    _require_count(K8S_TESTS, EXPECTED_K8S_TESTS)
    print(f"  PASS count  {os.path.relpath(K8S_TESTS, ROOT)} = {EXPECTED_K8S_TESTS}")

    # ---- hubble pure script: the file was already checked under existence; here only
    # the "contains no `def test_`" half is pinned. The substring test is the
    # strictest reading: any occurrence anywhere in the file counts — once there is an
    # assertion it must enter the counting convention, not hang outside the ledger.
    if 'def test_' in _read(HUBBLE_CASE):
        raise CoverageError(
            f"hubble pure script broken: {os.path.relpath(HUBBLE_CASE, ROOT)} "
            f"contains `def test_` — new assertions must enter the counting convention, not stay out of domain")

    # ---- Catalog reconciliation: content files must be mentioned by at least one
    # declaration surface. Division of labor with the three items above: those guard
    # "not deleted", this one guards "not forgotten".
    catalog_files = _require_catalog(os.path.join(ROOT, 'casestudy'))
    print(f"  PASS catalog  {len(catalog_files)} content files all mentioned by >=1 declaration surface")

    print(f"casestudy gate all green: existence 6, counts 5, pure-script assertion 1, "
          f"catalog {len(catalog_files)}")
    return 0


if __name__ == '__main__':
    # --mutation runs only the mutation evidence, not the main gate — the two have
    # different concerns: the main gate answers "is the current tree green", mutation
    # evidence answers "does this gate have discriminating power". Mixed into one run,
    # a red tree makes it impossible to tell which layer the red came from.
    if '--mutation' in sys.argv:
        run_mutation_checks()
        raise SystemExit(0)
    raise SystemExit(main())


# ---- Mutation evidence (references/writing-claims.md, step six) ----------------------
# Both hard disciplines for the catalog-reconciliation gate were measured in this
# project, and each is honored here:
#   ① the red must come from the "not mentioned" defense line, not from another check
#      that happened to fire — hence asserting the characteristic substring of the
#      error message, not merely "it raised".
#   ② the mutation must be confirmed to take effect first: N=0 means it did not, and
#      "not caught" then is not evidence.
# Both directions: too loose (omission passes) and too tight (a mentioned file is
# blocked) are tested — the latter would block what should pass, and a gate used
# twice gets bypassed.

def _mk_tree(root):
    """Build a miniature casestudy tree: pdg/ and llama/ each hold a same-named
    aligned.py (the duplicate-name scenario, verifying the count guard against "only
    one mentioned") + pdg/ holds one teaching document."""
    for sub in ('pdg', 'llama'):
        d = os.path.join(root, 'casestudy', sub)
        os.makedirs(d)
        with open(os.path.join(d, 'aligned.py'), 'w', encoding='utf-8') as f:
            f.write('# stub\n')
    d = os.path.join(root, 'casestudy', 'pdg')
    with open(os.path.join(d, 'TEACHING-pdg.md'), 'w', encoding='utf-8') as f:
        f.write('# stub\n')
    return root


def _mk_faces():
    """Three declaration surfaces: aligned.py mentioned twice (once for pdg/, once for
    llama/), TEACHING-pdg.md mentioned once."""
    return {
        'README.md': 'pdg/aligned.py\n',
        'INDEX.md': 'llama/aligned.py\n',
        os.path.join('casestudy', 'README.md'): 'TEACHING-pdg.md\n',
    }


def run_mutation_checks():
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp(prefix='casestudy-catalog-mut-')
    try:
        root = _mk_tree(os.path.join(tmp, 'repo'))
        cs = os.path.join(root, 'casestudy')

        # Baseline: all mentioned → zero gaps (prove the fixture itself is green first,
        # otherwise the later "red" cannot be told apart from a fixture that was red to
        # begin with)
        assert check_catalog(cs, _mk_faces(), root=root) == [], \
            "fixture baseline should have zero gaps"

        # ---- mutation 1: too loose — remove TEACHING from every declaration surface ----
        # Confirm the mutation first: the name must no longer appear anywhere, N=0 means
        # it did not take effect
        stripped = {k: v.replace('TEACHING-pdg.md', 'REDACTED')
                    for k, v in _mk_faces().items()}
        assert 'TEACHING-pdg.md' not in '\n'.join(stripped.values()), \
            "mutation did not take effect: the name is still present"
        gaps = check_catalog(cs, stripped, root=root)
        # It must be this defense line that blocks: the gap is exactly that file, and only it
        assert gaps == ['casestudy/pdg/TEACHING-pdg.md'], \
            f"too-loose direction: expected only TEACHING-pdg.md, got {gaps}"

        # ---- mutation 2: too loose, duplicate-name count — aligned.py mentioned once ----
        # pdg/ and llama/ each have an aligned.py; mentioning it once means a reader
        # following the docs to the other side finds nothing. This one specifically
        # guards "mention one and count it as two"
        once = {k: v.replace('llama/aligned.py', 'REDACTED')
                for k, v in _mk_faces().items()}
        assert once['INDEX.md'].count('aligned.py') == 0, \
            "mutation did not take effect: INDEX.md still contains aligned.py"
        gaps2 = check_catalog(cs, once, root=root)
        assert sorted(gaps2) == ['casestudy/llama/aligned.py',
                                 'casestudy/pdg/aligned.py'], \
            f"duplicate-name count direction: both sides should be reported, got {gaps2}"

        # ---- mutation 3: too tight — every file mentioned once must pass ----
        # Blocking what should pass = gate noise; after two uses it gets switched off
        assert check_catalog(cs, _mk_faces(), root=root) == [], \
            "too-tight direction: all mentioned yet gaps were reported"

        # ---- mutation 4: word boundary — a substring must not count as a mention ----
        # test_aligned.py / misaligned.py contain the aligned.py substring; a substring
        # convention would count them as "mentioned" — here we explicitly pin that
        # substrings do not count
        tricky = dict(_mk_faces())
        tricky['INDEX.md'] = 'see test_aligned.py and misaligned.py\n'
        blob_hits = len(re.findall(_NAME_BOUNDARY('aligned.py'),
                                   '\n'.join(tricky.values())))
        assert blob_hits == 1, \
            f"word boundary lost: a substring counted as a mention, hits={blob_hits} (should be 1)"

        print("  mutation evidence 4/4: too loose x2 (including duplicate-name count) / too tight / word boundary, all red or pass as expected")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

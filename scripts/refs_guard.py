# -*- coding: utf-8 -*-
"""
refs_guard — a static reference-integrity gate between SKILL.md and references/
================================================================================
Nothing at runtime guards the pointer relations between SKILL.md and
references/: an article gets renamed, a link breaks, one of them is deleted
silently, and the differential engine is completely blind to it — it only reads
claims, not documents. Every one of these failure modes "looks normal"; they
are the three-level silence at the document layer.

This module runs static checks at the document layer and turns a dead link into
a non-zero cost. The 14 checks are independent functions (the red condition is
in each function's docstring). The CLI live-repo mode runs all 13 in one pass,
and the key set (including AGENTS.md's two, M-N3/M-N4) is frozen key by key by
the tests, so the default check surface does not drift.

Usage:
    assertion library: from refs_guard import assert_no_dead_links, ...
             The text arguments (skill_text / agents_text) can be injected;
             when injected the injected value wins, and the corresponding file
             may be absent from disk.
    live repo:  python refs_guard.py            # 13 checks, prints every SKIP
    change gate: python refs_guard.py --check-commit   # changing SKILL.md requires changing CHANGELOG.md

Exit codes, three tiers (following the receipt.py convention):
    0  all green
    1  something red (RefsError, gate semantics)
    2  runtime error (cannot read a file, an injected check blew up — not
       having run is not the same as having run)

Design points:
  1. Every red is a RefsError; the text starts with [refs_guard], names the
     specific file, and where a line can be located carries
     "relative/path:line" (forward slashes, so grep still finds it on another
     machine).
  2. SKIP has exactly one legal condition: the target file does not exist yet
     (e.g. the hooks contract before B5 lands). Record it in SKIP_LOG (target
     name + reason) and print it — silence is forbidden; a known red in the
     live repo must not hide behind SKIP.
  3. warn exists in exactly one place: AGENTS.md line count outside the
     reference band. Recorded in WARN_LOG, never raises; the line count is a
     health metric, not a gate clause.
  4. SKIP_LOG / WARN_LOG are module-level lists, cleared when run_checks
     enters — each report contains only this run's records; mixing runs cannot
     be reconciled.
"""
import os
import re
import subprocess
import sys

EXIT_PASS = 0
EXIT_GATE_FAIL = 1
EXIT_RUNTIME_ERROR = 2


class RefsError(ValueError):
    """Reference integrity is broken. Gate semantics → exit code 1."""


# ── module-level logs: the only queryable record of SKIP and warn ─────────────
# Global lists rather than return values: return values are easily ignored by
# callers, logs are not.
SKIP_LOG = []
WARN_LOG = []

# Instruction-pattern corpus for the navigation table (M-N1). Navigation is a
# pure "item → location" map; verb-style instructions belong in SKILL.md or
# ORCHESTRATION.md and must not settle here. The corpus is content: it started
# with the two samples the plan names, and extending it is just adding entries —
# think before adding one, so legitimate explanatory prose is not hit as
# collateral red. Matching lowercases both sides: English sentence case varies,
# and a case-sensitive corpus would only fire on one spelling.
INSTRUCTION_PATTERNS = ("Do not change P", "Must write red first")

# The TOC line criterion counts non-blank lines: blank lines are layout, not
# content. The 2026-10-16 live-repo ledger (writing-claims 161 lines, the rest
# ≤81) was recorded on that account; a physical-line account would report 3
# extra reds outside the ledger. NAV_LINE_BAND is the opposite — it pins
# physical lines, because the line-count fixture contains blank lines and the
# test asserts on physical lines. Each criterion keeps its own evidence anchor;
# do not force them into one.
TOC_THRESHOLD = 100          # a table of contents is required above this many non-blank lines
TOC_TOP_LINES = 10           # tolerance for "top": a TOC within the first 10 lines counts
NAV_LINE_BAND = (40, 120)    # AGENTS.md line-count reference band (closed, physical lines); outside → warn only

# What counts as a "path" inside a table cell: ends with a common file suffix,
# or contains a path separator.
_CELL_PATH_RE = re.compile(
    r"^[\w./\\ -]+\.(py|md|txt|json|toml|cfg|ini|sh|ps1|bat)$|^[\w.-]+/[\w./\\ -]+$")
_REF_LINK_RE = re.compile(r"references/[\w.-]+\.md")


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _ref_files(root):
    """The sorted list of .md files under references/. A missing directory is
    treated as an empty set — the gate is about reference relations, not the
    directory itself."""
    rd = os.path.join(root, "references")
    if not os.path.isdir(rd):
        return []
    return sorted(f for f in os.listdir(rd) if f.endswith(".md"))


def _read_ref(root, fname):
    return _read_text(os.path.join(root, "references", fname))


def _refs_union_text(root):
    """The union text of SKILL.md ∪ references, for criteria that check
    verbatim presence."""
    parts = [_read_text(os.path.join(root, "SKILL.md"))]
    parts += [_read_ref(root, f) for f in _ref_files(root)]
    return "\n".join(parts)


def _nonblank_lines(text):
    return [ln for ln in text.splitlines() if ln.strip()]


def _fail(lines):
    raise RefsError("\n".join(lines))


# ── 1. dead links: every references article SKILL.md points at must exist ────
def assert_no_dead_links(root, skill_text=None):
    """Every references/X.md reference in SKILL.md must exist as a real file.
    Red condition: a dead link. The text carries SKILL.md:line and the missing
    file name."""
    if skill_text is None:
        skill_text = _read_text(os.path.join(root, "SKILL.md"))
    dead = []
    for lineno, line in enumerate(skill_text.splitlines(), 1):
        for m in _REF_LINK_RE.finditer(line):
            target = os.path.join(root, m.group(0).replace("/", os.sep))
            if not os.path.isfile(target):
                dead.append((lineno, m.group(0)))
    if dead:
        lines = [f"[refs_guard] SKILL.md has {len(dead)} pointer(s) to files that do not exist:"]
        lines += [f"    · SKILL.md:{ln} → {t}" for ln, t in dead]
        lines += ["",
                  "  A broken pointer is worse than no pointer: the reader follows it into empty space.",
                  "  Fix: add the missing file, or point the pointer at an article that exists."]
        _fail(lines)


# ── 2. orphans: every references article must be pointed at from SKILL.md ────
def assert_no_orphans(root, skill_text=None):
    """Every references/*.md must be named directly in SKILL.md in the form
    references/X.md (the same regular expression as assert_no_dead_links defines
    "reference").
    Red condition: an orphan (written out but nobody points the way — the reader
    can never reach it)."""
    if skill_text is None:
        skill_text = _read_text(os.path.join(root, "SKILL.md"))
    linked = {m.group(0) for m in _REF_LINK_RE.finditer(skill_text)}
    orphans = [f for f in _ref_files(root)
               if f"references/{f}" not in linked]
    if orphans:
        lines = [f"[refs_guard] references/ has {len(orphans)} orphan(s): SKILL.md does not reference them directly."]
        lines += [f"    · references/{f}" for f in orphans]
        lines += ["",
                  "  An article you cannot reach from SKILL.md does not exist, and it still costs audit effort.",
                  "  Fix: add a pointer, or delete the article — do not leave it hanging."]
        _fail(lines)


# ── 3. cross-links: references must not link to each other (M-D6, one level) ─
def assert_no_reference_cross_links(root):
    """No references/Y.md link may appear in the body of references/*.md
    (pointing at itself is allowed). Red condition: a cross-link; the text
    carries file:line.
    One level deep: only explicit links in the references bodies are scanned;
    a second level is not followed."""
    bad = []
    for fname in _ref_files(root):
        for lineno, line in enumerate(_read_ref(root, fname).splitlines(), 1):
            for m in _REF_LINK_RE.finditer(line):
                if m.group(0) != f"references/{fname}":
                    bad.append((fname, lineno, m.group(0)))
    if bad:
        lines = ["[refs_guard] references/ contain cross-links (forbidden at one level deep):"]
        lines += [f"    · references/{f}:{ln} → {t}" for f, ln, t in bad]
        lines += ["",
                  "  A mesh of links between articles bypasses SKILL.md's navigation, and edits break it silently.",
                  "  Fix: lift the cross-referenced content into SKILL.md, or describe it in prose instead of a link."]
        _fail(lines)


# ── 4. long articles must have a table of contents (M-D7) ────────────────────
def assert_toc_required(root):
    """references/*.md with more non-blank lines than TOC_THRESHOLD must have a
    table-of-contents section at the top.

    The heading accepts `## Contents` and `## TOC`; a verbatim occurrence within
    the first TOC_TOP_LINES lines counts as the top. The Chinese heading was
    accepted during the i18n transition and is gone now that every article is
    English; keeping it would also leave a non-ASCII literal in this module.
    Red condition: long but no TOC. The criterion account is in the
    TOC_THRESHOLD comment."""
    toc_headings = ("## Contents", "## TOC")
    bad = []
    for fname in _ref_files(root):
        body = _nonblank_lines(_read_ref(root, fname))
        if len(body) <= TOC_THRESHOLD:
            continue
        top = body[:TOC_TOP_LINES]
        if not any(any(h in ln for h in toc_headings) for ln in top):
            bad.append((fname, len(body)))
    if bad:
        lines = [f"[refs_guard] {len(bad)} long article(s) (non-blank lines >{TOC_THRESHOLD}) have no \"## Contents\" at the top:"]
        lines += [f"    · references/{f} (non-blank lines {n})" for f, n in bad]
        lines += ["",
                  "  Without a table of contents the reader has to scroll the whole article to find a section.",
                  "  Fix: add a \"## Contents\" section at the top, or split the article shorter."]
        _fail(lines)


# ── 5. host variables: references must not contain ${CLAUDE_ (M-D5) ──────────
def assert_no_host_vars_in_references(root):
    """references/*.md must not contain host variables with the ${CLAUDE_
    prefix. Red condition: a hit; the text carries file:line. The scan surface
    is pinned to references/ — host variables in the SKILL.md body are legal,
    and scanning beyond would drag legal files into a false red."""
    bad = []
    for fname in _ref_files(root):
        for lineno, line in enumerate(_read_ref(root, fname).splitlines(), 1):
            if "${CLAUDE_" in line:
                bad.append((fname, lineno))
    if bad:
        lines = [f"[refs_guard] references/ contain host variables ${{CLAUDE_ ({len(bad)} place(s)):"]
        lines += [f"    · references/{f}:{ln}" for f, ln in bad]
        lines += ["",
                  "  references is the cross-host method layer; hard-coding a host variable ties it to one host.",
                  "  Fix: move host-specific snippets back into SKILL.md and describe them in prose in references."]
        _fail(lines)


# ── 6. pointer form: three parts (M-P3) ──────────────────────────────────────
def assert_pointer_form(root, skill_text=None):
    """Every line in SKILL.md that contains a references/ pointer must hold at
    least 2 "→" (trigger condition → which section to read → what it solves).
    Red condition: one arrow or none; the text carries the line number.
    Trade-off: only the lower bound ≥2 is judged, with no ceiling — the essence
    of the three-part form is that all three parts are there, and one extra
    pointer in the flow does not break it; pinning a ceiling would hit legal
    dense pointers as red."""
    if skill_text is None:
        skill_text = _read_text(os.path.join(root, "SKILL.md"))
    bad = []
    for lineno, line in enumerate(skill_text.splitlines(), 1):
        m = _REF_LINK_RE.search(line)
        if not m:
            continue
        arrows = line.count("→")
        if arrows < 2:
            bad.append((lineno, m.group(0), arrows))
    if bad:
        lines = [f"[refs_guard] SKILL.md has {len(bad)} pointer(s) that are not three-part (fewer than 2 → on the line):"]
        lines += [f"    · SKILL.md:{ln} → {t} ({n} → actually present)" for ln, t, n in bad]
        lines += ["",
                  "  Three-part = trigger condition → which section to read → what it solves; a two-part pointer cannot say why to read it.",
                  "  Fix: supply both the trigger condition and the purpose segment."]
        _fail(lines)


# ── 7. pointer promises: what each pointer promises must be present in the
#       target file (B11) ─────────────────────────────────────────────────────
def _pointer_segments(line):
    """Split a pointer line on → into [(start, end, text)]. A → inside
    parentheses is prose, not a segment boundary (e.g. "(red-first baseline →
    regression_lock)"); count parenthesis depth before splitting.
    Segment 0 = trigger condition, the segment holding the file = which section
    to read, the segments after it = what it solves."""
    segs, start, depth = [], 0, 0
    for i, ch in enumerate(line):
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        elif ch == "→" and depth == 0:
            segs.append((start, i, line[start:i]))
            start = i + 1
    segs.append((start, len(line), line[start:]))
    return segs


# Content-word splitting: non-word characters (\W happens to cover all
# full-width punctuation) and the Chinese structural particles are split away;
# the Chinese conjunction for "and" is not split — a coordinate promise such as
# "install snippet and the Windows powershell wrapper" stays one phrase, which
# keeps a back-reference like "use the install snippet from the previous
# section" from substring-matching an already-deleted passage back to life. A
# trailing section-word suffix is stripped: promising "the reconciliation
# section" means the reconciliation content is present, not the section title
# verbatim (the minimal allowance for word-form variation; wider starts
# swallowing real promises).
# The two Chinese structural particles (U+7684 "of", U+4E86 perfective) are
# written as \u escapes: the Chinese tokenizing path is frozen behavior and must
# keep matching them, while this module stays free of non-ASCII literals.
_PROMISE_SPLIT_RE = re.compile(r"[\W_]+|[\u7684\u4e86]")

# Stopwords for English pointers: \W splits English into words correctly, but
# function words like the/of/to would turn "every promise word is absent" into
# "any single function word counts as delivery". Only words that carry no
# information are filtered, and there is no stemming (stemming would introduce a
# second semantics). Phase 3 extended the list once the pointer corpus was
# English: live pointers leaked pronouns and pure function words ("you", "what",
# "per", "via"), and since SKILL.md is written in the second person, an
# incidental "you" in any body could fulfill a promise about something else
# entirely. The action word "read" is filtered for the same reason — it would
# otherwise carry a whole promise by itself. Every live promise still reconciles
# after the extension.
_EN_PROMISE_STOPWORDS = frozenset("""
the a an of to in on for with and or by as at is are was were be been being
this that these those it its from into than then so such not no only also all
any each every which who whom whose when where why how do does did can could
may might must should will would read reads reading see also above below
you your yours we our ours us they them their theirs there here what
per via about over under between before after while because but if else
very more most some own just even still yet again once
""".split())


def _promise_tokens(text):
    """Promise text → list of content-word tokens: the file reference itself is
    not a promise, so strip it first.

    i18n: there are two tokenizing paths, Chinese and English. Chinese keeps
    the original account (>=2 chars, strip a trailing section-word suffix);
    English lowercases after splitting on \\W, keeps >=3 characters, and filters
    stopwords — English has no morphological boundary between content and
    function words, so a stopword list is the only workable approximation.
    """
    text = _REF_LINK_RE.sub(" ", text)
    out = []
    for part in _PROMISE_SPLIT_RE.split(text):
        part = part.strip()
        if not part:
            continue
        if part.isascii():
            word = part.lower()
            if len(word) >= 3 and word not in _EN_PROMISE_STOPWORDS and not word.isdigit():
                out.append(word)
            continue
        # U+8282 is the Chinese section-word suffix stripped above.
        if len(part) >= 3 and part.endswith("\u8282"):
            part = part[:-1]
        if len(part) >= 2:
            out.append(part)
    return out


# Head title lines: H1/H2 (starting with "# " or "## "). H3 and below are out of
# scope — they never appear at the head of a file as self-introduction.
_HEAD_TITLE_RE = re.compile(r"#{1,2}\s")


def _body_minus_head_titles(doc):
    """Strip the H1/H2 title lines at the head of the file: from the first
    non-blank line up to the first paragraph of body, every consecutive title
    line (blank lines in between still count as the head) is stripped. A title
    is the file's self-introduction; pointing at it hits by nature, and using
    titles to fulfill promises is not reconciliation at all (review
    counter-example: hooks topic → read hooks.md stayed green after the body was
    emptied down to the title). Once the body starts, the H2s after it are
    section structure and are counted in the hit text as usual."""
    kept, in_head = [], True
    for ln in doc.splitlines():
        if in_head:
            if not ln.strip():
                kept.append(ln)
                continue
            if _HEAD_TITLE_RE.match(ln.strip()):
                continue
            in_head = False
        kept.append(ln)
    return "\n".join(kept)


def _own_trigger_clause(between):
    """The trigger segment of the 2nd+ pointer on a line that holds several
    pointers: from the raw text between this pointer and the previous one, drop
    in three steps the tail that does not belong to the trigger segment — after
    the last top-level → comes the start of the file segment ("read "), drop it
    first; then drop the previous pointer's file-segment tail (its file name up
    to the previous top-level →); finally drop the previous pointer's motive
    segment (before the ";"). The chained writing convention looks like "read
    the reconciliation section of a.md → stops drift; change the differential
    core → read the section of b.md". When every separator is absent the whole
    remaining text becomes the trigger segment — words leaking in from the
    previous pointer only widen the matching direction and never lose the new
    trigger segment. Both the ASCII and the full-width semicolon separate
    pointers: English prose writes ";", and the separator set is part of the
    bilingual i18n handling, not a frozen identifier."""
    return (between.rsplit("→", 1)[0]
            .rsplit("→", 1)[-1]
            .rsplit("；", 1)[-1]
            .rsplit(";", 1)[-1])


def assert_pointer_promises(root, skill_text=None):
    """Every references pointer in SKILL.md must promise what it points at: the
    content-word phrases in the trigger segment and the file segment are the
    delivery list the pointer hands out, reconciled forward — against the body
    of the target file.
    Locating power and ceiling, stated honestly: this check is a low-threshold
    sentinel. It catches a pointer that hangs in the air as a whole (every
    promise word is absent, so the promise cannot be reconciled); it does not
    promise verbatim guardianship — a promise whose content drifted while some
    word still occurs is outside its scope, and the B12 cold-start blind run
    covers that.
    Two sources are excluded from a hit (B11 hardening):
      1) a promise word equal to the target file's own name does not count —
         in "hooks topic → read hooks.md" the word hooks hits only the file
         name, not the content;
      2) the H1/H2 title lines at the head of the target file are not part of
         the hit text (see _body_minus_head_titles) — a title is self-
         introduction, and pointing at it hits by nature.
    Two classes of red condition, both worded as reconciliation and each
    reported by its own trigger segment:
      a) every promise word is absent after exclusion → "pointer promises X,
         but xxx.md does not deliver";
      b) no content word can be extracted after exclusion → the promise cannot
         be reconciled, equally red (the three-part form only guarantees that
         arrows exist; this one guarantees that the words the arrows point at
         are checkable).
    A line with several pointers (chained "read the section of a.md → stops
    drift; change the differential core → read the section of b.md"): the
    trigger segment of the 2nd+ pointer is extracted independently (see the
    three-step tail drop in _own_trigger_clause) instead of mistakenly reusing
    the line-start segment; several references inside one segment ("read a.md
    and b.md") share that one trigger segment.
    The target file not existing → not checked here (that is no_dead_links'
    territory; reporting twice would dress one dead link as two diseases); it
    does not go into SKIP_LOG either — a file on disk is always decidable, and
    this check has no suspended state.
    The "what it solves" segments (those after the file segment) are off limits
    for reconciliation: that is the motive for reading it, not a promise about
    the file content ("stops an all-green test run being read as a pass" need
    not appear verbatim in the file), and reconciling motives would judge every
    pointer as broken.
    """
    if skill_text is None:
        skill_text = _read_text(os.path.join(root, "SKILL.md"))
    unfulfilled, wordless = [], []
    for lineno, line in enumerate(skill_text.splitlines(), 1):
        matches = list(_REF_LINK_RE.finditer(line))
        if not matches:
            continue
        segs = _pointer_segments(line)
        prev_end = prev_idx = None
        prev_trigger = ""
        for m in matches:
            path = os.path.join(root, m.group(0).replace("/", os.sep))
            idx = next(i for i, (s, e, _t) in enumerate(segs)
                       if s <= m.start() < e)
            if prev_end is None:
                trigger = segs[0][2]              # line-start pointer: segment 0 is the trigger
            elif idx == prev_idx:
                trigger = prev_trigger            # several references in one segment share the trigger
            else:
                trigger = _own_trigger_clause(line[prev_end:m.start()])
            if os.path.isfile(path):              # dead links belong to assert_no_dead_links
                tokens = _promise_tokens(trigger + " " + segs[idx][2])
                stem = os.path.splitext(os.path.basename(path))[0]
                checkable = [t for t in tokens if t.lower() != stem.lower()]
                if not checkable:
                    wordless.append((lineno, m.group(0)))
                else:
                    with open(path, encoding="utf-8") as f:
                        doc = _body_minus_head_titles(f.read()).lower()
                    if not any(t.lower() in doc for t in checkable):
                        unfulfilled.append((lineno, m.group(0), checkable))
            prev_end, prev_idx, prev_trigger = m.end(), idx, trigger
    if not (unfulfilled or wordless):
        return
    lines = []
    if unfulfilled:
        lines.append(f"[RG:POINTER_PROMISE_UNFULFILLED] [refs_guard] SKILL.md has {len(unfulfilled)} unfulfilled pointer commitment(s):")
        lines += [f"    · SKILL.md:{ln} promises [{', '.join(tk)}], "
                  f"but {t} does not deliver (every promise word is absent "
                  "from the target's body)"
                  for ln, t, tk in unfulfilled]
    if wordless:
        if lines:
            lines.append("")
        lines.append(f"[RG:POINTER_PROMISE_EMPTY] [refs_guard] SKILL.md has {len(wordless)} pointer(s)"
                     " that yield no checkable promise word:")
        lines += [f"    · SKILL.md:{ln} → {t} (no content word besides the file reference "
                  "and the file's own name; the promise cannot be reconciled)"
                  for ln, t in wordless]
    lines += ["",
              "  A pointer promises what to read; the target's body must really contain it.",
              "  The file's own name and the head titles do not count as delivery — zero hits",
              "  means the content has drifted.",
              "  Fix: align the pointer's promise words with the file, or add the promised content to the file."]
    _fail(lines)


# ── text-loading logic shared by the three navigation checks ─────────────────
def _nav_text(root, agents_text):
    """Injected AGENTS.md text wins; without an injection and with no file on
    disk → leave a SKIP trace and return None. AGENTS.md is a B4 artifact, so
    this group of checks can only hang before B4 — and hanging must also leave a
    trace."""
    if agents_text is not None:
        return agents_text
    path = os.path.join(root, "AGENTS.md")
    if not os.path.isfile(path):
        SKIP_LOG.append("AGENTS.md does not exist yet (B4 artifact) — navigation table checks skipped")
        return None
    return _read_text(path)


# ── 8. navigation prose: AGENTS.md must not contain instruction patterns (M-N1) ─
def assert_no_prose_in_nav(root, agents_text=None):
    """AGENTS.md must not hit any instruction-pattern word in
    INSTRUCTION_PATTERNS. Red condition: a hit; the text carries AGENTS.md:line."""
    text = _nav_text(root, agents_text)
    if text is None:
        return
    bad = []
    for lineno, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        hit = [w for w in INSTRUCTION_PATTERNS if w.lower() in lowered]
        if hit:
            bad.append((lineno, hit))
    if bad:
        lines = [f"[refs_guard] AGENTS.md has {len(bad)} line(s) hitting an instruction pattern (navigation is a map, not a tutorial):"]
        lines += [f"    · AGENTS.md:{ln} hits {', '.join(h)}" for ln, h in bad]
        lines += ["",
                  "  Verb-style instructions belong in SKILL.md or ORCHESTRATION.md; the navigation table keeps only \"item → location\".",
                  "  Fix: move the instruction out, and make the navigation line a pure pointer."]
        _fail(lines)


# ── 9. navigation dead links: path cells must exist (M-N2) ───────────────────
# Documents carrying a navigation table, each with the base its cells resolve
# against. AGENTS.md cells are repo-root-relative; INDEX.md is section-scoped, so
# its cells were rewritten to carry their own directory prefix and it resolves from
# the root like AGENTS.md; casestudy/README.md lives one level down and resolves from
# its own directory.
#
# Why this list and not just AGENTS.md: measured before the extension, AGENTS.md had
# **zero** path-like cells, so the check passed while inspecting nothing — a green
# that carried no information, sitting inside the very gate meant to prevent exactly
# that. Extending the surface is what gives it teeth; a check that cannot fail is
# not a check.
NAV_DOCS = (
    ("AGENTS.md", ""),
    ("INDEX.md", ""),
    (os.path.join("casestudy", "README.md"), "casestudy"),
)


def _nav_dead_cells(root, doc_rel, base_rel, text=None):
    """Dead path-like cells in one navigation table. Returns [(line, cell)].

    A cell is resolved against the document's own base. Directories count as
    existing: a cell like `examples/data/` names a real directory, and requiring
    isfile would red it for the wrong reason — which is the noise discipline at
    work (noise is worse than a miss, because a gate that cries wolf gets switched off).
    """
    if text is None:
        path = os.path.join(root, doc_rel)
        if not os.path.isfile(path):
            SKIP_LOG.append(f"{doc_rel} does not exist — its navigation cells were not checked")
            return None
        text = _read_text(path)
    base = os.path.join(root, base_rel) if base_rel else root
    bad, seen = [], 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        for cell in (c.strip() for c in line.strip().strip("|").split("|")):
            # Backticks are markdown formatting, not part of the path. Measured
            # before this fix: `_CELL_PATH_RE` has no backtick in its character
            # class, so every cell written in the repo's own prevailing style —
            # `` `scripts/breakingdiff.py` `` — matched nothing and was never
            # checked. The extension to three documents would have bought three
            # vacuous greens. Strip the wrapper before deciding what a cell is.
            probe = cell.strip("`").strip()
            if not _CELL_PATH_RE.match(probe):
                continue
            seen += 1
            target = os.path.join(base, probe.replace("\\", "/").replace("/", os.sep))
            if not os.path.exists(target):
                bad.append((lineno, cell))
    return bad, seen


def assert_nav_links_exist(root, agents_text=None):
    """A cell in a navigation table that looks like a path (has a file suffix or
    a path separator) must exist relative to that document's base. Red condition:
    a dead cell; the text carries the document, the line number and the path.

    agents_text is kept for the injected-fixture path: it substitutes AGENTS.md's
    text, the other documents are read from disk. A check that cannot be pointed at
    a self-made fixture cannot be tested without mutating the repository.
    """
    injected = {"AGENTS.md": agents_text} if agents_text is not None else {}
    per_doc = []
    total_seen = 0
    for doc_rel, base_rel in NAV_DOCS:
        text = injected.get(doc_rel)
        out = _nav_dead_cells(root, doc_rel, base_rel, text)
        if out is None:
            continue
        bad, seen = out
        total_seen += seen
        if bad:
            per_doc.append((doc_rel, bad))
    if total_seen == 0:
        # A green over an empty surface is the failure this check was extended to
        # remove, so it must be visible — but the judgement is made across the WHOLE
        # navigation surface, not per document. Two of the three documents legitimately
        # carry no path-like cells (AGENTS.md uses a different cell syntax;
        # casestudy/README.md uses inline markdown links, covered by the relative-link
        # check). Warning per document would be noise, and a gate that manufactures
        # noise gets switched off — which is worse than the miss it was meant to close.
        WARN_LOG.append(
            f"navigation cells: 0 path-like cell across all {len(NAV_DOCS)} table(s) — "
            f"this check had nothing to verify, so its green carries no information")
    if per_doc:
        total = sum(len(b) for _, b in per_doc)
        lines = [f"[refs_guard] {total} navigation cell(s) pointing at paths that do not exist:"]
        for doc_rel, bad in per_doc:
            lines += [f"    · {doc_rel}:{ln} → {c}" for ln, c in bad]
        lines += ["",
                  "  Navigation that points at empty space is worse than no navigation: the reader thinks there is a road.",
                  "  Cells are resolved against the document's own base — write them with the",
                  "  directory prefix they need, or correct the path, or delete the row."]
        _fail(lines)


# ── 9b. relative markdown links: the syntax the prose files actually use ────
# The nav-cell check reads table cells. The README/AGENTS/casestudy-README tables
# also carry inline markdown links, which _CELL_PATH_RE cannot see — measured: the
# casestudy README has 11 links and 0 path-like cells, so a pointer typo there was
# invisible to every check. This is the layer that closes it, and it is what would
# have caught the broken `TEACHING-port.md` link.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((?!https?:|mailto:)([^)#\s]+)(?:#[^)]*)?\)")
_MD_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".trae"}


def assert_no_dead_relative_links(root, extra_files=None):
    """Every relative markdown link in the repository must resolve. Red condition:
    a dead link; the text carries file, line and target.

    Scanned: every .md under root, skipping VCS/tool/build directories. The
    probes/**/_grader_local/ tree is deliberately NOT skipped here beyond the generic
    rule — those files are gitignored precisely so they stay out of the product, and
    a grader note pointing at a now-deleted case file is still a dead link in the repo.
    """
    dead = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _MD_SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            base = os.path.dirname(path)
            try:
                text = _read_text(path)
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for m in _MD_LINK_RE.finditer(line):
                    target = m.group(1)
                    if not os.path.exists(os.path.join(base, target)):
                        dead.append((rel, lineno, target))
    for rel, _ln, target in (extra_files or []):
        dead.append((rel, 0, target))
    if dead:
        lines = [f"[refs_guard] {len(dead)} relative markdown link(s) point at paths that do not exist:"]
        lines += [f"    · {rel}:{ln} → {t}" for rel, ln, t in dead]
        lines += ["",
                  "  A broken pointer is worse than no pointer: the reader follows it into empty space.",
                  "  Fix: add the missing file, or point the link at a file that exists."]
        _fail(lines)


# ── 10. line-count warning: outside the reference band → warn, never block (M-N5/M-P1) ─
def warn_nav_line_count(root, agents_text=None):
    """AGENTS.md's physical line count outside NAV_LINE_BAND (closed interval) →
    a WARN_LOG trace (carrying the actual count), never raising. The line count
    is a health metric: too thin means navigation that should be there is
    missing, too fat means prose has seeped back in — neither is a
    reference-integrity problem, so neither earns a delivery block. The account
    is physical lines, not non-blank lines — the line-count fixture contains
    blank lines and the test asserts on physical lines."""
    text = _nav_text(root, agents_text)
    if text is None:
        return
    n = len(text.splitlines())
    lo, hi = NAV_LINE_BAND
    if not (lo <= n <= hi):
        WARN_LOG.append(f"AGENTS.md line count {n} is outside the [{lo},{hi}] reference band — "
                        "the navigation table has grown or shrunk; give it a human look")


# ── 11. hooks pairing: the two test files must exist together (M-H4) ────────
def assert_hooks_contract_pair(root):
    """scripts/hooks_contract_test.py and scripts/hook_entry_test.py must exist
    together. If the former is absent → SKIP (B5 artifact not landed; the file
    being waited for is named, and it turns into a real check automatically once
    that file lands); the former present while the latter absent → red."""
    contract = os.path.join(root, "scripts", "hooks_contract_test.py")
    entry = os.path.join(root, "scripts", "hook_entry_test.py")
    if not os.path.isfile(contract):
        SKIP_LOG.append("scripts/hooks_contract_test.py does not exist yet (B5 artifact) — "
                        "hooks pairing check skipped; it becomes a real check once that file lands")
        return
    if not os.path.isfile(entry):
        _fail([
            "[refs_guard] hooks contract pair is half missing:",
            f"    · {contract} is present, {entry} is not",
            "",
            "  A contract test and the entry point it exercises must land as a pair; one side alone is false verification.",
            "  Fix: add the missing half, or withdraw the half that is there.",
        ])


# ── 12. changing SKILL requires changing CHANGELOG (M-D8) ───────────────────
def assert_changelog_on_skill_change(changed_files):
    """SKILL.md in this change list requires CHANGELOG.md in the same list.
    Path matching normalizes separators and compares basenames: git speaks
    forward slashes, an injector may hand backslashes, and that difference must
    not let "changed SKILL without changing CHANGELOG" slip through."""
    norm = [f.replace("\\", "/") for f in changed_files]
    skill_changed = any(os.path.basename(f) == "SKILL.md" for f in norm)
    changelog_changed = any(os.path.basename(f) == "CHANGELOG.md" for f in norm)
    if skill_changed and not changelog_changed:
        _fail([
            "[refs_guard] this change touches SKILL.md but not CHANGELOG.md:",
            "    · SKILL.md (changed) / CHANGELOG.md (unchanged)",
            "",
            "  A promise that changed must leave a trace, otherwise the capability declaration table is self-referential.",
            "  Fix: add an entry to CHANGELOG.md (what changed, the readout, the date).",
        ])


def _changed_files_from_git():
    """The change list behind --check-commit: git diff --name-only HEAD takes
    every change in the working tree relative to HEAD (staged and unstaged
    together), one parse layer fewer than status --porcelain. If git is
    unavailable or this is not a repository, return None and let the caller map
    it to exit code 2 — when the list cannot be computed, hang rather than run
    empty."""
    try:
        out = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


# ── 13. agent-visible set boundary: full-text health check of AGENTS.md (M-N3) ─
# grader-only prefixes are grading-side read-set and reference paths (evaluation
# layer plan v3 §0b); appearing in the agent-visible set is a breach. The list
# may only grow, never shrink: shrinking = the visible-set boundary was quietly
# widened.
GRADER_ONLY_PREFIXES = ("probes/", "evidence/")

# Full-text path shape: a repo-relative path ending in a common file suffix,
# optionally with directory prefixes. A bare directory (scripts/ and the like)
# does not count — it promises no specific file; that is left to M-N2's cell
# criterion and to human review, and only files are recognized here.
_MANIFEST_PATH_RE = re.compile(
    r"(?:[\w.-]+/)*[\w-][\w./\\-]*\.(?:py|md|txt|json|toml|cfg|ini|sh|ps1|bat)")

# A URL is not a repo-relative path: https://example.com/docs/page.md would be
# cut by the path regex into "example.com/docs/page.md" and looked up on disk,
# a false dead link (B4 review evidence). Strip the whole token before scanning;
# the path criterion and the test_ function-name criterion share this step.
_URL_TOKEN_RE = re.compile(r"\b[A-Za-z][\w+.-]*://\S+")

# Assertion-content shape: an identifier starting with test_. P11 refinement —
# test file names are allowed on the command line (they have to be run), but
# naming an assertion function in prose writes the grading map into the
# navigation.
_TEST_FUNC_RE = re.compile(r"\btest_[A-Za-z0-9_]+")

# Command-line openers: a command line inside a verification block is exempt
# from the test_ function-name criterion once it hits one of these.
_COMMAND_STARTS = ("python", "pytest", "cd ")


def assert_agent_visible_manifest(root, agents_text=None):
    """Health-check all of AGENTS.md as "what an agent will read"; the three
    sub-criteria each go red independently:
    a) every repo-relative path in the full text (tables and code blocks
       included) must exist — navigation pointing at empty space makes the
       reader think there is a road. Division of labor with M-N2: M-N2 checks
       table cells only (map completeness), this checks the full text
       (visible-set boundary); both accounts are kept.
    b) grader-only prefixes must not appear — a grading-side material location
       that is visible to the agent is a leaked answer.
    c) test_ assertion function names must not appear outside a command-line
       context — strip path tokens first (test_xxx.py is a file name, not a
       function name); lines opened by a command are exempt as a whole.
    Red condition: any hit; the text carries AGENTS.md:line and the
    path/prefix/function name."""
    text = _nav_text(root, agents_text)
    if text is None:
        return
    lines = text.splitlines()
    hit = [(ln, p) for ln, line in enumerate(lines, 1)
           for p in GRADER_ONLY_PREFIXES if p in line]
    if hit:
        _fail([f"[refs_guard] AGENTS.md has {len(hit)} occurrence(s) of a grader-only prefix"
               " (grading-side material, forbidden in the agent-visible set):"]
              + [f"    · AGENTS.md:{ln} → {p}" for ln, p in hit] + [
              "",
              "  These two prefixes belong to the grading-side read set; writing them into the navigation is a visible-set breach.",
              "  Fix: delete the reference there; if the agent really needs the material, move it to a public location and point there."])
    dead = []
    for ln, line in enumerate(lines, 1):
        for m in _MANIFEST_PATH_RE.finditer(_URL_TOKEN_RE.sub("", line)):
            rel = m.group(0).replace("\\", "/").replace("/", os.sep)
            if not os.path.isfile(os.path.join(root, rel)):
                dead.append((ln, m.group(0)))
    if dead:
        _fail([f"[refs_guard] AGENTS.md has {len(dead)} path(s) pointing at files that do not exist"
               " (full-text scan, not just tables):"]
              + [f"    · AGENTS.md:{ln} → {p}" for ln, p in dead] + [
              "",
              "  A map pointing at empty space is worse than no map: the reader thinks there is a road.",
              "  Fix: add the missing file, or point the path at a location that exists."])
    leaked = []
    for ln, line in enumerate(lines, 1):
        if line.strip().startswith(_COMMAND_STARTS):
            continue
        m = _TEST_FUNC_RE.search(
            _MANIFEST_PATH_RE.sub("", _URL_TOKEN_RE.sub("", line)))
        if m:
            leaked.append((ln, m.group(0)))
    if leaked:
        _fail([f"[refs_guard] AGENTS.md has {len(leaked)} occurrence(s) naming a test_ assertion"
               " function outside a command-line context:"]
              + [f"    · AGENTS.md:{ln} → {name}" for ln, name in leaked] + [
              "",
              "  A test file name is allowed on a command line; naming an assertion function in prose writes the grading map into the navigation.",
              "  Fix: drop the function name and use a file-level pointer such as \"tests live in scripts/xxx_test.py\"."])


# ── 14. zero content overlap between the two files (M-N4) ───────────────────
def assert_no_overlap_between_agents_and_skill(root, agents_text=None,
                                               skill_text=None):
    """The non-blank lines of AGENTS.md and SKILL.md must intersect in the empty
    set. Navigation is another map; copying sentences means drift — when
    SKILL.md changes, the copy inside AGENTS.md does not follow, and the two
    accounts tell different stories from then on. Title lines count too (title
    wording must differ between the two files); blank lines do not (layout is
    not content). Red condition: non-empty intersection; the text lists the
    shared lines."""
    agents = _nav_text(root, agents_text)
    if agents is None:
        return
    if skill_text is None:
        skill_text = _read_text(os.path.join(root, "SKILL.md"))
    shared = {ln.strip() for ln in agents.splitlines() if ln.strip()} & {
        ln.strip() for ln in skill_text.splitlines() if ln.strip()}
    if shared:
        ordered = sorted(shared)
        _fail([f"[refs_guard] AGENTS.md and SKILL.md share {len(ordered)} verbatim line(s):"]
              + [f"    · {ln}" for ln in ordered] + [
              "",
              "  Navigation and rules are two maps: when SKILL.md changes, the copy inside AGENTS.md does not follow.",
              "  Fix: reword these lines into your own words, or delete them in favor of a pointer."])


# ── CLI: the run_checks summary plus the main facade ─────────────────────────
def run_checks(root, pointer_form_active=True, checks=None):
    """Run the default 13 checks and return a fixed six-key dict:
    {root, checks: {function name: pass/skip/warn/red/error},
     reds: [(check name, text)], skips, warnings, exit_code}

    The default surface must hold all 13 (including M-N3/N4): a programmatic
    consumer calls run_checks(root) without going through main(), so any check
    mounted only on the injection channel runs silently never — the default
    check surface is aligned key by key with the test-side frozen list, which
    prevents quiet additions and removals.
    pointer_form_active defaults to True (M-P3 active since B8): once the live
    repo's pointers were converted to the three-part form this check stayed on
    the default surface, and the suspended branch was deleted.
    The checks argument accepts [(name, zero-arg function)] for extra
    injection — zero-arg, so the injector closes over root itself; this serves
    scenarios beyond the default surface. Exceptions other than RefsError count
    as runtime errors (exit 2), separate from gate semantics.
    """
    SKIP_LOG.clear()
    WARN_LOG.clear()
    results, reds = {}, []

    def _run(name, fn):
        before_skip, before_warn = len(SKIP_LOG), len(WARN_LOG)
        try:
            fn()
        except RefsError as e:
            results[name] = "red"
            reds.append((name, str(e)))
        except Exception as e:                      # noqa: BLE001 — every check that did not run must show up explicitly
            results[name] = "error"
            reds.append((name, f"[refs_guard] {name} raised a runtime error (exit 2 semantics): {e!r}"))
        else:
            if len(SKIP_LOG) > before_skip:
                results[name] = "skip"
            elif len(WARN_LOG) > before_warn:
                results[name] = "warn"
            else:
                results[name] = "pass"

    plan = [
        ("assert_no_dead_links",
         lambda: assert_no_dead_links(root)),
        ("assert_no_orphans",
         lambda: assert_no_orphans(root)),
        ("assert_no_reference_cross_links",
         lambda: assert_no_reference_cross_links(root)),
        ("assert_toc_required", lambda: assert_toc_required(root)),
        ("assert_no_host_vars_in_references",
         lambda: assert_no_host_vars_in_references(root)),
        ("assert_pointer_promises",
         lambda: assert_pointer_promises(root)),
        ("assert_no_prose_in_nav", lambda: assert_no_prose_in_nav(root)),
        ("assert_nav_links_exist", lambda: assert_nav_links_exist(root)),
        ("assert_no_dead_relative_links", lambda: assert_no_dead_relative_links(root)),
        ("warn_nav_line_count", lambda: warn_nav_line_count(root)),
        ("assert_hooks_contract_pair", lambda: assert_hooks_contract_pair(root)),
        ("assert_agent_visible_manifest",
         lambda: assert_agent_visible_manifest(root)),
        ("assert_no_overlap_between_agents_and_skill",
         lambda: assert_no_overlap_between_agents_and_skill(root)),
    ]
    if pointer_form_active:
        plan.append(("assert_pointer_form", lambda: assert_pointer_form(root)))

    for name, fn in plan:
        _run(name, fn)
    for name, fn in (checks or []):
        _run(name, fn)

    code = EXIT_RUNTIME_ERROR if any(v == "error" for v in results.values()) \
        else (EXIT_GATE_FAIL if reds else EXIT_PASS)
    return {"root": root, "checks": results, "reds": reds,
            "skips": list(SKIP_LOG), "warnings": list(WARN_LOG),
            "exit_code": code}


def main(root=None):
    """Live-repo entry point. root defaults to the repository root (this file
    lives under scripts/, so its parent is the root). Every SKIP/WARN/RED is
    printed — a log that is not printed is still invisible to people; the last
    link of the no-silence chain is here. --check-commit goes through the
    changed-files gate (a separate M-D8 entry point)."""
    if "--check-commit" in sys.argv:
        return _main_check_commit()
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # No try wrapper: _run absorbs all 13 checks (one that did not run gets the
    # error key → exit 2), so this level cannot construct a crashing scenario;
    # wrapping it would be a dead branch.
    rep = run_checks(root)

    print(f"refs_guard live-repo checks: {root}")
    for s in rep["skips"]:
        print(f"SKIP {s}")
    for w in rep["warnings"]:
        print(f"WARN {w}")
    for name, msg in rep["reds"]:
        print(f"RED [{name}]")
        print(msg)
    n_pass = sum(1 for v in rep["checks"].values() if v == "pass")
    print(f"\n{n_pass}/{len(rep['checks'])} passed"
          f", {len(rep['reds'])} red, {len(rep['skips'])} SKIP, {len(rep['warnings'])} warn")
    return rep["exit_code"]


def _main_check_commit():
    """The change list is computed from git diff --name-only HEAD (in one
    sentence: staged and unstaged changes of the working tree relative to HEAD
    are taken together, one parse layer fewer than status --porcelain); git
    unavailable → exit code 2, and if the list cannot be computed, do not set a
    gate."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = _changed_files_from_git()
    if files is None:
        print("[refs_guard] git is unavailable or this is not a repository; --check-commit cannot compute the changed-files list",
              file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    try:
        assert_changelog_on_skill_change(files)
    except RefsError as e:
        print(e)
        return EXIT_GATE_FAIL
    print(f"[refs_guard] --check-commit passed ({len(files)} changed file(s), SKILL/CHANGELOG pair holds)")
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())

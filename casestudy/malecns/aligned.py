"""malecns strength-layer case — selecting accounts so that they align: bounded claims.

[What this script teaches]
Get the **strength shape** of a claim wrong, and true data looks like bad data. For the same observable
(number of neurons per type × hemisphere, transmitter composition of a type), a claim can be written at three strengths:

    point value (n = exact value)  <  strict equality (nL = nR)  <  bounded (|n − expected| ≤ band)

Point value / strict equality produce a large false-red surface on biological data whose left-right counts commonly
deviate from the baseline (see misaligned.py: 2,720 / 4,354 true data points go red, 12.3% / 19.6%); a bounded claim
puts "normal fluctuation" inside the band and only lets points outside it go red. This script is what alignment looks
like: domain = existence points (Q, an always-true anchor), three bounded accounts P1/P2/P3 plus an existence
baseline, run through the real engine to an N=4 readout.

[Read path]
Both feather files are ARROW1 (Feather V2). pyarrow 25.0.1 measured both tables readable directly
(the early probe's claim that "Lz4 compressed input contains more than one frame" could not be reproduced in this
environment — disproved by a reviewer, and test_aligned.py now carries an independent pyarrow recomputation surface).
This file still decodes Arrow IPC itself: hand-decoded footer/schema flatbuffer + lz4 frames (block-dependent,
FLG bit5=0). The reason is not that pyarrow cannot read them but **read-path autonomy**: the readout does not hang
on a third-party library's version behavior, and it runs with zero dependencies; the in-house path also verifies the
decompressed length buffer by buffer, so a wrong read blows up on the spot instead of silently returning a value.
The decoder and pyarrow reconcile cell by cell on both tables (the reconciliation cases in test_aligned.py), so the
two read paths are each other's reconciliation.

How to run: python aligned.py
"""
import math
import os
import struct
import sys
from array import array

# The Windows console defaults to GBK and the report uses glyphs outside that code
# page. Switch to UTF-8 and downgrade unencodable characters so the script cannot
# die with UnicodeEncodeError while printing its own warning.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
# ★ Search upward for breakingdiff.py instead of hard-coding "how many levels up" (same reason as pdg/aligned.py:
#   a hard-coded depth silently becomes ModuleNotFoundError once the directory moves).
def _find_scripts_root():
    cur = _HERE
    while True:
        if os.path.isfile(os.path.join(cur, "scripts", "breakingdiff.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit(
                "[FATAL] cannot find scripts/breakingdiff.py above this directory. "
                "       This case study must run inside the breakingdiff repository "
                "(scripts/ and casestudy/ at the same level).")
        cur = parent

_ROOT = _find_scripts_root()
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from breakingdiff import Claim, compare_n, render_n  # noqa: E402

FEATHER_ANNOT = "body-annotations-male-cns-v0.9-minconf-0.5.feather"
FEATHER_NT = "body-neurotransmitters-male-cns-v0.9.feather"
ANNOT_PATH = os.path.join(_HERE, FEATHER_ANNOT)
NT_PATH = os.path.join(_HERE, FEATHER_NT)


def _require_corpus():
    # ★ Same as pdg: checking exists is not enough; an empty file must be stopped too (an interrupted download leaves half a file).
    missing = [n for n, p in ((FEATHER_ANNOT, ANNOT_PATH), (FEATHER_NT, NT_PATH))
               if not os.path.isfile(p) or os.path.getsize(p) == 0]
    if missing:
        raise SystemExit(
            f"[FATAL] corpus missing or empty: {', '.join(missing)}\n"
            f"       Run python fetch_corpus.py first to download it into this directory.")


# ============================================================
# Arrow IPC (Feather V2) + lz4 self-decoder
# ============================================================
LZ4_MAGIC = 0x184D2204

# Arrow message header types (MessageHeader union)
HDR_SCHEMA, HDR_DICT, HDR_RECORD = 1, 2, 3
# Arrow type union tags (this case needs only these)
T_INT, T_FLOAT, T_UTF8, T_LIST, T_STRUCT = 2, 3, 5, 12, 13


def _u16(b, o):
    return b[o] | (b[o + 1] << 8)


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _i64(b, o):
    return struct.unpack_from("<q", b, o)[0]


def _tab(b, pos):
    """flatbuffer table: at pos there is a soffset, vtable = pos - soffset."""
    so = struct.unpack_from("<i", b, pos)[0]
    vt = pos - so
    return vt, _u16(b, vt), pos


def _slot(b, vt, vts, tp, fid):
    """Look up a field slot in the vtable (in-table offset), return the absolute slot; 0 if the field is absent."""
    o = 4 + 2 * fid
    if o >= vts:
        return 0
    off = _u16(b, vt + o)
    return tp + off if off else 0


def _ind(b, s):
    """Indirect field (sub-table/vector/string): the slot content is a u32 offset relative to the slot.
    ★ Trap on record: a slot and its content are two jumps; merging them reads a garbage offset."""
    return s + _u32(b, s) if s else 0


def _fstr(b, s):
    s = _ind(b, s)
    n = _u32(b, s)
    return b[s + 4:s + 4 + n].decode("utf-8")


def lz4_block_decode(src, out):
    """Decode an LZ4 block, appending into out (out already holds the history window, supporting block dependence)."""
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                c = src[i]
                i += 1
                lit += c
                if c != 255:
                    break
        if lit:
            out += src[i:i + lit]
            i += lit
        if i == n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        if off == 0:
            raise ValueError("lz4 offset 0")
        ml = tok & 15
        if ml == 15:
            while True:
                c = src[i]
                i += 1
                ml += c
                if c != 255:
                    break
        ml += 4
        cur = len(out)
        if off > cur:
            raise ValueError(f"lz4 offset {off} exceeds history {cur}")
        if off >= ml:
            out += out[cur - off:cur - off + ml]
        else:
            # overlapping match: copy byte by byte to preserve LZ4 semantics (reading back from a growing dst)
            for j in range(ml):
                out.append(out[cur - off + j])


def lz4_frame_decode(buf, pos):
    """Decode a single lz4 frame. With block dependence (FLG bit5=0) use the first 64 KB of output as the history window.
    Returns (decompressed data, start of the next frame, block count, whether blocks are independent)."""
    if _u32(buf, pos) != LZ4_MAGIC:
        raise ValueError(f"not an lz4 frame header at {pos}: {buf[pos:pos + 4].hex()}")
    flg = buf[pos + 4]
    if (flg >> 6) != 1:
        raise ValueError(f"bad lz4 FLG version bits: {flg >> 6}")
    has_cksum = bool(flg & 0x10)
    has_csize = bool(flg & 0x08)
    has_dictid = bool(flg & 0x04)
    p = pos + 6
    if has_csize:
        p += 8
    if has_dictid:
        p += 4
    p += 1  # header checksum
    hist = b""
    out_all = bytearray()
    nblocks = 0
    while True:
        bsz = _u32(buf, p)
        p += 4
        if bsz == 0:
            break  # EndMark
        stored = bsz & 0x80000000
        blen = bsz & 0x7FFFFFFF
        block = buf[p:p + blen]
        p += blen
        out = bytearray(hist)
        base = len(hist)
        if stored:
            out += block
        else:
            lz4_block_decode(block, out)
        out_all += out[base:]
        hist = bytes(out[-65536:]) if len(out) > 65536 else bytes(out)
        nblocks += 1
    if has_cksum:
        p += 4
    return bytes(out_all), p, nblocks, bool(flg & 0x20)


def lz4_frames_decode(buf):
    """★ The core trap of this case: one Arrow compressed buffer contains several lz4 frames in a row.
    Split frame by frame, decode each, concatenate — pyarrow's decompressor assumes exactly one frame and
    therefore refuses with "more than one frame"."""
    out, pos, frames = [], 0, 0
    indep = []
    while pos < len(buf):
        if not any(buf[pos:pos + 8]):
            break  # trailing alignment zero padding
        data, pos, _nb, ind = lz4_frame_decode(buf, pos)
        out.append(data)
        frames += 1
        indep.append(ind)
    return b"".join(out), frames, indep


def _bitmap_nulls(valid, n):
    return {i for i in range(n) if not (valid[i >> 3] >> (i & 7)) & 1}


def _parse_field(fb, fo):
    fvt, fvts, ftp = _tab(fb, fo)
    name = _fstr(fb, _slot(fb, fvt, fvts, ftp, 0))
    tslot = _slot(fb, fvt, fvts, ftp, 2)
    ttype = fb[tslot] if tslot else 0
    typ = _ind(fb, _slot(fb, fvt, fvts, ftp, 3))
    dic = _ind(fb, _slot(fb, fvt, fvts, ftp, 4))
    dicid, idxbits = None, None
    if dic:
        dvt, dvts, dtp = _tab(fb, dic)
        s0 = _slot(fb, dvt, dvts, dtp, 0)
        dicid = _i64(fb, s0) if s0 else 0
        it = _ind(fb, _slot(fb, dvt, dvts, dtp, 1))
        if it:
            ivt, ivts, itp = _tab(fb, it)
            s0 = _slot(fb, ivt, ivts, itp, 0)
            idxbits = _i32(fb, s0) if s0 else 32
    detail = None
    if typ:
        tvt, tvts, ttp = _tab(fb, typ)
        s0 = _slot(fb, tvt, tvts, ttp, 0)
        if ttype == T_INT:
            detail = _i32(fb, s0) if s0 else 0  # bitWidth
        elif ttype == T_FLOAT:
            detail = fb[s0] if s0 else 2        # precision (2=double)
    cvec = _ind(fb, _slot(fb, fvt, fvts, ftp, 5))
    children = ([_parse_field(fb, c) for c in _vec_tables(fb, cvec)]
                if cvec else [])
    return (name, ttype, detail, dicid, idxbits, children)


def _vec_tables(b, vec):
    return [_ind(b, vec + 4 + 4 * i) for i in range(_u32(b, vec))]


def _nbufs(ttype, dicid, children):
    """Number of buffers this field has in a record batch — skipped columns must advance by this count too,
    ★ otherwise the buffer pointer shifts for every Utf8/List column after the first skipped one."""
    if dicid is not None:
        return 2                       # validity + indices
    if ttype == T_UTF8:
        return 3                       # validity + offsets + data
    if ttype == T_LIST:
        return 2 + sum(_nbufs(c[1], c[3], c[5]) for c in children)
    if ttype == T_STRUCT:
        return 1 + sum(_nbufs(c[1], c[3], c[5]) for c in children)
    return 2                           # int/float/bool: validity + data


def _parse_schema(fb, sch):
    vt, vts, tp = _tab(fb, sch)
    fvec = _ind(fb, _slot(fb, vt, vts, tp, 1))
    return [_parse_field(fb, fo) for fo in _vec_tables(fb, fvec)]


def _parse_message(data, pos):
    cont = _u32(data, pos)
    base = pos + 8 if cont == 0xFFFFFFFF else pos + 4
    vt, vts, tp = _tab(data, base + _u32(data, base))
    s1 = _slot(data, vt, vts, tp, 1)
    htype = data[s1] if s1 else 0
    hdr = _ind(data, _slot(data, vt, vts, tp, 2))
    s3 = _slot(data, vt, vts, tp, 3)
    bodylen = _i64(data, s3) if s3 else 0
    return htype, hdr, bodylen


def _parse_rb(data, hdr):
    vt, vts, tp = _tab(data, hdr)
    s0 = _slot(data, vt, vts, tp, 0)
    length = _i64(data, s0) if s0 else 0
    nv = _ind(data, _slot(data, vt, vts, tp, 1))
    bv = _ind(data, _slot(data, vt, vts, tp, 2))
    comp = _ind(data, _slot(data, vt, vts, tp, 3))
    codec = None
    if comp:
        cvt, cvts, ctp = _tab(data, comp)
        s0 = _slot(data, cvt, cvts, ctp, 0)
        codec = data[s0] if s0 else 0   # 0=LZ4_FRAME
    nodes, bufs = [], []
    if nv:
        for i in range(_u32(data, nv)):
            o = nv + 4 + 16 * i
            nodes.append((_i64(data, o), _i64(data, o + 8)))
    if bv:
        for i in range(_u32(data, bv)):
            o = bv + 4 + 16 * i
            bufs.append((_i64(data, o), _i64(data, o + 8)))
    return length, nodes, bufs, codec


def _blocks(fb, vecslot):
    """The Block vector in the footer: (offset, metaDataLength, bodyLength).
    ★ body start = offset + metaDataLength (metadata includes the alignment total with continuation),
    bodyLength is only a length — using it as the start reads the tail of the previous message."""
    if not vecslot:
        return []
    vec = _ind(fb, vecslot)
    out = []
    for i in range(_u32(fb, vec)):
        o = vec + 4 + 24 * i
        out.append((_i64(fb, o), _i32(fb, o + 8), _i64(fb, o + 16)))
    return out


def _decode_buffer(data, body, off, ln, codec):
    if not ln:
        return b""
    raw = data[body + off:body + off + ln]
    if codec == 0:
        expect = struct.unpack_from("<q", raw, 0)[0]
        out, _frames, _indep = lz4_frames_decode(raw[8:])
        if len(out) != expect:
            raise ValueError(f"lz4 decompressed {len(out)} != declared {expect}")
        return out
    return raw


def _decode_utf8(data, body, bufs, codec, nrows):
    dec = [_decode_buffer(data, body, o, l, codec) for (o, l) in bufs]
    valid, offs, blobs = dec
    memo = {}
    oi = array("i")
    oi.frombytes(offs)
    nulls = _bitmap_nulls(valid, nrows) if len(valid) else set()
    out = []
    get = memo.setdefault
    for i in range(nrows):
        if i in nulls:
            out.append(None)
            continue
        raw = blobs[oi[i]:oi[i + 1]]
        out.append(get(raw, raw.decode("utf-8")))
    return out


def _decode_scalar(data, body, bufs, codec, nrows, fmt):
    valid_b, data_b = bufs
    arr = array(fmt)
    arr.frombytes(_decode_buffer(data, body, data_b[0], data_b[1], codec))
    vraw = _decode_buffer(data, body, valid_b[0], valid_b[1], codec)
    nulls = _bitmap_nulls(vraw, nrows) if len(vraw) else set()
    return [None if i in nulls else arr[i] for i in range(nrows)]


_INT_FMT = {8: "b", 16: "h", 32: "i", 64: "q"}
_FP_FMT = {0: "e", 1: "f", 2: "d"}


def ipc_row_count(path):
    """Walk only to the record batch message headers and sum their lengths; decode no buffer.
    Used by fetch_corpus.py to generate the manifest's rows anchor — pyarrow cannot read the transmitter table,
    so both tables' row counts come from this path (the test side independently double-checks the annotation table's rows with pyarrow)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"ARROW1\x00\x00" or data[-6:] != b"ARROW1":
        raise ValueError(f"{os.path.basename(path)} is not in ARROW1 format")
    fs = _u32(data, len(data) - 10)
    fb = data[len(data) - 10 - fs:len(data) - 10]
    vt, vts, tp = _tab(fb, _u32(fb, 0))
    rbvec = _slot(fb, vt, vts, tp, 3)
    total = 0
    for (off, _mlen, _bl) in _blocks(fb, rbvec):
        htype, hdr, _ = _parse_message(data, off)
        if htype != HDR_RECORD:
            continue
        length, _nodes, _bufs, _codec = _parse_rb(data, hdr)
        total += length
    return total


def read_ipc_columns(path, wanted):
    """In-house Arrow IPC read: returns (dict[col] = list, total rows).
    Decodes only the wanted columns; other columns only advance the buffer pointer."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"ARROW1\x00\x00" or data[-6:] != b"ARROW1":
        raise ValueError(f"{os.path.basename(path)} is not in ARROW1 format")
    fs = _u32(data, len(data) - 10)
    fb = data[len(data) - 10 - fs:len(data) - 10]
    vt, vts, tp = _tab(fb, _u32(fb, 0))
    sch = _ind(fb, _slot(fb, vt, vts, tp, 1))
    dicvec = _slot(fb, vt, vts, tp, 2)
    rbvec = _slot(fb, vt, vts, tp, 3)
    fields = _parse_schema(fb, sch)

    dicts = {}
    for (off, mlen, _bl) in _blocks(fb, dicvec):
        htype, hdr, _ = _parse_message(data, off)
        if htype != HDR_DICT:
            continue
        dvt, dvts, dtp = _tab(data, hdr)
        s0 = _slot(data, dvt, dvts, dtp, 0)
        did = _i64(data, s0) if s0 else 0
        rec = _ind(data, _slot(data, dvt, dvts, dtp, 1))
        n, _nodes, bufs, codec = _parse_rb(data, rec)
        dicts[did] = _decode_utf8(data, off + mlen, bufs, codec, n)

    cols = {name: [] for name in wanted}
    total = 0
    for (off, mlen, _bl) in _blocks(fb, rbvec):
        htype, hdr, _ = _parse_message(data, off)
        if htype != HDR_RECORD:
            continue
        nrows, nodes, bufs, codec = _parse_rb(data, hdr)
        total += nrows
        body = off + mlen
        bi = 0
        for fi, (name, ttype, detail, dicid, idxbits, children) in enumerate(fields):
            nb = _nbufs(ttype, dicid, children)
            if name not in cols:
                bi += nb
                continue
            if nodes[fi][0] != nrows:
                raise ValueError(f"{name}: node row count {nodes[fi][0]} != batch row count {nrows}")
            if dicid is not None:
                idx = _decode_scalar(data, body, bufs[bi:bi + 2], codec, nrows,
                                     _INT_FMT[idxbits or 32])
                bi += nb
                vals = dicts[dicid]
                # null in a dictionary column = index slot None: record it faithfully as None,
                # do not raise (null is data, not an exception).
                cols[name] += [None if j is None else vals[j] for j in idx]
            elif ttype == T_UTF8:
                cols[name] += _decode_utf8(
                    data, body, bufs[bi:bi + 3], codec, nrows)
                bi += nb
            elif ttype == T_INT:
                cols[name] += _decode_scalar(
                    data, body, bufs[bi:bi + 2], codec, nrows,
                    _INT_FMT[detail])
                bi += nb
            elif ttype == T_FLOAT:
                cols[name] += _decode_scalar(
                    data, body, bufs[bi:bi + 2], codec, nrows,
                    _FP_FMT[detail])
                bi += nb
            else:
                raise ValueError(f"column {name}: type {ttype} is outside the in-house reader's range")
    return cols, total


# ============================================================
# Corpus readout (cached: the corpus is static once its hash is anchored, so a repeat read in the same process hits the cache)
# ============================================================
_CACHE = {}


def load_counts():
    """{(type, side): n} — existence points with non-empty type, somaSide ∈ {L,R}, count > 0.
    Cell-for-cell equal to test_aligned.py's independent pyarrow recomputation (the two read paths are each other's reconciliation)."""
    if "counts" in _CACHE:
        return _CACHE["counts"]
    _require_corpus()
    cols, _ = read_ipc_columns(ANNOT_PATH, ("type", "somaSide"))
    cs = {}
    for t, s in zip(cols["type"], cols["somaSide"]):
        if t is None or not str(t).strip():
            continue
        key = (str(t), str(s))
        cs[key] = cs.get(key, 0) + 1
    counts = {(t, s): n for (t, s), n in cs.items() if s in ("L", "R") and n > 0}
    _CACHE["counts"] = counts
    _CACHE["per_type_total"] = _per_type_totals(cs)
    return counts


def _per_type_totals(cs):
    """Total body count of a type (including the M side and the side-less rows — that is where error mode ①'s baseline gets contaminated)."""
    pt = {}
    for (t, _s), n in cs.items():
        pt[t] = pt.get(t, 0) + n
    return pt


def load_type_totals():
    load_counts()
    return _CACHE["per_type_total"]


def load_nt_fractions():
    """{type: (voted main transmitter, its share, the data's self-reported celltype_predicted_nt)}.

    Two accounts: neuron-level majority vote (predicted_nt votes per body, unclear counts as a vote, a tie takes the
    lexicographically largest — 136 tied vote patterns make that rule discriminating) vs the data's self-reported
    type-level label (celltype_predicted_nt; measured 0 types with multiple values). Share denominator = the number
    of members of that type that have a transmitter row. Key universe = types with non-empty cell_type in the
    transmitter table (11,732, equal to the number of unique types in the annotation table)."""
    if "fr" in _CACHE:
        return _CACHE["fr"]
    _require_corpus()
    cols, _ = read_ipc_columns(
        NT_PATH, ("cell_type", "predicted_nt", "celltype_predicted_nt"))
    votes = {}
    cellpreds = {}
    nrows = {}
    for c, pn, cp in zip(cols["cell_type"], cols["predicted_nt"],
                         cols["celltype_predicted_nt"]):
        if c is None or not str(c).strip():
            continue
        c = str(c)
        nrows[c] = nrows.get(c, 0) + 1
        if pn is not None:
            votes.setdefault(c, {}).setdefault(pn, 0)
            votes[c][pn] += 1
        cellpreds.setdefault(c, set()).add(cp)
    fr = {}
    for c, cnt in votes.items():
        mx = max(cnt.values())
        top = sorted(k for k, v in cnt.items() if v == mx)
        cps = [x for x in cellpreds[c] if x is not None]
        fr[c] = (top[-1], cnt[top[-1]] / nrows[c],
                 cps[0] if len(cps) == 1 else None)
    _CACHE["fr"] = fr
    return fr


def domain_points():
    """Comparison domain: the sorted list of existence points (same key set as load_counts)."""
    return sorted(load_counts())


def __getattr__(name):
    # PEP 562: CRITERIA is built lazily. Importing this module must do zero corpus IO
    # (both fetch_corpus.py and misaligned.py import it, and the import must succeed even
    # when the corpus is absent); only the first access to CRITERIA scans the corpus.
    if name == "CRITERIA":
        pts = domain_points()
        globals()["CRITERIA"] = pts
        return pts
    raise AttributeError(name)


# ============================================================
# Accounts
# ============================================================
_ANNOT_SRC = "MaleCNS v0.9 body-annotations feather (type/somaSide columns)"
_NT_SRC = ("MaleCNS v0.9 body-neurotransmitters feather"
           "(predicted_nt column, in-house IPC read)")


def _fact(s):
    """Provenance quote holder: quote and quote_source are the same string (verified verbatim at construction)."""
    return s


def _side_expect(counts, t):
    """The side-count expectation for this type: two-sided types expect half of both sides, one-sided types the full complement."""
    nL, nR = counts.get((t, "L"), 0), counts.get((t, "R"), 0)
    return (nL + nR) // 2 if (nL > 0 and nR > 0) else nL + nR


def build_q_claim():
    """Existence baseline Q: the anchor on the domain, always true. Whether it holds is computed by the predicate on
    the real domain, not guaranteed by a gate (source_tests keeps two real existence points as examples)."""
    return Claim(
        name="Q existence baseline (annotation-table existence points)",
        predicate=lambda x: x in load_counts(),
        applies=lambda x: True,
        domain_note=("domain = annotation-table existence points with non-empty type × somaSide∈{L,R} × count>0, "
                     "sorted; the 392 M-side bodies and 60,748 side-less bodies stay out of the domain "
                     "(P2 is defined only for L/R)"),
        source=_ANNOT_SRC,
        quote=_fact("rule=exists; domain=annotation(type×somaSide); "
                    "points=22176"),
        quote_source=_fact("rule=exists; domain=annotation(type×somaSide); "
                           "points=22176"),
        source_tests=((("KCab-s", "L"), True), (("R1-R6", "R"), True)),
    )


def build_p1_claim():
    """P1 count band: the side count lands within "half of the two-sided total ± 30%".

    The 30% width is a design tolerance, with its dimension taken from the within-dataset left-right difference
    distribution — Schlegel 2024's ~30% cannot be cited as the source: that is cross-dataset individual variation
    between FlyWire and hemibrain, not the same quantity as a within-dataset left-right difference. Mathematically,
    for a two-sided type |nL−n0| = |nL−nR|/2, so P1 (±30%) and P2 (10%) are the coarse and fine grades of the same
    statistic; this band is three times looser than P2 and measured only 12/22,176 false reds — slightly loose,
    conservative, harmless. Another basis is the data's self-report (median count in the domain 3 / maximum 3,377, so
    only a relative width can span two orders of magnitude). One-sided types expect the full complement — they are not
    two-sided, the "half" expectation does not apply, and forcing it only manufactures 294 false reds. The two-sided
    baseline uses (nL+nR)/2 rather than half of the type's total body count: M-side and side-less bodies enter no
    hemisphere, and mixing them into the baseline is error mode ①'s disease."""
    counts = load_counts()

    def pred(x):
        n0 = _side_expect(counts, x[0])
        return abs(counts[x] - n0) <= max(1, math.ceil(0.30 * n0))

    def point_pred(x):
        return counts[x] == _side_expect(counts, x[0])

    point_variant = Claim(
        name="P1 reading variant: point-value claim (n == n0, band collapsed to a point)",
        predicate=point_pred,
        applies=lambda x: True,
        domain_note="same domain and baseline as P1, but band width = 0",
        source=_ANNOT_SRC,
        quote=_fact("rule=n==n0; domain=annotation(type×somaSide); points=22176"),
        quote_source=_fact("rule=n==n0; domain=annotation(type×somaSide); points=22176"),
    )
    return Claim(
        name="P1 count band: side count within half of the two-sided total ±30%",
        predicate=pred,
        applies=lambda x: True,
        domain_note=("per (type, side) point: two-sided types expect n0=(nL+nR)//2, one-sided types expect "
                     "the full complement; band width max(1, ceil(0.30×n0))"),
        source=_ANNOT_SRC,
        quote=_fact("rule=|n-n0|<=max(1,ceil(0.30*n0)); "
                    "domain=annotation(type×somaSide); points=22176"),
        quote_source=_fact("rule=|n-n0|<=max(1,ceil(0.30*n0)); "
                           "domain=annotation(type×somaSide); points=22176"),
        source_tests=((("R1-R6", "R"), False),      # |9-6|=3 > 2: narrowing the band produces a readout
                      (("AMMC007", "R"), True),     # L=4/R=5: passes the band, fails point value (the discriminating point)
                      (("KCab-s", "L"), True)),     # |234-328|=94 ≤ 99: inside the band
        reading_variants=(point_variant,),
    )


def build_p2_claim():
    """P2 hemisphere symmetry band: |nL − nR| ≤ max(2, 10% of the two-sided complement).

    Strict equality is the wrong strength: most Drosophila hemisphere types mirror exactly (8,911 types with equal
    sides), but counting/allocation noise makes ±1–2 common; the types whose left and right counts truly differ
    inside the data (e.g. KCab-s |L−R|=189) are what the band should catch. KCab-s's difference is recomputable
    within the data and its cause awaits adjudication: pooled KCab* four subtypes L=885/R=925 near-symmetric while
    the subtypes are inversely unbalanced among themselves (s: R≫L; m/c: L≫R); FAFB KCab 844L/799R is symmetric and
    KC has no known asymmetric type — the subtyping/annotation-artifact explanation dominates. The band floor of 2
    absorbs small-sample counting noise; the 10% relative band lets a small proportional difference in a large type
    through. One-sided types = maximal asymmetry (R=0), and falling outside the band is a real readout, not a false
    red — the left-right difference account is meant to cover them."""
    counts = load_counts()

    def pred(x):
        nL, nR = counts.get((x[0], "L"), 0), counts.get((x[0], "R"), 0)
        return abs(nL - nR) <= max(2, math.ceil(0.10 * (nL + nR)))

    hard_equal_variant = Claim(
        name="P2 reading variant: left-right strict equality (band width 0)",
        predicate=lambda x: counts.get((x[0], "L"), 0)
        == counts.get((x[0], "R"), 0),
        applies=lambda x: True,
        domain_note="same domain as P2, but band width = 0",
        source=_ANNOT_SRC,
        quote=_fact("rule=nL==nR; domain=annotation(type×somaSide); points=22176"),
        quote_source=_fact("rule=nL==nR; domain=annotation(type×somaSide); points=22176"),
    )
    return Claim(
        name="P2 hemisphere symmetry band: |nL−nR| ≤ max(2, 10% two-sided complement)",
        predicate=pred,
        applies=lambda x: True,
        domain_note="per (type, side) point: the type's left-right count difference against the band",
        source=_ANNOT_SRC,
        quote=_fact("rule=|nL-nR|<=max(2,ceil(0.10*(nL+nR))); "
                    "domain=annotation(type×somaSide); points=22176"),
        quote_source=_fact("rule=|nL-nR|<=max(2,ceil(0.10*(nL+nR))); "
                           "domain=annotation(type×somaSide); points=22176"),
        source_tests=((("KCab-s", "L"), False),     # |234-423|=189 > 66: left-right unequal inside the data (cause to be adjudicated)
                      (("AL-AST1", "L"), True)),    # L=1/R=2: passes the band, fails strict equality (the discriminating point)
        reading_variants=(hard_equal_variant,),
    )


def build_p3_claim():
    """P3 transmitter composition band: the main transmitter (neuron-level vote) has share ≥ 0.5.

    A "main" transmitter has to cover more than half the members to deserve the word. The vote account = per-body
    votes on predicted_nt (unclear counts, a tie takes the lexicographically largest); the reading variant drops
    unclear from both the votes and the denominator — the two accounts disagree on 22 domain points (11 types × 2
    sides): all 20 points the main account flags false are rescued by the variant (FS4A acetylcholine 0.49→0.82,
    LHAV4a4 gaba 0.41→0.58), and the variant alone flags 2 points false (Pleural remotor/abductor MN: unclear 0.79
    passes the band, after dropping it histamine 1/3 — non-unclear votes split three ways). AVLP548_b goes both ways
    (unclear 1/3 vs glutamate 1/2 after dropping), evidence that "does unclear count as a vote" is not a small matter.
    A type with no transmitter row is not judged false (no evidence ≠ a violation).

    KCab-s is a reverse warning: on this table both accounts agree on dopamine (656/657), but KC is textbook
    cholinergic (VFB/FAFB explorer ACh@100%), and the official v1.0 curation layer's consensus_nt has already
    changed the whole KC line to acetylcholine — the `celltype_predicted_nt` read here is the model layer, so
    "votes = self-report" ≠ "= biology". When the model, curation, and textbook layers disagree, the outlier is the
    signal: a deeper layer of the account lesson."""
    fr = load_nt_fractions()

    def pred(x):
        v = fr.get(x[0])
        return True if v is None else v[1] >= 0.5

    no_unclear_variant = Claim(
        name="P3 reading variant: unclear neither votes nor counts in the denominator",
        predicate=lambda x: (lambda v: True if v is None else v[1] >= 0.5)(
            _fr_no_unclear().get(x[0])),
        applies=lambda x: True,
        domain_note="same domain as P3; unclear is dropped from both the vote count and the denominator",
        source=_NT_SRC,
        quote=_fact("rule=share_excl_unclear>=0.5; domain=annotation(type×somaSide); "
                    "points=22176"),
        quote_source=_fact("rule=share_excl_unclear>=0.5; domain=annotation(type×somaSide); "
                           "points=22176"),
    )
    return Claim(
        name="P3 composition band: voted main transmitter share ≥ 0.5",
        predicate=pred,
        applies=lambda x: True,
        domain_note="per (type, side) point: the type's voted main transmitter share against the lower band; a type with no transmitter row is not judged false",
        source=_NT_SRC,
        quote=_fact("rule=share>=0.5; domain=annotation(type×somaSide); points=22176"),
        quote_source=_fact("rule=share>=0.5; domain=annotation(type×somaSide); points=22176"),
        source_tests=((("KCab-s", "L"), True),      # dopamine 656/657 ≈ 0.9985
                      (("R1-R6", "L"), True),       # unclear 2627/3377 ≈ 0.7779
                      (("AVLP548_b", "L"), False)), # unclear 1/3 < 0.5: narrowing the band produces a readout
        reading_variants=(no_unclear_variant,),
    )


_NO_UNCLEAR = {}


def _fr_no_unclear():
    """{type: (top1, share)} for the unclear-dropped account — used by P3's reading variant.
    It uses the same raw votes as the main account, only a different counting rule: unclear neither votes nor enters
    the denominator, and predicted_nt=None gets the same treatment (None is not a vote)."""
    if _NO_UNCLEAR:
        return _NO_UNCLEAR
    _require_corpus()
    cols, _ = read_ipc_columns(NT_PATH, ("cell_type", "predicted_nt"))
    votes = {}
    nrows = {}
    for c, pn in zip(cols["cell_type"], cols["predicted_nt"]):
        if c is None or not str(c).strip():
            continue
        if pn is None or pn == "unclear":
            continue
        c = str(c)
        votes.setdefault(c, {}).setdefault(pn, 0)
        votes[c][pn] += 1
        nrows[c] = nrows.get(c, 0) + 1
    for c, cnt in votes.items():
        mx = max(cnt.values())
        top = sorted(k for k, v in cnt.items() if v == mx)
        _NO_UNCLEAR[c] = (top[-1], cnt[top[-1]] / nrows[c])
    return _NO_UNCLEAR


def build_claims():
    return [build_p1_claim(), build_p2_claim(), build_p3_claim(),
            build_q_claim()]


def run():
    claims = build_claims()
    return claims, compare_n(claims, domain_points(), chain=False)


def main():
    claims, r = run()
    counts = load_counts()
    pts = domain_points()
    one_sided = sum(1 for t in {t for t, _ in counts}
                    if (counts.get((t, "L"), 0) == 0)
                    != (counts.get((t, "R"), 0) == 0))

    print("=" * 78)
    print("MaleCNS v0.9 strength layer: bounded-account verdicts over type × hemisphere")
    print(f"corpus {FEATHER_ANNOT} + {FEATHER_NT}")
    print(f"accounts {len(claims)} (P1 count band / P2 symmetry band / P3 composition band / Q existence)")
    print("=" * 78)
    print(f"  comparison domain {r.total} points = annotation-table existence points (non-empty type × L/R × count>0)")
    print(f"  unique types {len(load_type_totals())}, {len(counts)} points in the domain, "
          f"one-sided types {one_sided}")

    print()
    print(f"{'account':<52}{'pass':>8}{'false red':>10}  verdict")
    print("-" * 78)
    for c in claims:
        fails = [x for x in pts if not c.predicate(x)]
        if c.name.startswith("Q"):
            verdict = "existence anchor (always true on the domain by design; read the other three)"
        elif not fails:
            verdict = "decorative band (zero readout)"
        elif len(fails) == len(pts):
            verdict = "rejects the whole dataset"
        else:
            w = ", ".join(f"{t}.{s}" for t, s in fails[:2])
            verdict = f"narrowed to a readout (witness {w}{'…' if len(fails) > 2 else ''})"
        print(f"  {c.name:<50}{len(pts) - len(fails):>8}{len(fails):>10}  {verdict}")

    print()
    print(render_n(claims, r))
    print()
    print("=" * 78)
    print("Readout conclusion")
    print("=" * 78)
    print(f"  parameter points {r.total} | all_true {r.all_true} / all_false {r.all_false} "
          f"/ split {r.split} / out_of_domain {r.out_of_domain}")
    for i, n in sorted(r.outliers.items()):
        print(f"  outlier → {r.names[i]} ({n} point(s) where it alone goes false)")
    print("  [No adjudication] outside the band ≠ bad data. An outlier only says \"this account does not hold at this point\";")
    print("          it is a list of left-right-unequal / mixed-transmitter types to send to human review, not an error report.")

    print()
    print("=" * 78)
    print("Counter-example: what a point-value claim looks like on the same data")
    print("=" * 78)
    import misaligned
    _c1, r1 = misaligned.wrong_1_point_value()
    band_fails = sum(1 for x in pts if not claims[0].predicate(x))
    print(f"  point-value claim (n = type total body count // 2): false red "
          f"{sum(r1.pioneers.values())}/{r1.total} points")
    print(f"  — on the same batch of real data, the P1 band flags only {band_fails} points false, "
          f"the point-value claim flags {sum(r1.pioneers.values())}.")
    print("     Pick the wrong strength shape and the readout goes from \"a handful of suspects\" to \"12% false alarms\".")


if __name__ == "__main__":
    main()

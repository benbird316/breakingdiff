"""Download the two malecns corpus feathers (GCS direct links, resumable), anchor SHA256 + row counts,
and generate/update corpus_manifest.json.

[Why this file exists]
The corpus is the public MaleCNS v0.9 release from Janelia flyem (about 56 MB, kept out of the repository by
.gitignore), and every readout in the case rests on it. Anyone who copies this directory runs this script once and
gets a corpus identical to this case's — the ledger (manifest) records measured facts,
but the ledger cannot replace re-running, and the re-download path must stay open.

★ Download-set discipline: the tbar-level transmitter table (tbar-neurotransmitters-…feather, 2.7 GB)
is optional advanced corpus for account 1 and is barred from the default — the default set is exactly the two
feathers; better to have less than to add noise, and a missing item is registered in the manifest with its impact.

★ Hash-anchor lesson: hashing while the download is still running captures an incomplete state (the first probe run
recorded one false anchor). This script accepts a download as complete only when "byte count matches + chunked
SHA256 matches" both hold; on a verification failure it keeps the .part for resuming and exits explicitly.

How to run:
    python fetch_corpus.py            # download (resumable) + verify + update the ledger
    python fetch_corpus.py --manifest # do not download; rescan the existing corpus and update the ledger
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request

# The Windows console defaults to GBK and the report uses glyphs outside that code
# page. Switch to UTF-8 and downgrade unencodable characters so the script cannot
# die with UnicodeEncodeError while printing its own warning.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(_HERE, "corpus_manifest.json")

GCS_BASE = ("https://storage.googleapis.com/flyem-male-cns/v0.9/"
            "connectome-data/flat-connectome/")
FEATHER_ANNOT = "body-annotations-male-cns-v0.9-minconf-0.5.feather"
FEATHER_NT = "body-neurotransmitters-male-cns-v0.9.feather"
# ★ The default download set is exactly the two feathers; the tbar-level 2.7 GB table is barred (fetch it yourself for the advanced account).
DEFAULT_TARGETS = (FEATHER_ANNOT, FEATHER_NT)

# Anchors: chunked (4 MB) SHA256 measured on this machine on 2026-10-20; they reconcile with the frozen values in
# test_aligned.py; a static release's hash does not change.
PINS = {
    FEATHER_ANNOT: {
        "sha256": "03cca8d1e667353f75f7674fb7d6b3a9e22e5b04b089865127407a5c38816cda",
        "bytes": 12900778,
    },
    FEATHER_NT: {
        "sha256": "93f436ed5ac29787c485907ba1aa2ca85213929a485466c46da034cd676fbbeb",
        "bytes": 43403618,
    },
}


def sha256_file(path):
    """Chunked (4 MB) SHA256 (same parameters as the test side's independent implementation; the two are each other's reconciliation)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(name, dst):
    """Single-file download: write to .part, resume with Range, then rename atomically.
    Verification failure → exit explicitly without delivering a false anchor: a short file keeps the .part for
    resuming; full length but a SHA mismatch means content corruption, so delete the .part and re-download (resuming cannot save it)."""
    pin = PINS[name]
    url = GCS_BASE + name
    part = dst + ".part"
    done = os.path.getsize(part) if os.path.exists(part) else 0
    if done == pin["bytes"]:
        # The .part has exactly the full length: verify the SHA first — accept it if right, delete it if wrong.
        # A full-length bad .part cannot be resumed (Range: bytes=N- hits a 416 deadlock).
        if sha256_file(part) == pin["sha256"]:
            os.replace(part, dst)
            print(f"    ✓ .part is complete and verified, accepting it directly: {name}")
            return dst
        os.remove(part)
        done = 0
        print(f"    .part had full length but the SHA did not match; deleted, re-downloading from scratch: {name}")
    elif done > pin["bytes"]:
        os.remove(part)
        done = 0
    if done:
        print(f"    resuming from {done / 1e6:.1f} MB: {name}")
    else:
        print(f"    downloading (about {pin['bytes'] / 1e6:.0f} MB): {name}")
        print(f"      {url}")
    req = urllib.request.Request(url, headers=({"Range": f"bytes={done}-"}
                                               if done else {}))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if done and r.status != 206:
                print("    the server does not support Range; re-downloading from scratch")
                done = 0
            with open(part, "ab" if done else "wb") as f:
                total = done
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
                    print(f"\r      received {total / 1e6:6.1f} / "
                          f"{pin['bytes'] / 1e6:.1f} MB", end="", flush=True)
    except Exception as e:
        print(f"\n    [FATAL] download failed: {e}")
        print(f"    .part kept ({os.path.getsize(part) if os.path.exists(part) else 0} bytes); "
              f"rerun this script to resume automatically, or download it manually and put it at:\n      {dst}")
        raise SystemExit(1)
    print()
    if os.path.getsize(part) != pin["bytes"]:
        raise SystemExit(
            f"[FATAL] {name} byte count mismatch: got {os.path.getsize(part)}, "
            f"anchor {pin['bytes']}. Download incomplete; .part kept for resuming.")
    got = sha256_file(part)
    if got != pin["sha256"]:
        # Reaching here means the byte count already matches the anchor: a SHA mismatch = content corruption.
        # Resuming cannot help, and keeping the .part only makes the rerun hit a 416 deadlock — delete it and re-download.
        os.remove(part)
        raise SystemExit(
            f"[FATAL] {name} verification failed; delete .part and re-download (it was removed for you):\n"
            f"       byte count matches the anchor ({pin['bytes']}) but the SHA256 does not — "
            f"got {got}, anchor {pin['sha256']}.\n"
            f"       Content corruption cannot be fixed by resuming; if it keeps failing, "
            f"check whether a network middlebox is rewriting it.")
    os.replace(part, dst)
    print(f"    ✓ verified (SHA256 + byte count): {name}")
    return dst


def fetch_all():
    for name in DEFAULT_TARGETS:
        dst = os.path.join(_HERE, name)
        if (os.path.isfile(dst) and os.path.getsize(dst) == PINS[name]["bytes"]
                and sha256_file(dst) == PINS[name]["sha256"]):
            print(f"  already in place, skipping: {name}")
            continue
        download(name, dst)


def _readings():
    """The readout table: everything comes from aligned's measured readout, cell by cell into the ledger (in-repo anchor)."""
    sys.path.insert(0, _HERE)
    import aligned
    counts = aligned.load_counts()
    totals = aligned.load_type_totals()
    fr = aligned.load_nt_fractions()

    types_lr = {t for (t, _s) in counts}
    one_sided = {t for t in types_lr
                 if (counts.get((t, "L"), 0) == 0)
                 != (counts.get((t, "R"), 0) == 0)}
    asym = {t for t in types_lr
            if counts.get((t, "L"), 0) > 0 and counts.get((t, "R"), 0) > 0
            and counts[(t, "L")] != counts[(t, "R")]}
    w1 = sum(1 for (t, _s) in counts if counts[(t, _s)] != totals[t] // 2)
    w2 = 0
    for (t, s) in counts:
        other = counts.get((t, "R" if s == "L" else "L"), 0)
        if counts[(t, s)] != other:
            w2 += 1
    w3 = sum(1 for (t, _s) in counts
             if t in fr and fr[t][0] != fr[t][2])
    mx = max(asym, key=lambda t: (abs(counts[(t, "L")] - counts[(t, "R")]), t))
    return {
        "domain_size": len(counts),
        "types": len(types_lr),
        "one_sided_types": len(one_sided),
        "asym_two_sided_types": len(asym),
        "wrong1_fail": w1,
        "wrong2_fail": w2,
        "wrong3_fail": w3,
        "vote_vs_celltype_types": sum(1 for v in fr.values() if v[0] != v[2]),
        "vote_share_subhalf_types": sum(1 for v in fr.values() if v[1] < 0.5),
        "max_asym_type": mx,
        "max_asym_left": counts[(mx, "L")],
        "max_asym_right": counts[(mx, "R")],
        "max_asym": abs(counts[(mx, "L")] - counts[(mx, "R")]),
    }


def refresh_manifest():
    """Rescan the corpus on disk: measure hash/byte count/row count item by item, recompute the whole readout table,
    and overwrite the ledger. Items missing from the corpus go into missing, with state = PARTIAL."""
    sys.path.insert(0, _HERE)
    import aligned

    files = {}
    missing = []
    for name in DEFAULT_TARGETS:
        path = os.path.join(_HERE, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            missing.append(name)
            continue
        got_sha = sha256_file(path)
        if got_sha != PINS[name]["sha256"]:
            print(f"  [WARN] {name} SHA256 does not match the anchor (got {got_sha}); "
                  f"recording it as missing; delete it and rerun fetch_corpus.py to re-download")
            missing.append(name)
            continue
        files[name] = {
            "sha256": got_sha,
            "bytes": os.path.getsize(path),
            "rows": aligned.ipc_row_count(path),
        }

    readings = {}
    if not missing:
        readings = _readings()
    # ★ When the corpus is missing/mismatched, a rescan would overwrite the in-repo COMPLETE anchor (measured
    #   hash/row counts/readout table) with a PARTIAL empty table — the readout table evaporates, the test's readings
    #   assertions all turn red, and nothing says "the anchor was destroyed by ourselves". Better to refuse the write
    #   than to degrade silently.
    if missing and os.path.isfile(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            prev = json.load(f)
        if prev.get("corpus_status", {}).get("state") == "COMPLETE":
            raise SystemExit(
                "[FATAL] refusing to overwrite corpus_manifest.json: the in-repo ledger is the COMPLETE anchor "
                "(measured hash/row counts/readout table of both feathers), and this rescan found missing or "
                f"mismatched items: {', '.join(missing)}.\n"
                "       Writing it down would destroy the anchor (PARTIAL empty table, readings cleared), "
                "and readers without the corpus would lose their only reconciliation stand-in.\n"
                "       Restore the corpus and rerun (python fetch_corpus.py); "
                "to really downgrade the ledger, delete this file manually and rerun.")
    status = {
        "_about": "An honest record of the corpus state. The case's readout was measured in this state.",
        "state": "COMPLETE" if not missing else "PARTIAL",
        "missing": missing,
        "impact": ("when the corpus is missing, every corpus-derived readout (domain facts, three bands, three error "
                   "modes) cannot be recomputed and only the readings anchor can be reconciled against; whichever "
                   "feather is missing, that side's (annotation/transmitter) accounts fail as a whole"),
        "how": "python fetch_corpus.py (GCS direct link, resumable; anchors in PINS)",
    }
    man = {
        "_about": ("malecns corpus ledger: measured anchors for the two feathers + the aggregate readout table. "
                   "The raw corpus does not enter the repository (.gitignore); this file is its in-repo stand-in."),
        "_why_this_file_exists": ("the readout table must let someone without the corpus check consistency, "
                                  "but checking consistency is not verification — re-running the probes still needs a re-download."),
        "_generated_by": "fetch_corpus.py (rescans the corpus on disk and overwrites this file)",
        "corpus_status": status,
        "files": files,
        "readings": readings,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  ✓ updated {os.path.basename(MANIFEST)}"
          f" (state={status['state']}"
          f"{'; missing ' + ', '.join(missing) if missing else ''})")
    return status


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Download the two malecns corpus feathers and maintain the ledger")
    ap.add_argument("--manifest", action="store_true",
                    help="do not download; only rescan the existing corpus and update the ledger")
    args = ap.parse_args(argv)

    if not args.manifest:
        print("=" * 74)
        print("MaleCNS v0.9 corpus fetch: two feathers (GCS public direct links)")
        print("=" * 74)
        fetch_all()
    refresh_manifest()
    if os.path.isfile(os.path.join(_HERE, FEATHER_ANNOT)):
        print()
        print("  Next steps:")
        print(f"    cd {os.path.basename(_HERE)}")
        print("    python aligned.py")
        print("    python misaligned.py")
        print("    python test_aligned.py   # should be all green")


if __name__ == "__main__":
    main()

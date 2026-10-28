"""Download and unpack the three official llama.cpp builds this case needs (corpus fetching, not committed to git).

[Why this file exists]
This case's corpus is three official binaries, about 2.1 GB unpacked — too big for git
and impossible to distribute with the repository. So "data included" can only work one way here:
**bundle the way to fetch it, not the data itself**.
Anyone who copies this directory runs this script once and gets a corpus identical to this case's.

Compare pdg/fetch_data.py: that corpus is only 7.6 MB but it is **pinned** to PDG 2024
(the 2024/2025 official URLs now return 404), so that script only verifies/recovers and
never downloads. Here it is 2.1 GB, several assets, and unpacking, so asset names and
exact bytes/SHA256 are pinned in `asset_pins` in corpus_manifest.json and every download
is verified item by item.

How to run:
    python fetch_corpus.py            # download and unpack the three builds into ./llama-b<tag>/
    python fetch_corpus.py --root D:/somewhere   # download elsewhere
    python fetch_corpus.py --asset cpu          # use the cpu build (about 17.3–18.7 MiB each; readout unverified)
    python fetch_corpus.py --links              # print the asset URLs/bytes/SHA256 only; no download, no write
    python fetch_corpus.py --manifest          # ★ corpus present: rescan and update the artifact-side ledger

★ The full asset list and manual download steps are in DOWNLOAD.md beside this script;
  `--links` is the executable printout of the same list.
★ The corpus is in gitignore, but **the ledger is not** —
  corpus_manifest.json records measured artifact facts, so readout consistency can be checked even without the corpus.
  But it **cannot replace re-running the probes**: only a run against the real binaries counts as verification.
★ Download verification: every zip is checked against its exact bytes + SHA256 before it is
  unpacked; a mismatch refuses to unpack and deletes the bad file. An existing file is
  verified too — a half-downloaded zip must not continue into extraction.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request
import zipfile

# The Windows console defaults to GBK and the report uses glyphs outside that code
# page. Switch to UTF-8 and downgrade unencodable characters so the script cannot
# die with UnicodeEncodeError while printing its own warning.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(_HERE, "corpus_manifest.json")

TAGS = ("b10472", "b10595", "b11681")
REPO = "ggml-org/llama.cpp"


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def _pin_entry(tag):
    """Take one build's asset pins from the ledger. ★ The ledger is the only source;
    the script never assembles a name or guesses a size itself."""
    pins = load_manifest()["asset_pins"]
    if tag not in pins:
        raise SystemExit(
            f"[FATAL] the ledger has no asset record for {tag}.\n"
            f"       Recorded: {sorted(k for k in pins if not k.startswith('_'))}\n"
            f"       If the build number changed, add an entry under asset_pins in "
            f"{os.path.basename(MANIFEST)} first.")
    return pins[tag]


def asset_spec(tag, kind):
    """Return (asset name, exact bytes, SHA256) for one build and asset kind.

    ★ The ledger is the only source; the script never assembles a name itself —
    measured: b10472/b10595 are cuda-13.3 while b11681 is cuda-13.4, the minor
    version changes over time, and hard-coding it points at a missing asset.
    ★ Bytes and SHA256 come from the same GitHub asset metadata; if either is
    absent the download is refused, otherwise a half-downloaded zip would be
    unpacked as if it were complete.
    """
    entry = _pin_entry(tag)
    if kind == "cuda":
        spec = {
            "asset": entry.get("used_asset"),
            "bytes": entry.get("used_asset_bytes"),
            "sha256": entry.get("used_asset_sha256"),
        }
    elif kind in ("cpu", "cuda-12.4"):
        alt = entry.get("alternatives", {}).get(kind, {})
        spec = {
            "asset": alt.get("asset"),
            "bytes": alt.get("bytes"),
            "sha256": alt.get("sha256"),
        }
    else:
        raise SystemExit(f"unknown asset type: {kind}")
    missing = [k for k in ("asset", "bytes", "sha256") if not spec.get(k)]
    if missing:
        raise SystemExit(
            f"[FATAL] asset pins for {tag}/{kind} lack {missing}; refusing to download "
            f"an asset without an anchor.\n"
            f"       Add them under asset_pins in {os.path.basename(MANIFEST)}.")
    return spec


def asset_name(tag, kind):
    """Backwards-compatible accessor: the asset file name for one build/kind."""
    return asset_spec(tag, kind)["asset"]


def asset_url(tag, spec):
    return (f"https://github.com/{REPO}/releases/download/"
            f"{tag}/{spec['asset']}")


def print_links():
    """--links: print URLs/bytes/SHA256 for the three asset categories.

    Reads only the manifest — no download, no corpus scan, no manifest write.
    The asset list is same-source as DOWNLOAD.md (both come from asset_pins in
    corpus_manifest.json), so the doc table and this printout match item by item.
    """
    titles = (
        ("cuda", "used / cuda-13.x (default; this case's original readout was measured on these three)"),
        ("cpu", "cpu (smaller; readout unverified)"),
        ("cuda-12.4", "cuda-12.4 (alternative runtime; not used for the readout)"),
    )
    print("llama.cpp corpus asset list (read-only: no download, no file writes)")
    print(f"source: asset_pins in {os.path.basename(MANIFEST)}")
    used_total = 0
    for kind, title in titles:
        print()
        print(f"[{title}]")
        for tag in TAGS:
            spec = asset_spec(tag, kind)
            print(f"  {tag}  {spec['asset']}")
            print(f"    bytes  {spec['bytes']:,}")
            print(f"    sha256 {spec['sha256']}")
            print(f"    url    {asset_url(tag, spec)}")
            if kind == "cuda":
                used_total += spec["bytes"]
    print()
    print(f"used total: {used_total:,} bytes"
          f" (about {used_total / 1048576:.1f} MiB / {used_total / 1e6:.1f} MB)")
    print("about 2.1 GB unpacked. Manual download and verification steps are in DOWNLOAD.md.")


def verify_asset(path, expected_bytes, expected_sha256):
    """Pure function: verify a downloaded file by bytes + SHA256 -> (ok, explanation).

    Decoupled from download so tests never need the network. ★ A size check alone
    is not enough: an interrupted zip usually does not add up to the right size,
    but a zip with swapped bad bytes can have exactly the same size.
    """
    if not os.path.exists(path):
        return False, "file does not exist"
    size = os.path.getsize(path)
    if size != expected_bytes:
        return False, (f"byte count mismatch: got {size:,}, expected {expected_bytes:,}"
                       f" (difference {expected_bytes - size:+,})")
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != str(expected_sha256).lower():
        return False, f"SHA256 mismatch: got {actual}, expected {expected_sha256}"
    return True, f"bytes {size:,} and SHA256 match"


def download(url, dst, spec):
    """Download one zip and **verify it before handing it to extraction**.

    - Existing file: verified first; on mismatch it is deleted and downloaded again
      (a half zip must not stay around).
    - Downloading: written to .part, then checked against bytes + SHA256, then
      atomically renamed.
    ★ No third-party library — this repository has to run after being copied
    elsewhere, so fewer dependencies is better.
    """
    expected_bytes = spec["bytes"]
    expected_sha256 = spec["sha256"]
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        ok, why = verify_asset(dst, expected_bytes, expected_sha256)
        if ok:
            print(f"    already present and verified, skipping download: {os.path.basename(dst)}"
                  f" ({expected_bytes:,} bytes)")
            return dst
        print(f"    already present but verification failed ({why}); deleting and re-downloading.")
        os.remove(dst)

    part = dst + ".part"
    if os.path.exists(part):
        os.remove(part)
    print(f"    downloading (about {expected_bytes / 1e6:.0f} MB; verified against bytes + SHA256 afterwards):")
    print(f"      {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
                print(f"\r      received {total / 1e6:6.1f} MB", end="", flush=True)
    except Exception as e:
        if os.path.exists(part):
            os.remove(part)
        print(f"\n    [FATAL] download failed: {e}")
        print(f"    If the network is restricted, download it manually, put it in this directory, and rerun:\n      {url}")
        raise SystemExit(1)
    print()
    ok, why = verify_asset(part, expected_bytes, expected_sha256)
    if not ok:
        os.remove(part)
        print(f"    [FATAL] download finished but the integrity check failed: {why}")
        print(f"    Deleted the bad file {os.path.basename(part)}; rerun this script.")
        print(f"    Ledger expectations: {expected_bytes:,} bytes / {expected_sha256}")
        raise SystemExit(1)
    os.replace(part, dst)
    print(f"    done and verified: {os.path.basename(dst)} ({expected_bytes:,} bytes)")
    return dst


def extract(zip_path, root, tag):
    """Unpack into <root>/llama-<tag>/; skip if it is already there."""
    target = os.path.join(root, f"llama-{tag}")
    if os.path.isdir(target):
        print(f"    already unpacked, skipping: {target}")
        return target
    print(f"    unpacking… ({os.path.getsize(zip_path) / 1e6:.0f} MB, please wait)")
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(root)
    except zipfile.BadZipFile:
        print(f"    [FATAL] {zip_path} is not a valid zip — most likely the download was interrupted.")
        print(f"    Delete that file and rerun: {zip_path}")
        raise SystemExit(1)
    if not os.path.isdir(target):
        print(f"    [WARN] unpacking finished but {target} was not found; "
              f"check whether the zip's directory layout matches the expectation.")
    else:
        print(f"    done: {target}")
    return target


def fetch_one(tag, root, kind, dl_dir):
    spec = asset_spec(tag, kind)
    name = spec["asset"]
    url = asset_url(tag, spec)
    os.makedirs(dl_dir, exist_ok=True)
    zp = download(url, os.path.join(dl_dir, name), spec)
    extract(zp, root, tag)
    return target_dir_ok(root, tag)


def target_dir_ok(root, tag):
    d = os.path.join(root, f"llama-{tag}")
    if not os.path.isdir(d):
        return False
    # ★ The criterion cannot be just "does the directory exist": an interrupted unpack leaves half a directory.
    #   At minimum the files the probes check must be recognized.
    need = ("llama-server-impl.dll",)
    return all(os.path.exists(os.path.join(d, f)) for f in need)


def verify_all(root):
    """All three builds must be present. ★ Exit explicitly when one is missing —
    with only one build left, this case's core conclusion (cross-version) cannot be re-run,
    and the tool will not tell you that; it just hands you a readout with a parameter missing."""
    missing = [t for t in TAGS if not target_dir_ok(root, t)]
    if not missing:
        print(f"  ✓ all three builds present: {', '.join(TAGS)}")
        return True
    # Diagnostics go to stderr: tests call this as a pure function (only the return value matters);
    # printing to stdout would mix into the test report, and pipe buffering would drift it after the summary, looking like a failure.
    print(f"  [FATAL] incomplete corpus, missing: {', '.join(missing)}", file=sys.stderr)
    if len(os.listdir(root)) and len(missing) < len(TAGS):
        print(file=sys.stderr)
        print("  ★ Note: this case's core conclusion is **cross-version** —", file=sys.stderr)
        print("    template-analysis is present in b10472/b10595 and missing in b11681.", file=sys.stderr)
        print("    With only one build left, that comparison cannot be re-run,", file=sys.stderr)
        print("    and the readout only shows 'fewer comparison points'; it does not raise an error.", file=sys.stderr)
        print("    So missing builds must be restored first, before any readout is discussed.", file=sys.stderr)
    print(file=sys.stderr)
    print(f"  To restore: python {os.path.basename(__file__)} --root <path>", file=sys.stderr)
    return False


def refresh_manifest(root):
    """★ Corpus present: rescan the real builds and write the measured values back into the ledger.

    This keeps the ledger from becoming "a record that never changes and may be out of date".
    """
    import aligned
    aligned.LLAMA_ROOT = root

    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)

    for tag in TAGS:
        if not target_dir_ok(root, tag):
            continue
        rec = man["builds"].get(tag, {})
        rec["on_disk"] = True
        probes = {}
        v = {}
        ok, note = aligned.probe_slots_n_diff(tag)
        probes["C1_server_has_SLOTS_N_DIFF"] = {"value": ok, "note": note}
        v["C1"] = ok
        ok, note = aligned.probe_mellum(tag)
        probes["C2_mellum_present"] = {"value": ok, "note": note}
        v["C2"] = ok
        ok, note = aligned.probe_template_analysis(tag)
        probes["C3_template_analysis_present"] = {"value": ok, "note": note}
        v["C3"] = ok
        rec["probes"] = probes
        rec["verdict_vector"] = v

        d = os.path.join(root, f"llama-{tag}")
        stub = os.path.join(d, "llama-server.exe")
        impl = os.path.join(d, "llama-server-impl.dll")
        if os.path.exists(stub) and os.path.exists(impl):
            rec["key_file_sizes"] = {
                "_about": "★ Sizes are recorded to pin the 'stub vs impl' trap",
                "llama-server.exe": os.path.getsize(stub),
                "llama-server-impl.dll": os.path.getsize(impl),
            }
        man["builds"][tag] = rec

    present = [t for t in TAGS if target_dir_ok(root, t)]
    missing = [t for t in TAGS if t not in present]
    man["corpus_status"]["present"] = present
    man["corpus_status"]["missing"] = missing
    man["corpus_status"]["state"] = "COMPLETE" if not missing else "PARTIAL"

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  ✓ updated {os.path.basename(MANIFEST)}"
          f" (present={present or 'none'})")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Download and unpack the three official nightly builds this case needs")
    ap.add_argument("--root", default=None,
                    help="root directory to unpack into (default: this script's directory)")
    ap.add_argument("--asset", choices=("cuda", "cpu"), default="cuda",
                    help="cuda=match this case's original readout (about 150 MB each); "
                         "cpu=8 times smaller (about 17.3–18.7 MiB), "
                         "but nobody has verified that the probe readout is the same")
    ap.add_argument("--keep-zips", action="store_true",
                    help="keep the downloaded zips (also kept by default; see the note below)")
    ap.add_argument("--links", action="store_true",
                    help="print the URLs/bytes/SHA256 of the used/cpu/cuda-12.4 assets only; "
                         "no download, no corpus scan (manifest only), no ledger write "
                         "(the same list is in DOWNLOAD.md)")
    ap.add_argument("--manifest", action="store_true",
                    help="do not download; only rescan the existing corpus and update the artifact-side ledger")
    args = ap.parse_args(argv)

    if args.links:
        print_links()
        return

    root = os.path.abspath(args.root or _HERE)

    if args.manifest:
        print("rescanning the corpus and updating the ledger…")
        if not os.path.isdir(root):
            raise SystemExit(f"[FATAL] corpus root does not exist: {root}")
        refresh_manifest(root)
        return

    print("=" * 74)
    print("llama.cpp corpus fetch: three official nightly builds")
    print("=" * 74)
    print(f"  corpus root: {root}")
    print(f"  asset type: {args.asset}"
          + (" (matches this case's original readout)" if args.asset == "cuda"
             else " (★ smaller, but readout equivalence is unverified, about 17.3–18.7 MiB each)"))
    print(f"  asset names / bytes / SHA256 come from asset_pins in {os.path.basename(MANIFEST)},")
    print(f"  not assembled in the script — measured: b10472/b10595 are cuda-13.3,")
    print(f"b11681 is cuda-13.4, and the minor version changes over time. Every download is verified.")

    already = all(target_dir_ok(root, t) for t in TAGS)
    if already:
        print()
        print("  All three builds are in place; skipping download.")
        refresh_manifest(root)
        verify_all(root)
        return

    dl_dir = os.path.join(root, "downloads")
    for tag in TAGS:
        print()
        print(f"[{tag}]")
        fetch_one(tag, root, args.asset, dl_dir)

    print()
    print("=" * 74)
    if verify_all(root):
        print()
        print("  Next steps:")
        print(f"    cd {root}")
        print("    python aligned.py")
        print("    python test_aligned.py    # should be all green")
        print()
        print("  ★ If you used --asset cpu, first check whether the readout matches")
        print("    what TEACHING-llama.md §3 records; a mismatch means the")
        print("    cpu build trimmed the relevant symbols, and you should rerun with the cuda build.")


if __name__ == "__main__":
    main()

"""Download and unpack the three official llama.cpp builds this case needs (corpus fetching, not committed to git).

[Why this file exists]
This case's corpus is three official binaries, about 2.1 GB unpacked — too big for git
and impossible to distribute with the repository. So "data included" can only work one way here:
**bundle the way to fetch it, not the data itself**.
Anyone who copies this directory runs this script once and gets a corpus identical to this case's.

Compare pdg/fetch_data.py: that one is a 7.6 MB sqlite file with a stable official URL,
so downloading it directly is enough. Here it is 2.1 GB, multiple assets, and needs unpacking,
so asset-name pinning and an integrity check were added.

How to run:
    python fetch_corpus.py            # download and unpack the three builds into ./llama-b<tag>/
    python fetch_corpus.py --root D:/somewhere   # download elsewhere
    python fetch_corpus.py --asset cpu          # use the cpu build (18 MB each)
    python fetch_corpus.py --manifest          # ★ corpus present: rescan and update the artifact-side ledger

★ The corpus is in gitignore, but **the ledger is not** —
  corpus_manifest.json records measured artifact facts, so readout consistency can be checked even without the corpus.
  But it **cannot replace re-running the probes**: only a run against the real binaries counts as verification.
"""
import argparse
import json
import os
import sys
import urllib.request
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(_HERE, "corpus_manifest.json")

TAGS = ("b10472", "b10595", "b11681")
REPO = "ggml-org/llama.cpp"


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def asset_name(tag, kind):
    """Take the asset name from the ledger. ★ The ledger is the only source; the script never assembles a name itself —
    measured: b10472/b10595 are cuda-13.3 while b11681 is cuda-13.4;
    the minor version changes over time, and hard-coding it points at an asset that does not exist."""
    pins = load_manifest()["asset_pins"]
    if tag not in pins:
        raise SystemExit(
            f"[FATAL] no asset record for {tag} in the ledger.\n"
            f"       Recorded: {sorted(k for k in pins if not k.startswith('_'))}\n"
            f"       If the build number changed, add an entry under asset_pins in "
            f"{os.path.basename(MANIFEST)} first.")
    entry = pins[tag]
    if kind == "cuda":
        return entry["used_asset"], entry
    if kind == "cpu":
        return entry["alternatives"]["cpu"], entry
    raise SystemExit(f"unknown asset type: {kind}")


def download(url, dst, expect_mb=None):
    """Download one zip. ★ No third-party library —
    this repository has to run after being copied elsewhere, so fewer dependencies is better."""
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print(f"    already present, skipping download: {os.path.basename(dst)}"
              f" ({os.path.getsize(dst) / 1e6:.0f} MB)")
        return dst
    size_hint = f", about {expect_mb} MB" if expect_mb else ""
    print(f"    downloading{size_hint}: {os.path.basename(dst)}")
    print(f"      {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dst, "wb") as f:
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
                print(f"\r      received {total / 1e6:6.1f} MB", end="", flush=True)
    except Exception as e:
        print(f"\n    [FATAL] download failed: {e}")
        print(f"    If the network is restricted, download it manually, put it in this directory, and rerun:\n      {url}")
        raise SystemExit(1)
    print()
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
    name, entry = asset_name(tag, kind)
    url = (f"https://github.com/{REPO}/releases/download/"
           f"{tag}/{name}")
    expect_mb = entry.get("used_asset_size_mb") or 20
    if kind == "cpu":
        expect_mb = int(str(entry["alternatives"]["cpu"]).split("(")[1]
                        .split("MB")[0])
    os.makedirs(dl_dir, exist_ok=True)
    zp = download(url, os.path.join(dl_dir, name), expect_mb)
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
                         "cpu=8 times smaller (about 18 MB), "
                         "but nobody has verified that the probe readout is the same")
    ap.add_argument("--keep-zips", action="store_true",
                    help="keep the downloaded zips (also kept by default; see the note below)")
    ap.add_argument("--manifest", action="store_true",
                    help="do not download; only rescan the existing corpus and update the artifact-side ledger")
    args = ap.parse_args(argv)

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
             else " (★ smaller, but readout equivalence is unverified)"))
    print(f"  asset names come from asset_pins in {os.path.basename(MANIFEST)},")
    print(f"  not assembled in the script — measured: b10472/b10595 are cuda-13.3,")
    print(f"b11681 is cuda-13.4, and the minor version changes over time.")

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

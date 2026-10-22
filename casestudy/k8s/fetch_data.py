# -*- coding: utf-8 -*-
"""Fetch the two official Kubernetes OpenAPI specs this case compares.

Corpus: `api/openapi-spec/swagger.json` from two release tags of the
kubernetes/kubernetes repository, unmodified. Two real snapshots, nothing
self-authored.

Why a fetch script at all: 6.2 MB of third-party corpus does not go into git
(`casestudy/.gitignore` excludes it). The SHA256 of both files is pinned in
`corpus_manifest.json`; a reader can verify a re-download without trusting this
file.

★ A fetch path that has rotted, recorded rather than papered over
--------------------------------------------------------------------------
Measured 2026-10-21: the jsDelivr path works for release-1.28 (HTTP 200, full
2,955,128 bytes) but returns **HTTP 403 for release-1.31**, with the body:

    Package size exceeded the configured limit of 50 MB. Try
    https://github.com/kubernetes/kubernetes/tree/release-1.31/... instead.

Two things worth keeping from that:

  1. The failure is **not** "the network is down". It is a CDN policy — 50 MB per
     package — applied at pack time. release-1.28 only succeeds because a cached
     package already exists; release-1.31 has never been packed, so the request
     has to build it and hits the limit. **A path that worked for one asset and
     fails for the next is not flaky, it is order-dependent.**
  2. The 403 body points at a **GitHub HTML tree page**, not a raw file. Anyone
     who follows that hint verbatim saves HTML into a `.json` slot. The SHA256
     check below is the only thing that catches it mechanically — a size check
     or a "does it start with `{`" check would not, because a GitHub error page
     is also text.

This is the same failure class as llama's missing builds, one level worse:
llama lost the data, this lost the road to the data.

Usage:
    python fetch_data.py                # download + verify both
    python fetch_data.py --manifest     # rescan and rewrite corpus_manifest.json
    python fetch_data.py --check        # verify on-disk SHA256 only, no network
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))

# SHA256 measured on 2026-10-21 from the files this case was developed against.
# A re-download that does not hash to these is not this corpus.
ASSETS = {
    "k8s-1.28.json": {
        "sha256": "44ff3c98bb011964585019e1765b0c09ee65d503e4c35cbda355df6a02486c86",
        "size": 2955128,
        "candidates": [
            ("jsdelivr", "https://cdn.jsdelivr.net/gh/kubernetes/kubernetes@release-1.28/api/openapi-spec/swagger.json"),
            ("github-raw", "https://raw.githubusercontent.com/kubernetes/kubernetes/release-1.28/api/openapi-spec/swagger.json"),
        ],
    },
    "k8s-1.31.json": {
        "sha256": "ddcb3d5c3d85849f1fadb56387d3a7bf44712da291e5bd08b34df4e8a4247f8d",
        "size": 3277085,
        "candidates": [
            # ★ measured 2026-10-21: this one returns 403 (50 MB package limit).
            # Kept first anyway because that is the order a reader will try, and
            # because the 403 is itself part of what this case teaches. The
            # fallback below is what actually works.
            ("jsdelivr", "https://cdn.jsdelivr.net/gh/kubernetes/kubernetes@release-1.31/api/openapi-spec/swagger.json"),
            ("github-raw", "https://raw.githubusercontent.com/kubernetes/kubernetes/release-1.31/api/openapi-spec/swagger.json"),
            ("statically", "https://cdn.statically.io/gh/kubernetes/kubernetes/release-1.31/api/openapi-spec/swagger.json"),
        ],
    },
}

MANIFEST = os.path.join(HERE, "corpus_manifest.json")

PROXY_HINT = (
    "github-raw / statically measured unreachable from this network (curl exit 000). "
    "Per this project's rules, non-domestic sources need the local proxy first: "
    "start %APPDATA%\\FlClash\\FlClash.exe, then re-run."
)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "breakingdiff-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def acquire(name, spec, allow_network=True):
    """Try every mirror in order; keep the first one whose bytes hash correctly.

    Verifying the hash before writing is the whole point: it is the only check
    that rejects an HTML error page saved under a .json name.
    """
    dest = os.path.join(HERE, name)
    attempts = []
    for label, url in spec["candidates"]:
        if not allow_network:
            break
        try:
            blob = _fetch(url)
        except urllib.error.HTTPError as e:
            detail = e.read(200).decode("utf-8", "replace").strip().replace("\n", " ")
            attempts.append(f"{label}: HTTP {e.code} {e.reason} — {detail}")
            continue
        except Exception as e:  # noqa: BLE001 — every failure mode must be reported, not swallowed
            attempts.append(f"{label}: {type(e).__name__}: {e}")
            continue
        got = hashlib.sha256(blob).hexdigest()
        if got != spec["sha256"]:
            attempts.append(
                f"{label}: hash mismatch — got {got[:16]}…, expected {spec['sha256'][:16]}… "
                f"({len(blob)} bytes; this is usually an HTML error page, not JSON)"
            )
            continue
        with open(dest, "wb") as f:
            f.write(blob)
        return True, attempts + [f"{label}: OK {len(blob)} bytes, sha256 verified"]
    return False, attempts


def write_manifest():
    """Record artifact-side facts so a reader without the corpus can check the readout.

    Following llama's discipline: the manifest is a **measured record**, not the
    evidence. It cannot replace re-running `aligned.py`; it only lets a reader
    confirm that what they see matches what was recorded.
    """
    on_disk = {}
    for name, spec in ASSETS.items():
        path = os.path.join(HERE, name)
        present = os.path.isfile(path)
        on_disk[name] = {
            "sha256": spec["sha256"],
            "size_bytes": spec["size"],
            "on_disk": present,
            "sha256_reverified": _sha256(path) == spec["sha256"] if present else None,
        }
    missing = [n for n, v in on_disk.items() if not v["on_disk"]]
    manifest = {
        "_about": (
            "Artifact-side ledger for the two Kubernetes OpenAPI snapshots. "
            "Companion to the case's teaching file."
        ),
        "_honesty_boundary": (
            "This file is a measured record, not the evidence. It lets a reader check "
            "that the readout they see matches what was recorded; it cannot replace "
            "re-running aligned.py. If you can re-fetch, re-fetch."
        ),
        "_generated_by": "fetch_data.py --manifest",
        "asset_pins": {
            name: {
                "sha256": spec["sha256"],
                "size_bytes": spec["size"],
                "mirrors_tried_in_order": [label for label, _ in spec["candidates"]],
            }
            for name, spec in ASSETS.items()
        },
        "corpus_status": {
            "state": "PRESENT" if not missing else "PARTIAL",
            "present": [n for n, v in on_disk.items() if v["on_disk"]],
            "missing": missing,
            "impact": (
                "★ **The removal finding cannot be re-run when either file is absent** — it "
                "is a cross-version comparison (present in 1.28 → absent in 1.31); with one "
                "side only, the existence account loses its comparison object and the "
                "four quadrants degrade to all-true. A missing corpus is not 'zero findings', "
                "it is 'no conclusion'."
            ) if missing else (
                "Both snapshots present and hash-verified; the four-quadrant readout in "
                "TEACHING-k8s.md can be re-run as written."
            ),
            "recoverable": True,
            "how": "python fetch_data.py (SHA256-pinned; see the 403 note below)",
            "known_broken_path": (
                "jsDelivr returns **HTTP 403 for release-1.31** ('Package size exceeded the "
                "configured limit of 50 MB') while release-1.28 succeeds from cache. This is "
                "a CDN package-size policy, not an outage, and the 403 body points at a "
                "GitHub **HTML tree page** — following it verbatim saves HTML into a .json "
                "slot. The SHA256 check is what catches that."
            ),
            "_why_record_this": (
                "Same discipline as llama's missing builds: a corpus problem must be "
                "recorded, not worked around — and it must name **which conclusion dies**, "
                "not merely that data is gone."
            ),
        },
        "files": on_disk,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", action="store_true",
                    help="rescan on-disk files and rewrite corpus_manifest.json")
    ap.add_argument("--check", action="store_true",
                    help="verify on-disk SHA256 only, no network access")
    args = ap.parse_args()

    if args.manifest:
        m = write_manifest()
        print(f"corpus_manifest.json rewritten, state = {m['corpus_status']['state']}")
        return 0

    ok_all = True
    for name, spec in ASSETS.items():
        print(f"--- {name} ---")
        if args.check:
            path = os.path.join(HERE, name)
            if not os.path.isfile(path):
                print(f"  MISSING  {path}")
                ok_all = False
                continue
            got = _sha256(path)
            good = got == spec["sha256"]
            print(f"  {'OK  ' if good else 'BAD '} sha256 {got}")
            if not good:
                print(f"       expected {spec['sha256']}")
                ok_all = False
            continue
        ok, attempts = acquire(name, spec)
        for line in attempts:
            print(f"  {line}")
        if not ok:
            ok_all = False
            print(f"  -> {name} NOT acquired. Every mirror failed; see the attempts above.")
            print(f"     {PROXY_HINT}")
    print()
    print("all assets verified" if ok_all else
          "★ NOT all assets verified — with either file absent, "
          "`aligned.py` cannot produce the cross-version conclusion.")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())

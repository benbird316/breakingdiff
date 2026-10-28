"""Verify (or recover) the PDG 2024 sqlite this case is pinned to — this is not a downloader.

[Why a verifier and not a downloader]
Every assertion and every teaching readout in this case was measured against the
**PDG 2024** sqlite: edition=2024 / schema_version=0.2 / 18,064 pdgdata rows, with
the SHA256 pinned below. The upstream online edition is now 2026 (edition=2026 /
schema=0.3 / 19,587 pdgdata rows / about 25.75 MB). That is **not a newer snapshot
of the same corpus**: it is a different corpus. Silently swapping the data would
change the readouts while the scripts keep raising nothing — exactly the kind of
failure this case is about, except here it would corrupt the case itself.

So this script **never downloads by default**: if the file is present it verifies
the pinned 2024 identity, and if it is absent it prints the exact recovery steps
and exits non-zero. Migrating to 2026 is a future work item; it has to change the
assertions and the teaching readouts together, which a fetch script cannot decide
on its own.

[Facts pinned here] (measured 2026-10-28)
    edition          2024
    citation         S. Navas et al. (Particle Data Group),
                     Phys. Rev. D 110, 030001 (2024)
    schema_version   0.2
    pdgdata rows     18,064
    file size        7,593,984 bytes (about 7.59 MB / 7.24 MiB)
    SHA256           a925777f... (see PINNED_SHA256)

Usage:
    python fetch_data.py                  # verify ./pdg.sqlite
    python fetch_data.py --path <file>    # verify a copy somewhere else

Exit code: 0 = matches the pinned identity; 1 = missing or mismatched (the reason
and the recovery steps are printed).
"""
import argparse
import hashlib
import os
import sqlite3
import sys

# The Windows console defaults to GBK, and report markers such as the star and
# warning glyphs are outside the GBK code page. Switch to UTF-8 and downgrade
# unencodable characters, otherwise this script dies with UnicodeEncodeError at
# the exact moment it is trying to report a warning.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(_HERE, "pdg.sqlite")

# ---- The pinned corpus identity. Changing this means changing the corpus, and
# ---- the assertions and teaching readouts have to change with it.
PINNED_EDITION = "2024"
PINNED_CITATION = ("S. Navas et al. (Particle Data Group), "
                   "Phys. Rev. D 110, 030001 (2024)")
PINNED_SCHEMA_VERSION = "0.2"
PINNED_PDGDATA_ROWS = 18064
PINNED_BYTES = 7593984
PINNED_SHA256 = ("a925777fd0066bce4a90752959c07a87d3834a8d68f39a53ba8cd38d22fd532e")

# Measured differences of the 2026 edition. Recorded only to explain why this
# case does not migrate; these values never participate in a download.
UNPINNED_2026 = {
    "edition": "2026",
    "schema_version": "0.3",
    "pdgdata_rows": 19587,
    "bytes_mb": 25.75,
}


class PinError(RuntimeError):
    """The corpus does not match the PDG 2024 identity this case is pinned to."""


def sha256_file(path):
    """Hash a file in fixed-size chunks (7.6 MB is small enough; no third-party library)."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_meta(path):
    """Read the pdginfo table into a dict. Failure means 'this is not the PDG sqlite'."""
    con = sqlite3.connect(path)
    try:
        rows = con.execute("SELECT name, value FROM pdginfo").fetchall()
    except sqlite3.DatabaseError as e:
        raise PinError(
            f"cannot read the pdginfo table; this is not the PDG sqlite: {path}\n"
            f"  underlying error: {e}")
    finally:
        con.close()
    return {name: value for name, value in rows}


def count_pdgdata_rows(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM pdgdata").fetchone()[0]
    except sqlite3.DatabaseError as e:
        raise PinError(
            f"cannot read the pdgdata table; this is not the PDG sqlite: {path}\n"
            f"  underlying error: {e}")
    finally:
        con.close()


def _mismatch(field, actual, pinned, why):
    return PinError(
        f"{field} mismatch: got {actual!r}, this case pins {pinned!r}.\n"
        f"  {why}")


def verify_sqlite(path=DST, *, check_sha256=True):
    """Check that one pdg.sqlite is the pinned PDG 2024 corpus.

    Structure first (edition / schema / citation / rows), then size and SHA256.
    The order is deliberate: it makes "a different edition was swapped in" and
    "one byte of this file was changed" report different reasons.

    Returns a dict of measured facts; any mismatch raises PinError (never silently
    accepted).
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise PinError(
            f"corpus missing or empty: {path}\n"
            f"  This case pins PDG {PINNED_EDITION} and will not download a substitute edition.")

    meta = read_meta(path)
    edition = meta.get("edition")
    schema = meta.get("schema_version")
    citation = meta.get("citation")

    if edition != PINNED_EDITION:
        raise _mismatch(
            "edition", edition, PINNED_EDITION,
            "this case's assertions and readouts were measured on PDG 2024; "
            "switching edition silently changes the readout. The 2026 migration is a "
            "future item and must change the assertions too.")
    if schema != PINNED_SCHEMA_VERSION:
        raise _mismatch(
            "schema_version", schema, PINNED_SCHEMA_VERSION,
            "a schema change means table layout or field semantics may have changed; "
            "the extraction has to be re-verified.")
    if citation != PINNED_CITATION:
        raise _mismatch(
            "citation", citation, PINNED_CITATION,
            "the citation is this corpus's identity anchor; a different citation is a "
            "different compilation.")

    rows = count_pdgdata_rows(path)
    if rows != PINNED_PDGDATA_ROWS:
        raise _mismatch(
            "pdgdata row count", rows, PINNED_PDGDATA_ROWS,
            "a different row count means the corpus content changed; the readout is "
            "not directly comparable to the old assertions.")

    size = os.path.getsize(path)
    facts = {
        "path": path,
        "bytes": size,
        "edition": edition,
        "schema_version": schema,
        "citation": citation,
        "pdgdata_rows": rows,
    }

    if check_sha256:
        if size != PINNED_BYTES:
            raise _mismatch(
                "file size in bytes", size, PINNED_BYTES,
                "a different size means the file was modified or is not the same corpus.")
        digest = sha256_file(path)
        facts["sha256"] = digest
        if digest != PINNED_SHA256:
            raise _mismatch(
                "SHA256", digest, PINNED_SHA256,
                "the file content does not match the pinned PDG 2024 corpus.")
    return facts


def recovery_text(path=DST):
    """Recovery steps when the file is absent. ★ It must say how to recover and why
    this script will not download a substitute edition."""
    return (
        f"This case pins the PDG {PINNED_EDITION} sqlite, but the verifier never "
        f"downloads a substitute edition.\n"
        f"\n"
        f"Missing file: {path}\n"
        f"\n"
        f"Recovery steps:\n"
        f"  1) The file is committed with the repository (a clone already contains it).\n"
        f"     From the repository root run:\n"
        f"       git restore casestudy/pdg/pdg.sqlite\n"
        f"     If you have another copy, you can also copy pdg.sqlite into "
        f"{os.path.dirname(path)}.\n"
        f"  2) After restoring, verify it (this script is the verifier):\n"
        f"         python fetch_data.py\n"
        f"  3) The anchors checked (four structural facts plus size and SHA256; any "
        f"mismatch is an error):\n"
        f"       edition={PINNED_EDITION}\n"
        f"       citation={PINNED_CITATION}\n"
        f"       schema_version={PINNED_SCHEMA_VERSION}\n"
        f"       pdgdata={PINNED_PDGDATA_ROWS:,} rows\n"
        f"       bytes={PINNED_BYTES:,}\n"
        f"       sha256={PINNED_SHA256}\n"
        f"\n"
        f"Why not download online: the official URLs for 2024/2025 now return 404 "
        f"(measured 2026-10-28),\n"
        f"and the only online edition is 2026, which is different data "
        f"(edition=2026 / schema {UNPINNED_2026['schema_version']} / "
        f"{UNPINNED_2026['pdgdata_rows']:,} rows / about {UNPINNED_2026['bytes_mb']} MB).\n"
        f"Silently substituting it would swap the case's conclusions for another "
        f"corpus's conclusions.\n"
    )


def _format_ok(facts):
    return (
        f"OK: pdg.sqlite matches the PDG {PINNED_EDITION} identity this case pins\n"
        f"  edition        {facts['edition']}\n"
        f"  citation       {facts['citation']}\n"
        f"  schema_version {facts['schema_version']}\n"
        f"  pdgdata        {facts['pdgdata_rows']:,} rows\n"
        f"  bytes          {facts['bytes']:,}"
        f" ({facts['bytes'] / 1e6:.2f} MB / {facts['bytes'] / 1048576:.2f} MiB)\n"
        f"  SHA256         {facts.get('sha256', '(not checked in this mode)')}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="verify that pdg.sqlite matches the PDG 2024 identity this case "
                    "pins (no download: the 2026 edition is incompatible with the "
                    "assertions)")
    ap.add_argument("--path", default=DST,
                    help="sqlite file to verify (default: pdg.sqlite beside this script)")
    args = ap.parse_args(argv)
    path = os.path.abspath(args.path)

    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print(recovery_text(path))
        sys.exit(1)

    try:
        facts = verify_sqlite(path)
    except PinError as e:
        print(f"[FATAL] corpus does not match the pinned identity; refusing to use it.\n\n{e}\n",
              file=sys.stderr)
        print("Recovery steps:\n", file=sys.stderr)
        print(recovery_text(path), file=sys.stderr)
        sys.exit(1)

    print(_format_ok(facts))


if __name__ == "__main__":
    main()

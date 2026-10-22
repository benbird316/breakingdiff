"""Download the PDG sqlite data file (not committed to git; see .gitignore).

Measured: https://pdg.lbl.gov/2026/api/pdg-2026.0.sqlite is about 7.6 MB, but the LBL
server responds very slowly (it may take several minutes). Be patient; it is not hung.
"""
import os
import sys

URL = "https://pdg.lbl.gov/2026/api/pdg-2026.0.sqlite"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdg.sqlite")


def main() -> None:
    if os.path.exists(DST):
        print(f"Already exists, skipping: {DST} ({os.path.getsize(DST) / 1e6:.1f} MB)")
        return
    print(f"Downloading (the server is slow; this may take several minutes)…\n  {URL}")
    rc = os.system(f'curl -L --retry 3 -o "{DST}" "{URL}"')
    if rc != 0 or not os.path.exists(DST):
        print("Download failed. You can download it manually and put it in this directory as pdg.sqlite.")
        sys.exit(1)
    print(f"Done: {DST} ({os.path.getsize(DST) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

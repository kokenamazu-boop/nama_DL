#!/usr/bin/env python3
"""Build the nama_DL distribution ZIP.

Usage:
    python tools/package.py [--skip-tests] [--out DIR]

What it does:
  1. Checks that every place that carries the version number agrees
     with extension/manifest.json (fails before building anything).
  2. Checks that the fixed extension ID in Setup.ps1 matches the
     public key embedded in extension/manifest.json.
  3. Runs the test suites (unless --skip-tests is given) and fails
     if any test was skipped: a suite that did not really run (for
     example the media tests without ffmpeg on PATH) must not ship.
  4. Packs ONLY the whitelisted distribution files into
     nama_DL-Windows-v<version>.zip under a top-level nama_DL/ folder,
     then verifies the ZIP contents against the whitelist and writes
     a .sha256.txt file next to it.
"""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files that make up the distribution. Anything not listed here never
# enters the ZIP (tests, tools, downloads, work files, ...).
WHITELIST = [
    "README.md",
    "LICENSE",
    "START_HERE.html",
    "はじめに.txt",
    "更新内容.txt",
    "Setup.cmd",
    "Setup.ps1",
    "ApplyUpdate.cmd",
    "ApplyUpdate.ps1",
    "CheckSetup.cmd",
    "CheckSetup.ps1",
    "Update.cmd",
    "Uninstall.cmd",
    "ConvertToMP4.cmd",
    "ConvertToMP4.ps1",
    "extension/manifest.json",
    "extension/page.js",
    "extension/popup.html",
    "extension/popup.js",
    "extension/queue-ui.js",
    "extension/edit-options.js",
    "extension/sites.js",
    "extension/report.js",
    "extension/update-check.js",
    "extension/style.css",
    "extension/icons/nama_DL.png",
    "host/host.py",
    "host/pick_folder.ps1",
]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def extension_id_from_key(key_b64):
    der = base64.b64decode(key_b64)
    digest = hashlib.sha256(der).digest()
    return "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 15)) for b in digest[:16])


def check_versions():
    manifest = json.loads(read("extension/manifest.json"))
    version = manifest["version"]
    problems = []

    def expect(label, found):
        if found != version:
            problems.append(f"{label}: found {found!r}, expected {version!r}")

    m = re.search(r"const VERSION='([0-9.]+)'", read("extension/worker.js"))
    expect("extension/worker.js VERSION", m.group(1) if m else None)

    m = re.search(r"get\('action'\)=='hello':send\('hello','',version='([0-9]+\.[0-9]+\.[0-9]+)'\)", read("host/host.py"))
    expect("host/host.py hello version", m.group(1) if m else None)

    m = re.search(r"拡張機能 ([0-9.]+) /", read("extension/popup.js"))
    expect("extension/popup.js display", m.group(1) if m else None)

    m = re.search(r"拡張機能 ([0-9.]+) /", read("extension/popup.html"))
    expect("extension/popup.html display", m.group(1) if m else None)

    m = re.search(r"Host updated to v([0-9]+\.[0-9]+\.[0-9]+)", read("ApplyUpdate.ps1"))
    expect("ApplyUpdate.ps1 message", m.group(1) if m else None)

    readme = read("README.md")
    m = re.search(r"\*\*現在のバージョン：([0-9.]+)\*\*", readme)
    expect("README.md version", m.group(1) if m else None)
    if f"nama_DL-Windows-v{version}.zip" not in readme:
        problems.append("README.md: distribution ZIP name does not match the version")
    if f"/releases/download/v{version}/" not in readme:
        problems.append("README.md: download link is not the GitHub Releases URL for this version")

    start = read("START_HERE.html")
    if f"v{version} ·" not in start:
        problems.append("START_HERE.html: header version does not match")
    if f"nama_DL-Windows-v{version}.zip" not in start:
        problems.append("START_HERE.html: distribution ZIP name does not match the version")

    hajime = read("はじめに.txt")
    if not hajime.startswith(f"nama_DL v{version}"):
        problems.append("はじめに.txt: first line version does not match")
    if f"nama_DL-Windows-v{version}.zip" not in hajime:
        problems.append("はじめに.txt: distribution ZIP name does not match the version")

    updates = read("更新内容.txt")
    if f"v{version}" not in updates[:200]:
        problems.append("更新内容.txt: no entry for this version near the top")

    m = re.search(r"assertEqual\(self\.read\(\)\['version'\],'([0-9.]+)'\)", read("tests/test_queue_protocol.py"))
    expect("tests/test_queue_protocol.py hello version", m.group(1) if m else None)

    # Fixed extension ID: manifest key <-> Setup.ps1 constant.
    key = manifest.get("key")
    if not key:
        problems.append("extension/manifest.json: no fixed 'key' (extension ID is not fixed)")
    else:
        derived = extension_id_from_key(key)
        m = re.search(r"\$fixedExtensionId = '([a-p]{32})'", read("Setup.ps1"))
        if not m:
            problems.append("Setup.ps1: $fixedExtensionId not found")
        elif m.group(1) != derived:
            problems.append(
                f"Setup.ps1: fixed ID {m.group(1)} does not match manifest key ID {derived}"
            )
        m = re.search(r"\$fixedExtensionId = '([a-p]{32})'", read("ApplyUpdate.ps1"))
        if not m:
            problems.append("ApplyUpdate.ps1: $fixedExtensionId not found")
        elif m.group(1) != derived:
            problems.append("ApplyUpdate.ps1: fixed ID does not match manifest key ID")

    return version, problems


def run_tests():
    commands = [
        [sys.executable, "-m", "unittest",
         "tests.test_processing", "tests.test_partial_download",
         "tests.test_queue_protocol", "tests.test_x_download"],
        ["node", "--test", "tests/queue.test.cjs", "tests/x-support.test.cjs",
         "tests/report.test.cjs", "tests/update-check.test.cjs"],
    ]
    for cmd in commands:
        print("+", " ".join(cmd))
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        print(result.stdout, end="")
        if result.returncode != 0:
            return False
        # A suite that "passes" with skipped tests did not really run.
        # The media tests skip themselves when ffmpeg/ffprobe are not on
        # PATH, which must never silently ship in a distribution build.
        m = re.search(r"skipped=([0-9]+)", result.stdout)
        if m and int(m.group(1)) > 0:
            print(f"Test run had {m.group(1)} SKIPPED test(s). "
                  "The media tests need ffmpeg and ffprobe on PATH; "
                  "without them the suite did not really run.")
            return False
    return True


def build(version, out_dir):
    missing = [rel for rel in WHITELIST if not (ROOT / rel).is_file()]
    if missing:
        print("Missing distribution files:")
        for rel in missing:
            print("  -", rel)
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"nama_DL-Windows-v{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in sorted(WHITELIST):
            info = zipfile.ZipInfo(f"nama_DL/{rel}", date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            zf.writestr(info, (ROOT / rel).read_bytes())
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(zf.namelist())
    expected = sorted(f"nama_DL/{rel}" for rel in WHITELIST)
    if names != expected:
        print("ZIP contents do not match the whitelist.")
        print("  unexpected:", sorted(set(names) - set(expected)))
        print("  missing   :", sorted(set(expected) - set(names)))
        return None
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path = out_dir / (zip_path.name + ".sha256.txt")
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    return zip_path, sha_path, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "dist"))
    args = parser.parse_args()

    version, problems = check_versions()
    if problems:
        print(f"Version/ID check FAILED for v{version}:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"Version/ID check OK: v{version}")

    if not args.skip_tests:
        if not run_tests():
            print("Tests FAILED. ZIP was not built.")
            return 1
        print("Tests OK.")

    built = build(version, Path(args.out))
    if built is None:
        return 1
    zip_path, sha_path, digest = built
    print(f"Built: {zip_path}")
    print(f"SHA-256: {digest}")
    print(f"Written: {sha_path}")
    print("Next step: create the GitHub Release v" + version +
          " and upload the ZIP and the .sha256.txt as release assets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

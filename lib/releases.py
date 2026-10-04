"""List installable release assets, or select the latest stable matching a prefix."""

import argparse
import json
import re
import subprocess
import sys


API = "https://api.github.com/repos/espressif/esp-idf/releases"
VERSION = re.compile(r"esp-idf-v(\d+\.\d+(?:\.\d+)?(?:-[A-Za-z0-9.-]+)?)\.zip")


def fetch_versions():
    versions = set()
    stable = set()
    page = 1
    while True:
        response = subprocess.run(
            ["curl", "-fsSL", "--retry", "3", "--connect-timeout", "20",
             f"{API}?per_page=100&page={page}"],
            check=True, stdout=subprocess.PIPE, text=True,
        )
        releases = json.loads(response.stdout)
        if not isinstance(releases, list):
            raise ValueError("expected a release list from GitHub")
        for release in releases:
            if release.get("draft"):
                continue
            for asset in release.get("assets", []):
                match = VERSION.fullmatch(asset.get("name", ""))
                if match:
                    version = match.group(1)
                    versions.add(version)
                    if "-" not in version and not release.get("prerelease"):
                        stable.add(version)
        if len(releases) < 100:
            return versions, stable
        page += 1


def version_key(version):
    main, _, suffix = version.partition("-")
    numbers = tuple(int(part) for part in main.split("."))
    numbers = (numbers + (0, 0, 0))[:3]
    # Compare digit runs numerically (rc2 precedes rc10); stable follows prerelease.
    suffix_key = tuple((1, int(part)) if part.isdigit() else (0, part)
                       for part in re.split(r"(\d+)", suffix))
    return numbers, not suffix, suffix_key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest", metavar="PREFIX")
    args = parser.parse_args()
    try:
        versions, stable = fetch_versions()
    except (subprocess.CalledProcessError, ValueError) as error:
        print(f"asdf-esp-idf: release discovery failed: {error}", file=sys.stderr)
        return 1
    if args.latest is not None:
        matches = [version for version in stable if version.startswith(args.latest)]
        if not matches:
            print(f"asdf-esp-idf: no stable release matches {args.latest!r}", file=sys.stderr)
            return 1
        print(max(matches, key=version_key))
    else:
        print(" ".join(sorted(versions, key=version_key)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

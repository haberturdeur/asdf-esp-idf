#!/usr/bin/env bash

set -euo pipefail

GH_REPO="espressif/esp-idf"
GH_RELEASES_API="https://api.github.com/repos/${GH_REPO}/releases"
GH_RELEASES_URL="https://github.com/${GH_REPO}/releases"

fail() {
  printf 'asdf-esp-idf: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

normalize_version() {
  local version="$1"
  version="${version#v}"
  printf '%s\n' "$version"
}

tag_for_version() {
  local version
  version="$(normalize_version "$1")"
  printf 'v%s\n' "$version"
}

asset_name_for_version() {
  local tag
  tag="$(tag_for_version "$1")"
  printf 'esp-idf-%s.zip\n' "$tag"
}

asset_url_for_version() {
  local tag asset
  tag="$(tag_for_version "$1")"
  asset="$(asset_name_for_version "$1")"
  printf 'https://github.com/%s/releases/download/%s/%s\n' "$GH_REPO" "$tag" "$asset"
}

fetch_release_tags() {
  require_cmd curl
  require_cmd python3
  # GitHub's generated "Source code" archives are intentionally ignored: they do
  # not include submodules. Release assets named esp-idf-vX.Y.Z.zip do include
  # submodules and are the only versions listed here.
  curl -fsSL "$GH_RELEASES_API?per_page=100" | python3 -c '
import json
import re
import sys

releases = json.load(sys.stdin)
versions = set()
for release in releases:
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        match = re.fullmatch(r"esp-idf-v(.+)\.zip", name)
        if match:
            versions.add(match.group(1))

def key(version):
    main, _, suffix = version.partition("-")
    nums = [int(part) for part in main.split(".") if part.isdigit()]
    nums = (nums + [0, 0, 0])[:3]
    # Stable releases sort after prereleases for the same numeric version.
    stable_rank = 1 if not suffix else 0
    return (*nums, stable_rank, suffix)

for version in sorted(versions, key=key, reverse=True):
    print(version)
'
}

latest_stable() {
  fetch_release_tags | grep -Ev '(^|[-.])(rc|alpha|beta|preview|dev)([0-9.-]|$)' | head -n 1
}

strip_single_root_dir() {
  local src="$1" dst="$2"
  shopt -s dotglob nullglob
  local entries=("$src"/*)
  if [ "${#entries[@]}" -eq 1 ] && [ -d "${entries[0]}" ]; then
    cp -a "${entries[0]}/." "$dst/"
  else
    cp -a "$src/." "$dst/"
  fi
}

download_and_extract() {
  local version="$1" dest="$2"
  require_cmd curl
  require_cmd unzip

  local url archive tmp
  url="$(asset_url_for_version "$version")"
  archive="$dest/$(asset_name_for_version "$version")"
  tmp="$dest/.extract"

  mkdir -p "$dest"
  rm -rf "$tmp"
  mkdir -p "$tmp"

  printf 'Downloading %s\n' "$url" >&2
  curl -fL --retry 3 --connect-timeout 20 -o "$archive" "$url"

  printf 'Extracting %s\n' "$archive" >&2
  unzip -q "$archive" -d "$tmp"
  rm -f "$archive"

  strip_single_root_dir "$tmp" "$dest"
  rm -rf "$tmp"
}

#!/usr/bin/env bash

set -euo pipefail

GH_REPO="espressif/esp-idf"

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
  python3 "$(dirname "${BASH_SOURCE[0]}")/releases.py" "$@"
}

latest_stable() {
  fetch_release_tags --latest "${1:-}"
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

download_and_extract() (
  # A subshell keeps cleanup traps independent of the install hook's traps.
  local version="$1" dest="${2%/}"
  require_cmd curl
  require_cmd unzip
  [ -n "$dest" ] || fail "download path must not be the filesystem root"

  local url archive tmp
  url="$(asset_url_for_version "$version")"
  mkdir -p "$(dirname "$dest")"
  tmp="$(mktemp -d "${dest}.tmp.XXXXXX")"
  trap 'rm -rf "$tmp"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  archive="$tmp/archive.zip"
  mkdir -p "$tmp/extract" "$tmp/source"

  printf 'Downloading %s\n' "$url" >&2
  curl -fL --retry 3 --connect-timeout 20 -o "$archive" "$url"

  printf 'Extracting %s\n' "$archive" >&2
  unzip -q "$archive" -d "$tmp/extract"
  strip_single_root_dir "$tmp/extract" "$tmp/source"

  # Publish only a complete extraction, without overwriting existing downloads.
  if [ -d "$dest" ]; then
    rmdir "$dest" || fail "download directory must be empty: $dest"
  elif [ -e "$dest" ]; then
    fail "download path already exists: $dest"
  fi
  mv "$tmp/source" "$dest"
)

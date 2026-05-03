#!/usr/bin/env bash
# Fetch python-build-standalone interpreters for noted's multi-Python venv
# support. Stashed under data/python-builds/ so noted's Dockerfile can install
# without any network call (Launchpad-independent + Astral-S3-independent).
#
# Source: https://github.com/astral-sh/python-build-standalone/releases
# These are the same install_only tarballs uv would fetch on demand; we
# pin them locally so the build is reproducible byte-for-byte and air-gapped.
#
# Usage:
#   bash scripts/fetch-python-builds.sh
#
# Versions selected match noted's existing Dockerfile multi-Python set.
# Re-run with the upgraded version list whenever bumping.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/data/python-builds"
mkdir -p "$OUTPUT_DIR"

# Standard install_only versions (regular GIL-enabled builds)
VERSIONS=("3.10" "3.11" "3.12" "3.13" "3.14")
# Freethreaded variants (GIL-free / nogil) — only available for 3.13+
FT_VERSIONS=("3.13" "3.14")

TRIPLE="x86_64-unknown-linux-gnu"
RELEASES_API="https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"

echo ">>> Querying latest python-build-standalone release..."
LATEST_JSON=$(curl -sfL "$RELEASES_API")
TAG=$(echo "$LATEST_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")
echo "    Release tag: $TAG"

# Extract asset name + URL pairs from the release JSON. Using the unencoded
# `name` field for pattern matching (the URL is %2B-encoded for `+` and our
# regex uses literal `+`).
ASSETS=$(echo "$LATEST_JSON" | python3 -c "
import sys, json
for a in json.load(sys.stdin)['assets']:
    print(a['name'] + '\t' + a['browser_download_url'])
")

download_one() {
  local pattern="$1"
  local label="$2"
  local line url fname
  line=$(echo "$ASSETS" | python3 -c "
import sys, re
pat = re.compile(r'$pattern')
for ln in sys.stdin:
    name, url = ln.rstrip('\n').split('\t', 1)
    if pat.fullmatch(name):
        print(ln.rstrip('\n'))
        break
" || true)
  if [ -z "$line" ]; then
    echo "    WARN: no asset matching pattern: $pattern  ($label)"
    return 0
  fi
  fname="${line%%$'\t'*}"
  url="${line##*$'\t'}"
  if [ -f "$OUTPUT_DIR/$fname" ]; then
    echo "    SKIP existing: $fname"
    return 0
  fi
  echo "    GET $fname"
  curl -fLo "$OUTPUT_DIR/$fname.partial" "$url"
  mv "$OUTPUT_DIR/$fname.partial" "$OUTPUT_DIR/$fname"
}

echo ">>> Downloading regular (GIL) interpreters..."
for v in "${VERSIONS[@]}"; do
  # python-build-standalone names: cpython-3.X.Y+YYYYMMDD-x86_64-unknown-linux-gnu-install_only.tar.gz
  download_one "cpython-${v}\.[0-9]+\+[0-9]+-${TRIPLE}-install_only(_stripped)?\.tar\.gz" "$v"
done

echo ">>> Downloading freethreaded (nogil) interpreters..."
for v in "${FT_VERSIONS[@]}"; do
  # Freethreaded names: cpython-3.Xt+...   OR   cpython-3.X.Y+...freethreaded...
  # Newer releases tag freethreaded as a separate variant in the filename.
  download_one "cpython-${v}\.[0-9]+\+[0-9]+-${TRIPLE}-freethreaded.*install_only(_stripped)?\.tar\.gz" "${v}t"
done

echo
echo ">>> Done. Tarballs in $OUTPUT_DIR:"
ls -la "$OUTPUT_DIR" | grep -E "\.tar\.gz$" | awk '{printf "  %s  %.1f MB\n", $9, $5/1024/1024}'

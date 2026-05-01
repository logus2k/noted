#!/usr/bin/env bash
# Builds the CodeMirror ESM bundle for the noted frontend.
# Run this whenever CodeMirror packages need to be updated or new exports added.
#
# Usage:
#   cd scripts/build-codemirror
#   ./build.sh
#
# Output: frontend/vendor/codemirror/codemirror.bundle.js

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/../../frontend/vendor/codemirror/codemirror.bundle.js"

cd "$SCRIPT_DIR"

echo "Installing packages..."
npm install

# Ensure esbuild binary is executable (can lose +x across filesystems)
find node_modules/@esbuild -name esbuild -type f 2>/dev/null | xargs -r chmod +x

echo "Bundling..."
npm run build

echo "Done → $OUT"

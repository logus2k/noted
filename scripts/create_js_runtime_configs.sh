#!/usr/bin/env bash
# Generate data/runtimes/javascript/{version}/runtime.json for each Node.js
# version installed via fnm.
# Runs at container startup (called from entrypoint.sh).
set -euo pipefail

RUNTIMES_DIR="${1:-/app/data/runtimes}"
FNM_DIR="${FNM_DIR:-/root/.local/share/fnm}"

# fnm must be available
if [ ! -x "${FNM_DIR}/fnm" ]; then
    echo "fnm not found at ${FNM_DIR}/fnm - skipping JavaScript runtime config generation."
    exit 0
fi

# Activate fnm so we can query installed versions
eval "$("${FNM_DIR}/fnm" env)"

# Resolve pnpm path (symlinked to /usr/local/bin during Docker build)
PNPM_BIN="/usr/local/bin/pnpm"
if [ ! -x "$PNPM_BIN" ]; then
    PNPM_BIN=$(command -v pnpm 2>/dev/null || true)
fi
if [ -z "$PNPM_BIN" ] || [ ! -x "$PNPM_BIN" ]; then
    echo "pnpm not found - skipping JavaScript runtime config generation."
    exit 0
fi

# Discover installed Node.js versions
# fnm stores versions in $FNM_DIR/node-versions/v{version}/installation/
NODE_VERSIONS_DIR="${FNM_DIR}/node-versions"
if [ ! -d "$NODE_VERSIONS_DIR" ]; then
    echo "No Node.js versions installed - skipping JavaScript runtime config generation."
    exit 0
fi

for version_dir in "$NODE_VERSIONS_DIR"/v*; do
    [ -d "$version_dir" ] || continue

    node_bin="${version_dir}/installation/bin/node"
    [ -x "$node_bin" ] || continue

    full_version=$(basename "$version_dir" | sed 's/^v//')
    major_version=$(echo "$full_version" | cut -d. -f1)

    dir="$RUNTIMES_DIR/javascript/$major_version"
    mkdir -p "$dir"

    cat > "$dir/runtime.json" <<RTEOF
{
  "language": "javascript",
  "version": "$major_version",
  "display_name": "Node.js $major_version",
  "executable": "$node_bin",
  "env_create_cmd": ["mkdir", "-p", "{env_path}"],
  "env_post_create_cmds": [
    ["cp", "-n", "/app/data/templates/javascript/package.json", "{env_path}/package.json"],
    ["$PNPM_BIN", "install", "--dir", "{env_path}"]
  ],
  "kernel_cmd": [
    "{env_path}/node_modules/.bin/ijskernel",
    "--protocol=5.1",
    "{connection_file}"
  ],
  "kernel_language": "javascript",
  "package_manager": {
    "list_cmd": ["$PNPM_BIN", "list", "--json", "--dir", "{env_path}"],
    "install_cmd": ["$PNPM_BIN", "add", "--dir", "{env_path}"],
    "remove_cmd": ["$PNPM_BIN", "remove", "--dir", "{env_path}"]
  }
}
RTEOF

    echo "Created runtime config: javascript/$major_version (Node.js $full_version) -> $node_bin"
done

echo "JavaScript runtime config generation complete."

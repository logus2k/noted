#!/usr/bin/env bash
# Generate data/runtimes/{language}/{version}/runtime.json for each installed Python.
# Runs at Docker build time. Detects all python3.X executables in /usr/bin.
set -euo pipefail

RUNTIMES_DIR="${1:-/app/data/runtimes}"

for py in /usr/bin/python3.[0-9]*; do
    [ -x "$py" ] || continue

    basename=$(basename "$py")

    # Skip if not a real versioned binary (e.g. python3 symlink)
    [[ "$basename" =~ ^python3\.([0-9]+)$ ]] || continue
    minor="${BASH_REMATCH[1]}"

    version=$($py --version 2>&1 | awk '{print $2}')
    major_minor=$(echo "$version" | cut -d. -f1,2)

    dir="$RUNTIMES_DIR/python/$major_minor"
    mkdir -p "$dir"

    cat > "$dir/runtime.json" <<RTEOF
{
  "language": "python",
  "version": "$major_minor",
  "display_name": "Python $major_minor",
  "executable": "$py",
  "env_create_cmd": ["{executable}", "-m", "venv", "{env_path}"],
  "env_post_create_cmds": [
    ["uv", "pip", "install", "--python", "{env_path}/bin/python", "ipykernel", "mlflow", "hydra-core"]
  ],
  "kernel_cmd": ["{env_path}/bin/python", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
  "kernel_language": "python",
  "package_manager": {
    "list_cmd": ["{env_path}/bin/pip", "list", "--format=json"],
    "install_cmd": ["{env_path}/bin/pip", "install"],
    "remove_cmd": ["{env_path}/bin/pip", "uninstall", "-y"],
    "uv_install_cmd": ["uv", "pip", "install", "--python", "{env_path}/bin/python"]
  }
}
RTEOF

    echo "Created runtime config: python/$major_minor ($version) -> $py"
done

# Free-threading variants (python3.Xt executables from deadsnakes -nogil packages)
for py in /usr/bin/python3.*t; do
    [ -x "$py" ] || continue

    basename=$(basename "$py")

    # Match python3.13t, python3.14t, etc.
    [[ "$basename" =~ ^python3\.([0-9]+)t$ ]] || continue
    minor="${BASH_REMATCH[1]}"

    version=$($py --version 2>&1 | awk '{print $2}')
    major_minor=$(echo "$version" | cut -d. -f1,2)
    version_label="${major_minor}t"

    dir="$RUNTIMES_DIR/python/$version_label"
    mkdir -p "$dir"

    cat > "$dir/runtime.json" <<RTEOF
{
  "language": "python",
  "version": "$version_label",
  "display_name": "Python $major_minor (Free-threaded)",
  "executable": "$py",
  "env_create_cmd": ["{executable}", "-m", "venv", "{env_path}"],
  "env_post_create_cmds": [
    ["uv", "pip", "install", "--python", "{env_path}/bin/python", "ipykernel", "mlflow", "hydra-core"]
  ],
  "kernel_cmd": ["{env_path}/bin/python", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
  "kernel_language": "python",
  "package_manager": {
    "list_cmd": ["{env_path}/bin/pip", "list", "--format=json"],
    "install_cmd": ["{env_path}/bin/pip", "install"],
    "remove_cmd": ["{env_path}/bin/pip", "uninstall", "-y"],
    "uv_install_cmd": ["uv", "pip", "install", "--python", "{env_path}/bin/python"]
  }
}
RTEOF

    echo "Created runtime config: python/$version_label (free-threaded, $version) -> $py"
done

echo "Runtime config generation complete."

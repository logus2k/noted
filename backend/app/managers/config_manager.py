"""NOTED.md configuration manager.

NOTED.md lives in DATA_DIR and stores user-editable configuration in a
simple YAML-front-matter + markdown format.  For now the primary use
is tracking mount definitions (host_path → mount_name).

File format:
```
---
mounts:
  - name: research
    host_path: /home/user/research
  - name: datasets
    host_path: /home/user/datasets
---

# Noted Configuration

Edit this file to manage your workspace mounts.
Each mount maps a host directory into the container.
After changes, restart the container for mounts to take effect.
```
"""

import os
import yaml

from app.config import DATA_DIR

CONFIG_FILE = os.path.join(DATA_DIR, "NOTED.md")

_DEFAULT_CONTENT = """\
---
mounts: []
---

# Noted Configuration

Edit this file to manage your workspace mounts.
Each mount entry maps a host directory into the container as `data/mounts/<name>`.
After adding or removing mounts, restart the container for changes to take effect.

## Mount format

```yaml
mounts:
  - name: my-data         # Appears as data/mounts/my-data
    host_path: /path/on/host
```
"""


def _ensure_config():
    """Create NOTED.md with defaults if it doesn't exist."""
    if not os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_CONTENT)


def _parse_config() -> dict:
    """Parse the YAML front-matter from NOTED.md."""
    _ensure_config()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract YAML between --- delimiters
    if not content.startswith("---"):
        return {"mounts": []}

    end = content.find("---", 3)
    if end == -1:
        return {"mounts": []}

    yaml_str = content[3:end].strip()
    try:
        data = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        return {"mounts": []}

    return data


def _save_config(data: dict):
    """Save config data back to NOTED.md, preserving the markdown body."""
    _ensure_config()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the end of YAML front-matter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            body = content[end + 3:]
        else:
            body = "\n"
    else:
        body = "\n" + content

    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)
    new_content = f"---\n{yaml_str}---{body}"

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)


def get_mounts() -> list[dict]:
    """Return list of configured mounts."""
    data = _parse_config()
    return data.get("mounts", []) or []


def add_mount(name: str, host_path: str) -> dict:
    """Add a new mount entry."""
    if not name or not name.strip():
        raise ValueError("Mount name cannot be empty")
    if not host_path or not host_path.strip():
        raise ValueError("Host path cannot be empty")

    # Sanitize name
    name = name.strip().replace(" ", "-")
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid mount name: {name}")

    data = _parse_config()
    mounts = data.get("mounts", []) or []

    # Check for duplicate names
    for m in mounts:
        if m.get("name") == name:
            raise ValueError(f"Mount '{name}' already exists")

    mounts.append({"name": name, "host_path": host_path.strip()})
    data["mounts"] = mounts
    _save_config(data)
    generate_compose_mounts_file()

    return {"name": name, "host_path": host_path.strip(), "added": True}


def remove_mount(name: str) -> dict:
    """Remove a mount entry by name."""
    data = _parse_config()
    mounts = data.get("mounts", []) or []
    original_len = len(mounts)
    mounts = [m for m in mounts if m.get("name") != name]

    if len(mounts) == original_len:
        raise ValueError(f"Mount '{name}' not found")

    data["mounts"] = mounts
    _save_config(data)
    generate_compose_mounts_file()
    return {"name": name, "removed": True}


def generate_compose_mounts_file() -> str:
    """Generate docker-compose.mounts.yml with volume entries for all mounts.

    This file is a compose override that adds mount volumes to both the
    noted container (/app/mounts/<name>) and all Airflow services that
    need DAG visibility (/opt/airflow/dags/<name>).

    Also adds data/projects to Airflow DAG paths so internal project
    DAGs are discovered automatically.

    Returns the path to the generated file.
    """
    mounts = get_mounts()
    # Normalize backslashes to forward slashes for Docker Compose on Windows
    for m in mounts:
        if 'host_path' in m:
            m['host_path'] = m['host_path'].replace('\\', '/')

    # Airflow services that need to see DAG files
    airflow_dag_services = [
        'airflow-apiserver',
        'airflow-scheduler',
        'airflow-dag-processor',
        'airflow-worker',
        'airflow-triggerer',
    ]

    # Build the compose structure
    services = {}

    # noted service: mount host paths to /app/mounts/<name>
    noted_volumes = []
    for m in mounts:
        host_path = m.get('host_path', '')
        name = m.get('name', '')
        if host_path and name:
            noted_volumes.append(f'{host_path}:/app/mounts/{name}')

    if noted_volumes:
        services['noted'] = {'volumes': noted_volumes}

    # Airflow services: mount host paths to /opt/airflow/dags/<name>
    # so Airflow recursively discovers DAG files in project dags/ folders.
    # Also mount data/projects for internal project DAGs.
    airflow_volumes = []
    airflow_volumes.append('../data/projects:/opt/airflow/dags/_projects')
    for m in mounts:
        host_path = m.get('host_path', '')
        name = m.get('name', '')
        if host_path and name:
            airflow_volumes.append(f'{host_path}:/opt/airflow/dags/{name}')

    if airflow_volumes:
        for svc in airflow_dag_services:
            services[svc] = {'volumes': airflow_volumes.copy()}

    # Graph service: mount host paths to /app/mounts/<name> (read-only, for scanning)
    graph_volumes = []
    for m in mounts:
        host_path = m.get('host_path', '')
        name = m.get('name', '')
        if host_path and name:
            graph_volumes.append(f'{host_path}:/app/mounts/{name}:ro')
    if graph_volumes:
        services['noted-graph'] = {'volumes': graph_volumes}

    compose = {'services': services}

    output_path = os.path.join(DATA_DIR, 'docker-compose.mounts.yml')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('# Auto-generated by noted - do not edit manually.\n')
        f.write('# Provides mount volumes for noted and Airflow services.\n')
        f.write('# Include with: docker compose -f docker-compose.yml -f ../data/docker-compose.mounts.yml up -d\n\n')
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

    return output_path

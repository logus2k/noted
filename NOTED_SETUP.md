# noted — Setup Guide for Reviewers

This document is a short, focused walkthrough for getting **noted**
running on your machine, with both demo projects (`jena_weather` and
`jena_client`) configured as mounts, so you can exercise the full
platform end-to-end.

If you only want to poke around without installing anything, a live
instance is available at:

> **Live demo**: <https://logus2k.com/noted>

For a permanent setup, follow the steps below.

---

## Quick links

- **noted source**: <https://github.com/logus2k/noted>
- **jena_weather** (training project): clone from the tutorial
  materials you received.
- **jena_client** (serving client demo): clone from the tutorial
  materials you received.
- **User Manual**: `documents/user-manual/` in the noted repo, or
  inside noted itself under **Knowledge Base > noted User Manual**
  once the platform is running.

---

## 1. Prerequisites

- **Docker** (Engine 24+ or Desktop 4.30+).
- **Docker Compose** plugin (`docker compose` subcommand).
- **NVIDIA Container Toolkit** (optional, required only if you want
  GPU acceleration for training). See:
  <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>
- **Git** for cloning the repositories.
- **~20 GB free disk** for Docker images and model artifacts.
- A **Linux host** is recommended. macOS and Windows work via
  Docker Desktop but the GPU path is Linux-only.

---

## 2. Clone the repositories

Clone all three repositories to a common parent directory, for
example `~/noted-demo/`:

```bash
mkdir -p ~/noted-demo && cd ~/noted-demo

# noted platform
git clone https://github.com/logus2k/noted.git

# Demo training project
git clone <your-jena_weather-repo-url> jena_weather

# Demo serving client
git clone <your-jena_client-repo-url> jena_client
```

Your layout should now look like:

```
~/noted-demo/
├── noted/
├── jena_weather/
└── jena_client/
```

---

## 3. Configure environment variables

noted reads Docker Compose environment variables from
`services/.env`. A template is provided.

```bash
cd ~/noted-demo/noted/services
cp .env.example .env
```

Open `.env` and set the following:

```bash
# Required: a shared secret the noted terminal uses to authenticate
# terminal sessions. Any non-empty string works for local review.
NOTED_TERMINAL_SECRET=changeme

# Optional: enables Claude models in the noted Assistant.
# Without this, only the local Gemma 4 model is available.
# Get a key at https://console.anthropic.com/
ANTHROPIC_API_KEY=

# Airflow credentials (default admin login for the Airflow UI)
_AIRFLOW_WWW_USER_USERNAME=airflow
_AIRFLOW_WWW_USER_PASSWORD=airflow

# MinIO credentials (the artifact store backing MLflow)
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=password
```

The other fields in the template can be left at their defaults
for a local review.

---

## 4. Configure project mounts

> **Important — read this whole section**: the two demo projects
> (`jena_weather` and `jena_client`) must be configured as **mounts**
> in noted before you can test the platform end-to-end. Otherwise
> noted starts up empty and none of the tutorial flows work.

noted's mounts are configured in the file `data/NOTED.md`, which
uses YAML frontmatter to declare host paths that will be bind-mounted
into the noted container. Edit that file before the first launch:

```bash
cd ~/noted-demo/noted
nano data/NOTED.md   # or your editor of choice
```

Replace the frontmatter section at the top so it matches the absolute
host paths of the two cloned demo projects. For the example layout
above:

```yaml
---
mounts:
- name: jena_weather
  host_path: /home/youruser/noted-demo/jena_weather
- name: jena_client
  host_path: /home/youruser/noted-demo/jena_client
---

# Noted Configuration

Edit this file to manage your workspace mounts.
(rest of the file can stay as-is)
```

Replace `/home/youruser/noted-demo/...` with your real absolute
paths. Relative paths are **not** supported - the file is read by
Docker Compose, which needs absolute host paths.

When noted starts up, it auto-generates `data/docker-compose.mounts.yml`
from `NOTED.md`. You do not need to edit that file by hand - it is
regenerated on every start.

**If you forget this step before the first launch**, you can still
add mounts later via the **Add Mount** action in the Explorer UI:
open the Explorer sidebar, click **Mounts**, and use the context
menu. The UI writes the new entry into `data/NOTED.md` for you. But
for the demo projects specifically, configuring them before the
first launch is faster and cleaner.

---

## 5. Launch noted and its dependencies

### With GPU

```bash
cd ~/noted-demo/noted/services

docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  -f ../data/docker-compose.mounts.yml \
  up -d --build
```

### CPU only

```bash
cd ~/noted-demo/noted/services

docker compose \
  -f docker-compose.yml \
  -f ../data/docker-compose.mounts.yml \
  up -d --build
```

The first launch builds several images and may take 5-15 minutes
depending on your network and CPU. Subsequent launches reuse cached
layers.

On success, `docker compose ps` shows the containers running:

```
noted               Up (healthy)
noted-serving       Up (healthy)
noted-graph         Up (healthy)
noted-evidently     Up (healthy)
noted-nginx         Up
mlflow              Up (healthy)
minio               Up (healthy)
postgres            Up (healthy)
redis               Up (healthy)
airflow-apiserver   Up (healthy)
airflow-scheduler   Up (healthy)
airflow-worker      Up (healthy)
... (more airflow workers)
```

---

## 6. Open noted

Open your browser at:

> **<http://localhost:8123>**

You should see the noted interface with:

- An Explorer sidebar on the left with root sections (Projects,
  Experiments, Data, Orchestration, Models, Environments, Assistant,
  Knowledge Base).
- Under **Mounts** (inside the Projects tree), your `jena_weather`
  and `jena_client` projects, ready to explore.
- A **Knowledge Base** > **noted User Manual** category with 7 pages
  covering every aspect of the platform.

---

## 7. First-run checklist

A quick smoke test to confirm everything is wired up correctly:

1. Open **Knowledge Base > noted User Manual > 1. Your First
   Project** and follow Page 1. This verifies project creation,
   environment creation, notebook, and kernel are working.
2. Open **Mounts > jena_weather > notebooks > emi_tutorial3_jena_weather.ipynb**
   and run a single cell using the Run Manager. This verifies
   Hydra config injection, MLflow tracking, and DVC data lineage
   end-to-end.
3. Click **Experiments** in the icon bar, drill down to the run you
   just created, and verify that all 5 lineage badges (Data, Config,
   Code, Run, Model) are populated.
4. Register the run's model, deploy it via the **Deploy** button,
   and click **Try It** to send a synthetic prediction. This
   verifies the serving stack.
5. Launch the `jena_client` standalone web app from a noted terminal
   (see the `jena_client` README inside its repo) and load a model
   via its dropdown UI. This verifies the external client path.

If all 5 steps pass, your review environment is fully functional.

---

## 8. Stopping and cleaning up

### Stop (preserves data and images)

```bash
cd ~/noted-demo/noted/services
docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  -f ../data/docker-compose.mounts.yml \
  down
```

### Stop and wipe volumes (removes MLflow runs, MinIO objects,
Airflow DB)

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  -f ../data/docker-compose.mounts.yml \
  down -v
```

### Remove the noted image (frees disk)

```bash
docker rmi logus2k/noted
```

The `data/` directory on your host is **not** touched by any `down`
command. It contains your projects, notebooks, environments, and
the noted configuration. Delete it manually only when you want a
completely fresh start.

---

## Troubleshooting

**noted is unreachable at http://localhost:8123**

```bash
docker compose ps             # is the noted container running?
docker logs noted | tail -60  # what does it say?
```

Most commonly a port conflict: another process is already on 8123.
Stop it or change the exposed port in `docker-compose.yml`.

**"permission denied" on data/NOTED.md when editing**

The file may be owned by root from a previous container run.
`sudo chown $USER:$USER data/NOTED.md` or edit with sudo.

**Mounts do not appear in the Explorer**

Check that `data/NOTED.md` has absolute host paths and that the
paths actually exist on the host. Run
`docker exec noted ls /app/mounts/` to confirm noted sees them.
If the mounts file was edited after the container started, restart
the noted service:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  -f ../data/docker-compose.mounts.yml \
  up -d --force-recreate --no-deps noted
```

**GPU not detected inside the noted container**

Verify the NVIDIA Container Toolkit is installed and working on the
host: `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`
should list your GPU. If that succeeds but noted still does not see
the GPU, confirm you used the `-f docker-compose.gpu.yml` override
on the `docker compose up` command.

**Assistant dropdown shows only the local model**

Set `ANTHROPIC_API_KEY` in `services/.env` and restart the noted
container with `--force-recreate --no-deps noted`.

---

## Next steps

- Follow the 7-page **User Manual** (Knowledge Base >
  noted User Manual) for a guided tour of every capability.
- Read the project documentation in `documents/` for architectural
  and planning context: `noted_plan.md`, `noted_vision.md`,
  `noted_scope.md`, and `README.md`.
- Ask questions inside the platform using the **noted Assistant**
  panel - it has 40+ skills covering Airflow, DVC, Evidently,
  Hydra, MLflow, and noted itself.

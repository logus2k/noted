# Setup Guide - Jena Weather Forecasting MLOps Pipeline

This guide walks through the complete setup to reproduce the Tutorial #1 notebook using noted.

## Repositories

- **noted** (platform): https://github.com/logus2k/noted
- **jena_weather** (project): https://github.com/logus2k/jena_weather

---

## Prerequisites

- Docker and Docker Compose installed
- Git installed
- GPU support (optional): [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

---

## 1. Clone the jena_weather project

```bash
git clone https://github.com/logus2k/jena_weather.git
```

---

## 2. Configure the environment

Edit the provided `.env` file and set `JENA_WEATHER_PATH` to the absolute path where you cloned jena_weather:

```ini
JENA_WEATHER_PATH=/home/youruser/jena_weather
```

On Windows (Docker Desktop), use forward slashes:

```ini
JENA_WEATHER_PATH=C:/Users/youruser/jena_weather
```

---

## 3. Launch the stack

There are two options for running the noted platform:

### Option A: Pull from Docker Hub (recommended)

Run from the directory where you extracted the delivery zip. The noted image will be pulled automatically from Docker Hub.

**With GPU support:**

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.local.yml up -d
```

**CPU only:**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

### Option B: Build from source

Clone the noted repository and run from `noted/services`. This builds the noted image locally.

```bash
git clone https://github.com/logus2k/noted.git
cd noted/services
cp /path/to/delivery/.env .
```

**With GPU support:**

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.local.yml up -d --build
```

**CPU only:**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

### Monitor startup

Wait for all containers to start (first launch takes several minutes for Airflow initialization):

```bash
docker logs noted -f
```

---

## 4. Access noted

Open your browser and navigate to:

http://localhost:6543

The noted workspace should load with the Explorer panel on the left. All integrated services (MLflow, Airflow, MinIO) are accessible through this single URL via the nginx reverse proxy.

---

## 5. Verify the jena_weather mount

In the Explorer panel, expand the workspace tree. The `jena_weather` mount should appear under the Mounts section. Expand it to see the project files: `config/`, `data/`, `notebooks/`, `src/`, etc.

---

## 6. Create a virtual environment and install dependencies

1. In the Explorer, expand **Virtual Environments** and click on a runtime (e.g., Python 3.12)
2. Enter an environment name (e.g., `jena_env`) and click **Create Virtual Environment**
3. Once created, select the new environment and open the **Packages** section
4. Install the required packages: `tqdm tensorflow[and-cuda]`

Note: `mlflow`, `hydra-core`, and `ipykernel` are pre-installed automatically in every new environment.

For CPU-only setups, install `tensorflow` instead of `tensorflow[and-cuda]`.

---

## 7. Open and run the notebook

1. In the Explorer, navigate to `jena_weather > notebooks`
2. Double-click `emi_tutorial1.ipynb` to open it
3. Select the virtual environment created in step 6 using the kernel selector in the notebook toolbar
4. Click **Run All** to execute all cells

The notebook will:
- Download the Jena Climate dataset (if not already present)
- Track it with DVC and push to MinIO
- Load and preprocess the data
- Load the Hydra configuration and compute its hash
- Train a baseline linear regression model
- Log all parameters, metrics, DVC hash, and Hydra config hash to MLflow
- Verify the logged data lineage

---

## 8. Verify results

### MLflow Experiments

Click the **MLflow** icon in noted's sidebar (bottom icon group) to open the MLflow UI. Navigate to the experiment matching the jena_weather project. You should see the `baseline_linear_regression` run with:

- **Parameters:** `dvc_data_hash`, `hydra_config_hash`, `model_type`, `features`, etc.
- **Tags:** `dvc.data_hash`, `dvc.data_file`, `hydra.config_hash`
- **Metrics:** `mae`, `rmse`
- **Artifacts:** `hydra_config.yaml`

### MinIO Storage

Click the **MinIO** icon in noted's sidebar to open the MinIO console (login: `admin` / `password`). Browse the `noted-dvc` bucket to verify the DVC-pushed dataset, and `noted-mlflow-artifacts` for MLflow run artifacts.

---

## 9. Service URLs (reference)

All services are accessed through the nginx proxy at `localhost:6543`:

| Service | URL | Credentials |
|---------|-----|-------------|
| noted | http://localhost:6543 | - |
| MLflow | http://localhost:6543/mlflow | - |
| Airflow | http://localhost:6543/airflow | airflow / airflow |
| MinIO Console | http://localhost:6543/minio | admin / password |

---

## Troubleshooting

- **`bash\r` error in container logs:** CRLF line ending issue on Windows. Rebuild with `docker compose build --no-cache noted`
- **Airflow 502 Bad Gateway:** Ensure you're using `docker-compose.local.yml` override. Run `docker compose down` then `up` with all three compose files
- **Mount not visible in Explorer:** Verify `JENA_WEATHER_PATH` in `.env` points to the correct absolute path
- **Kernel won't start:** Ensure the virtual environment was created successfully and is selected in the toolbar
- **DVC push fails:** Check that the MinIO container is running (`docker ps | grep minio`)

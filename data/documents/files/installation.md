# Apache Airflow Installation Guide

This guide provides a step-by-step walkthrough for setting up Apache Airflow 3.1.7 using Docker. It covers the specific requirements for both Windows (Docker Desktop) and Linux (including WSL2).

In case your installation is successful, you'll see a screen similar to this:

<img src="https://logus2k.com/docbro/categories/airflow/images/homepage.png" width=600/>

> The official reference page for the installation can be found at: [Running Airflow in Docker](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html)

## 1. Project Initialization
Create the project root directory and set up a local Python virtual environment for development.

### Create and Enter Folder
**Windows:**
```powershell
md EMI-WeatherForecast
cd EMI-WeatherForecast

```

**Linux:**

```bash
mkdir EMI-WeatherForecast
cd EMI-WeatherForecast

```

### Setup Virtual Environment

```bash
python -m venv .venv_emi_weather

```

### Activate Environment

**Windows:**

```powershell
.venv_emi_weather\Scripts\activate

```

**Linux:**

```bash
source .venv_emi_weather/bin/activate

```

---

## 2. Docker Requirements

Before proceeding, ensure Docker and Docker Compose are installed and running.

```bash
# Check installations
docker --version
docker compose version

```

### Pull the Base Image

```bash
docker pull apache/airflow:latest

```

---

## 3. Airflow Directory Setup

Create the specific folder structure required by the Airflow Docker Compose file.

**Windows:**

```powershell
md airflow
cd airflow
md config
md logs
md plugins
md dags

```

**Linux:**

```bash
mkdir airflow
cd airflow
mkdir config logs plugins dags

```

---

## 4. Environment Configuration

Create the necessary configuration files inside the `/airflow` folder.

### Create `.env`

**On Windows:** Create a file named `.env` and paste:

```text
AIRFLOW_IMAGE_NAME=apache/airflow:latest
AIRFLOW_UID=50000

```

**On Linux:** Run these commands:

```bash
echo "AIRFLOW_IMAGE_NAME=apache/airflow:latest" > .env
echo "AIRFLOW_UID=$(id -u)" >> .env

```

### Create `Dockerfile`

Create a file named `Dockerfile` (no extension) with the following content:

```dockerfile
FROM apache/airflow:latest

```

---

## 5. Docker Compose Setup

1. Download the official [docker-compose.yaml](https://airflow.apache.org/docs/apache-airflow/3.1.7/docker-compose.yaml) and place it in your `/airflow` folder.
2. Open the file and locate the `x-airflow-common` section.
3. Modify the following lines:

```yaml
x-airflow-common:
  &airflow-common
  # image: ${AIRFLOW_IMAGE_NAME:-apache/airflow:3.1.7}  # 1. Comment this line
  build: .                                              # 2. Uncomment this line
  env_file:
    - ${ENV_FILE_PATH:-.env}

```

---

## 6. Deployment

Execute the following commands from within the `/airflow` folder to build and start your environment.

### Build the Image

```bash
docker compose build

```

### Initialize the Database

```bash
docker compose up airflow-init

```

*Wait until the process finishes with `exited with code 0`.*

### Start Airflow

```bash
docker compose up -d

```

---

## 7. Verification & Access

Wait approximately 1 minute for all containers to reach a "healthy" state.

### Check Status

```bash
docker compose ps

```

### Access the UI

Open your browser and navigate to: **http://localhost:8080**

**Login Credentials:**

* **Username:** `airflow`
* **Password:** `airflow`

### Common Troubleshooting

| Issue | Solution |
| --- | --- |
| **Containers keep restarting** | Check your Docker RAM. Increase it to at least 4 GB in Docker Settings > Resources. |
| **Permission denied (Linux)** | Ensure you set the `AIRFLOW_UID` in the `.env` file as shown in Step 3. |
| **Port 8080 already in use** | Open `docker-compose.yaml` and change the mapping for `airflow-webserver` from `8080:8080` to `8081:8080`. |

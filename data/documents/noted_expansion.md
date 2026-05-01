# noted Expansion

## 1. Executive Summary
The goal of the **noted** expansion is to transition from a Python-centric ML workbench to a high-performance, polyglot AI engineering platform. By integrating languages like **Julia**, **R**, and **Mojo**, and implementing a "Zero-Copy" data bridge, **noted** will solve the "two-language problem" (research vs. production) that current platforms like Databricks or standard Jupyter often fail to address seamlessly.

---

## 2. Language Expansion Roadmap

### 2.1 Julia: The Performance Core
* **Rationale:** Julia solves the "two-language problem" by offering the readability of Python with the execution speed of C/Fortran. It is essential for Scientific Machine Learning (SciML) and custom mathematical solvers.
* **Integration:**
    * **Native Path:** Use `IJulia` as a first-class kernel.
    * **Python Interop:** Leverage `PythonCall.jl` to allow Julia users to import existing Python-based tools like **Evidently** or **Hydra** directly into Julia scripts.
    * **MLOps:** Use `MLFlowClient.jl` for native experiment tracking.

### 2.2 R & Octave: The Academic & Statistical Bridge
* **Rationale:** R remains the gold standard for statistical analysis, while Octave provides critical compatibility for legacy MATLAB-based engineering code.
* **Integration:**
    * **R:** Use `IRkernel` and the official `mlflow` R package.
    * **Octave:** Integrate via `oct2py` on the backend or a dedicated Octave kernel.
    * **MLOps:** Use CLI wrappers (via the `subprocess` pattern) for DVC and Airflow orchestration.

### 2.3 Mojo: Next-Gen AI Acceleration
* **Rationale:** As a superset of Python, Mojo allows for massive performance gains (up to 68,000x over standard Python) while maintaining compatibility with the existing Python ecosystem.
* **Integration:** Add the Mojo kernel to the `noted` Docker runtime to allow users to write custom high-performance kernels without leaving the Python syntax family.

### 2.4 SQL: The Data-First Citizen
* **Rationale:** Most ML begins with data retrieval. First-class SQL support allows for a "SQL-to-Model" pipeline within a single environment.
* **Integration:** Use **DuckDB** as the local SQL engine to query Parquet/CSV files directly in the project directory.

---

## 3. Technical Integration Architecture

### 3.1 The "State Bridge" (Sharing Data Between Cells)
To move from separate files to a unified polyglot notebook experience, **noted** must manage state across different language runtimes.

* **Apache Arrow (Memory Layer):** Use Arrow's columnar format to share data between Python, Julia, and R. Because Arrow uses a standardized memory layout, data can be passed between kernels in **milliseconds** with zero serialization overhead.
* **DuckDB (The Data Bus):** Implement DuckDB as a central hub. A SQL cell can transform a dataset, and the resulting table can be immediately accessed as a native DataFrame in a subsequent Python or Julia cell.

### 3.2 Unified MLOps Service Mesh
The existing backend architecture can support multiple languages by abstracting the service interactions:

| Feature | Strategy for Expansion |
| :--- | :--- |
| **MLflow** | Retain `MlflowManager` in Python; use REST API for Node.js/R and native clients for Julia. |
| **DVC** | Remain language-agnostic by using the current `DvcManager` subprocess wrapper. |
| **Airflow** | Orchestrate non-Python scripts via `BashOperator` or `DockerOperator`, triggered via the `AirflowManager` REST client. |
| **Evidently** | Use the existing async HTTP client pattern to allow R or Julia cells to send data to the Evidently service for drift reporting. |

---

## 4. Market Positioning: noted vs. Databricks

While Databricks focuses on "Big Data" for enterprises, **noted** is positioned as the high-performance workstation for "AI Engineers."

* **The "Gap":** Databricks is often too complex and "heavy" for rapid research. **noted** offers a low-config, modular approach using open-source standards (DVC, MLflow) rather than proprietary vendor lock-in.
* **Performance Advantage:** By prioritizing Julia and Mojo, **noted** enables researchers to build new algorithms that run at native speed, something Databricks' JVM-based Spark context is not optimized for.

---

## 5. Assistant & MCP Evolution
The **noted** Assistant must be updated to handle the new polyglot surfaces:

* **Context Emitters:** Add new emitters in `llm_context.py` for `julia_active`, `sql_in_context`, etc., to gate language-specific skills.
* **Polyglot Tools:** Expand the MCP toolset in `backend/app/mcp/tools.py` to include tools for sharing variables between languages (e.g., `share_to_python`, `get_from_sql`).
* **Language-Specific Skills:** Drop new `SKILL.md` files into `data/skills/` focused on Julia optimization, R plotting, and Mojo performance.

---

## 6. Deployment Impact
* **Containerization:** The `docker-compose.yml` will be updated to include broader Jupyter kernel installations.
* **Backend Scaling:** The `KernelManagerService` will be enhanced to track multiple active kernels per project session to support per-cell language switching.

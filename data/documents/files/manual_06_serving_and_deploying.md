# Page 6: Serving & Deploying Models

**Goal**: Register a trained model, deploy it into the serving
endpoint, test it with the built-in Try It panel, and understand how
external clients can consume it.

**Prerequisite**: A finished MLflow run that logged a model (Page 3
or Page 4).

**Time**: ~10 minutes.

---

## What is noted-serving?

`noted-serving` is a small FastAPI service that loads a registered
MLflow model into memory and answers prediction requests over HTTP.
It runs as its own container alongside the noted container and
talks to the same MLflow tracking server.

Exactly one model is deployed at a time. Deploying a new model
replaces the currently loaded one. This keeps the demo simple and
the memory footprint small.

From noted's Explorer you can:

- **Register** a model version from a run.
- **Deploy** any registered version to `noted-serving`.
- **Unload** the currently deployed model.
- **Try It** by sending a synthetic input to the running model and
  seeing its prediction.
- Inspect the **Logged Model** artifacts (`MLmodel`, `conda.yaml`,
  `python_env.yaml`, `requirements.txt`, and the framework-specific
  weights) that MLflow archived when the model was logged.

---

## Step 1: Register a model from a run

Open the **Experiments** section in the Explorer, drill down to the
run that produced the model you want to serve, and click to open
its detail panel.

Scroll to the action buttons and click **Register Model**.

A dialog asks for:

- **Model name** - the name the model will appear under in the
  Registry (for example `Jena Weather Forecaster`). Registering
  under an existing name creates a new version instead of a new
  model.
- **Aliases** (optional) - any aliases to attach to this version.
  A common pattern is to set `champion` on the version that
  downstream systems should pick up.

Click **Register**. The new version appears under
**Models > Model Registry > {model name}** in the Explorer.

Each registered version has a lineage chain visible in its detail
panel. See Page 3 Step 5 for the full explanation of the
Data / Config / Pipeline / Code / Run / Model chain.

---

## Step 2: Open the Model Registry view

Click **Models > Model Registry** in the Explorer to see the full
list of registered models and versions. For each version, the
detail panel shows:

- **Version metadata** - version number, created timestamp,
  description, stage, aliases.
- **Lineage chain** - the five (or six) layer cards showing the
  data, config, pipeline, code, MLflow run, and the registered
  model itself.
- **Deploy / Unload / Try It** buttons - the three-button
  controller for serving.
- **Logged Models** section - the MLflow 3.x Logged Model entity
  linked to this run. Expanding it shows the archived artifact tree:
  `MLmodel` (with the model signature and flavor), `conda.yaml`,
  `python_env.yaml`, `requirements.txt`, and the framework-specific
  `data/` folder. Clicking any file opens a syntax-highlighted
  preview of its contents.

---

## Step 3: Deploy a version

Click **Deploy** on the version you want to serve.

noted opens a streaming progress card that shows the phases of the
deploy as they happen:

- **resolving** - looking up the version in MLflow.
- **downloading** - fetching the model artifact locally.
- **loading_model** - loading the weights into the serving process.
- **ready** - the model is live and ready to answer predictions.

A successful deploy takes a few seconds for a cached model and a
few tens of seconds for a cold one (first time a given model is
loaded after container start).

When the deploy completes, the state machine on the version card
transitions to **Deployed here** and the **Unload** button becomes
available. Other versions of the same model show **Deployed
elsewhere** to make it clear where the currently-serving one lives.

If the deploy fails, the progress card shows an **error** phase
with a clear message: MLflow unreachable, version not found,
artifact download failed, or model load error. Noted never reports
success if the load did not actually complete.

---

## Step 4: Test the deployed model with Try It

With a model deployed, click **Try It** on its version card. The
Try It panel opens showing:

- **Current model** - name, version, and load time (confirms you
  are testing the right one).
- **Input form** - derived from the model's signature. For a
  tensor-input model, it shows the expected shape and dtype, with a
  **Generate Sample** button that builds a synthetic input matching
  the signature.
- **Predict** button - sends the input to the serving endpoint.
- **Prediction output** - rendered according to the model's output
  signature: a scalar, a vector plotted as a chart, or a JSON tree
  for structured outputs.

Try It is the fastest way to verify a deploy: deploy, click Try It,
click Predict, see a result.

---

## Step 5: Unload the current model

Click **Unload** on the currently-deployed version. noted asks the
serving container to drop the model and free its memory.

Unload is optional between deploys. Deploying a new version
automatically unloads the previous one. Unload is useful when you
want to:

- Free GPU memory without deploying anything new.
- Confirm a deploy / unload cycle as part of a smoke test.

After unload, all version cards for this model show **Not
deployed**, and Try It is disabled until something is deployed
again.

---

## Step 6: Inspect the Logged Model artifacts

The **Logged Models** section under the version card shows the
MLflow 3.x Logged Model entity linked to this run. It is a separate
artifact store from the run's own artifact tree - the model binary
plus the environment files that describe how it was trained and
what it needs at inference time.

Click any file to preview it inline:

- **`MLmodel`** - the YAML manifest with the model signature, flavor
  (tensorflow, pytorch, sklearn, and so on), loader module, and
  MLflow version. Syntax-highlighted.
- **`requirements.txt`** - the pip requirements that MLflow captured
  when the model was logged. This is what a production serving
  environment needs to install to run the model faithfully.
- **`conda.yaml`** / **`python_env.yaml`** - conda and pip
  environment specs, again for serving-time reproducibility.
- **`data/`** - the framework-specific model files (for example
  `model.keras` for a Keras model, `state_dict.pt` for PyTorch).

A **Download** button is available on each file so you can export
any of them without leaving noted.

---

## Step 7: Consuming the model from an external client

The `noted-serving` container exposes a simple HTTP API that any
external client can use:

- `GET /health` - current state (what model is loaded, load time,
  framework, parameter count).
- `POST /load` - streaming NDJSON response that loads a model by
  name and version (and optionally alias).
- `POST /predict` - sends an input to the currently loaded model
  and returns the prediction.
- `GET /schema` - the model's input and output signature, used by
  clients to build correct request payloads.

A working reference client ships with the platform at
`iscte/jena_client/`. It is a small FastAPI + socket.io app that:

- Talks to MLflow directly via REST to list registered models and
  their versions and aliases.
- Presents three dropdowns (Model / Version / Alias) so a user can
  pick which version to load.
- Streams load progress from `noted-serving`'s NDJSON endpoint and
  shows the phases in its UI.
- Builds a synthetic input matching the loaded model's schema,
  sends it to `/predict`, and renders the result as a chart plus a
  table.
- Applies the inverse scaler transform (using `target_mean` and
  `target_std` logged as MLflow params) to convert standardized
  model output back into real units when the model was trained on
  normalized data.

The jena_client is useful as a standalone demo of noted-serving and
as a starting point for building a custom inference UI for your
own models.

---

## Where to go next

- **Page 7 - noted Assistant** introduces the in-product AI
  assistant. It can answer questions about deployed models, run
  diagnostics, and trigger MCP tool calls such as model registration
  and run comparison.

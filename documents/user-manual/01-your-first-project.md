# Page 1: Your First Project

**Goal**: Create a new project, set up a Python environment, open a
notebook, and run your first cell. By the end of this page you will
have a working notebook connected to a Python kernel with your
installed packages ready to use.

**Time**: ~5 minutes

---

## The noted interface

When you open noted in your browser, you see a layout similar to a
modern code editor:

- A narrow **icon bar** on the left (vertical strip of icons).
- A **sidebar panel** (Explorer) that opens when you click an icon.
- A **center pane** where notebooks and files open.
- A **right panel** that hosts the noted Assistant (collapsible).

The Explorer is organized into top-level sections that each represent
a capability of noted: **Projects**, **Experiments**, **Data** (Catalog
and Storage), **Orchestration**, **Models** (Registry and APIs),
**Environments**, **Assistant**, and **Knowledge Base** (Graph plus
document categories).

Most operations in noted start with a click on one of these sections.

---

## Step 1: Create a project

1. Click the **folder icon** on the icon bar to open the Explorer if
   it is not already visible.
2. Double-click **Projects** to expand it, then single-click
   **Projects** to select it.
3. The Explorer title bar shows a green **Create Project** (`+`)
   button. Click it.
4. Enter a project name (for example `my-first-project`) and confirm.

Your new project appears under Projects in the tree.

> **Tip**: noted follows a "select first, then act" pattern. Most
> actions appear in the title bar and change depending on the node you
> have selected in the Explorer tree. You can also right-click any
> node to see a context menu with the same actions.

---

## Step 2: Create a notebook

1. Double-click your new project to expand it.
2. Right-click the project name and choose **New Notebook**.
3. Name the notebook (for example `experiment.ipynb`) and confirm.

The notebook opens in the center pane with one empty code cell.

---

## Step 3: Create a Python environment

Before you can run code, you need a Python environment. noted manages
Python, JavaScript, and R environments under the **Environments**
section.

1. In the Explorer, double-click **Environments** to expand it. You
   see language sub-nodes: **Python**, **JavaScript**, **R**.
2. Double-click **Python** to expand it. You see the Python versions
   available on the host (typically 3.10 through 3.14).
3. Right-click on a version (for example `Python 3.12`) and choose
   **Create Environment**.
4. Enter an environment name (for example `my-env`) and confirm.
5. noted creates the virtual environment in a few seconds and a toast
   notification confirms success.

The new environment appears as a child of its Python version under
the Environments section.

---

## Step 4: Install packages

A fresh environment contains only `pip` and `setuptools`. To install
packages you need for your work:

1. In the Explorer, click your environment. The center pane shows the
   environment detail page with a package list and an install control.
2. Type package names into the install input (for example
   `numpy pandas matplotlib`) and click **Install**.
3. A terminal opens showing live pip output. When the install
   finishes, the package list refreshes.

You can install any packages available on PyPI the same way, either
one at a time or several at once.

---

## Step 5: Connect the environment to your notebook

The notebook needs to know which environment to use for running cells.

1. Click the notebook's tab in the center pane to focus it.
2. In the notebook's **top bar**, click the **kernel selector**. It
   shows the current kernel status (initially **No kernel**).
3. A list of available environments appears. Pick the environment you
   just created (for example `my-env (Python 3.12)`).
4. The kernel status indicator turns green when the kernel is ready
   (~5 seconds).

The notebook is now bound to your environment for the lifetime of the
session.

---

## Step 6: Run your first cell

1. Click inside the empty code cell.
2. Type:
   ```python
   import numpy as np
   print(f"numpy version: {np.__version__}")
   print("Hello from noted!")
   ```
3. Press **Shift+Enter** to run the cell (or click the play button in
   the cell toolbar).
4. The output appears below the cell.

You now have a working notebook.

---

## Where to go next

- **Page 2 - Configuring an Experiment** shows how to use noted's
  Hydra Composer to parameterize your training code so you can sweep
  across many configurations without editing the notebook.
- **Page 3 - Running an Experiment** explains how the Run Manager
  wraps your notebook execution in an MLflow run that captures
  parameters, metrics, data lineage, and the full Hydra configuration
  bundle for reproducibility.
- **Page 7 - noted Assistant** introduces the in-product AI assistant
  that knows all of noted's capabilities and can answer questions or
  perform tasks for you.

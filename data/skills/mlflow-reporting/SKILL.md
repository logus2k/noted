---
name: mlflow-reporting
description: Generating experiment reports in Word and Markdown format. Use when user asks how to create a report, export experiment results, generate a Word document, or prepare results for presentation or thesis.
triggers: [mlflow_experiment_in_context]
priority: 1
max_tokens: 350
---
Experiment reporting in noted:

REPORT GENERATION:
- Access via the Reports section in the Experiments panel.
- Select an experiment and choose runs to include.
- Output formats: Word (.docx) and Markdown (.md).
- Reports are generated server-side using DocumentConverter.

REPORT CONTENTS:
- Experiment summary: name, creation date, total runs.
- Run comparison table: all selected runs with key metrics and parameters.
- Best run highlight: automatically identifies the top performer on the primary metric.
- Training curves: embedded chart images from run artifacts.
- Configuration details: Hydra config used for each run.
- Model information: architecture, parameter count, artifact paths.

CUSTOMIZATION:
- Choose which metrics and parameters to include in the comparison table.
- Select the primary metric for ranking runs.
- Include or exclude training curve charts.
- Add custom sections or notes before generating.

WORKFLOW:
1. Complete a set of experiments (manual runs or sweep).
2. Open Reports in the Experiments panel.
3. Select the experiment and relevant runs.
4. Configure report options (metrics, format).
5. Generate and download the report.

USE CASES:
- Team progress updates: share results with colleagues.
- Experiment documentation: record what was tried and what worked.
- Thesis/paper preparation: export formatted results for academic writing.

Reports pull data directly from MLflow - no manual data entry needed. The generated Word documents use proper formatting with tables and embedded images.

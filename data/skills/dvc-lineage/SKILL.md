---
name: dvc-lineage
description: How DVC hashes connect to MLflow runs and model lineage. Use when user asks which data trained a model, how to trace data to model, what dataset a run used, or how to check data provenance.
triggers: [dvc_in_context]
priority: 1
max_tokens: 350
---
DVC-to-MLflow lineage in noted:

THE CONNECTION:
- When a run is executed via the Run Manager, noted tags the MLflow run with the DVC hashes of selected datasets.
- The tag key follows the pattern: `dataset.<filename>` with the DVC MD5 hash as the value.
- This creates a direct link: which data version produced which training result.

TRACING DATA TO MODEL:
1. Start with a DVC-tracked file and its hash.
2. Search MLflow runs for the matching dataset tag hash.
3. Those runs were trained on that exact data version.
4. From the run, follow to the registered model version (if any).
5. Result: data file hash -> run -> model version.

TRACING MODEL TO DATA:
1. Start with a registered model version.
2. Find its source run_id.
3. Check the run's dataset tags for DVC hashes.
4. Match hashes to `.dvc` pointer files in git history.
5. Result: model version -> run -> data file hash -> git commit.

USE CASES:
- "Which data was used to train the champion model?" - trace model -> run -> dataset tags.
- "Which models used this dataset version?" - search runs by dataset hash.
- "Did the data change between run A and run B?" - compare their dataset tag hashes.
- "Can I reproduce this model?" - checkout the git commit, DVC checkout the data hash, use the Hydra config hash.

KNOWLEDGE GRAPH:
- The Knowledge Graph visualizes these relationships as nodes and edges.
- Data versions, runs, and model versions appear as connected entities.
- Hover to see hashes and metadata. Click to navigate to the entity.

Always reference specific hashes when discussing lineage - vague references like "the data" are ambiguous.

RECONSTRUCT A RUN'S DATA (workflow when user asks "what data trained run X"):
1. Call `get_run_details(run_id=<id>)` to fetch the run's params and tags.
2. Look in the params for `dataset_hashes` (or `dataset.<filename>` tags). These are the DVC MD5 hashes of the files used.
3. Always state the reproduction recipe even if the hashes aren't present: find the git commit where those exact hashes live in the `.dvc` pointer files (e.g. `git log -p -- 'data/*.dvc'` and grep the hash), `git checkout <commit>`, then `dvc checkout` syncs data files to those hashes.
4. If the run lacks `dataset_hashes` (pre-DVC tagging or triggered without dataset selection), SAY SO plainly AND still describe steps 1-3 generically so the user knows the standard recipe for future runs.

"SAME METRICS, SAME DATA?" / "COMPARE TWO RUNS' DATA":
- When the user gives you two run_ids and wants to know if they used the same data, call `compare_runs(run_id_a=<id_a>, run_id_b=<id_b>)` ONCE. This tool returns params (including `dataset_hashes`), metrics, and tags side by side.
- Do NOT call `get_run_details` after `compare_runs` - the comparison already contains every param and tag you need. Additional calls are redundant and forbidden here.
- If the user didn't name the runs, first call `get_experiment_runs(experiment_name=<project>)` to find candidates, then `compare_runs` on the chosen pair.
- Inspect the `dataset_hashes` row/column in `compare_runs` output. Equal hashes -> same data (so equal metrics are not coincidental). Different hashes -> different data. If hashes are missing on both runs, say that plainly - the runs pre-date DVC tagging or lacked dataset selection; do not speculate.

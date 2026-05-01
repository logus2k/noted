# Skill: dvc-lineage

**Type:** skill
**Source:** [data/skills/dvc-lineage/SKILL.md](../../../data/skills/dvc-lineage/SKILL.md)

## Purpose

How DVC dataset hashes plug into noted's lineage chain.

## Scenarios

### S1 - DVC role in lineage
dataset_hashes param on runs.

### S2 - Reconstruct data
`get_run_details` → dataset_hashes → git commit → checkout.

### S3 - Same metrics coincidence?
`compare_runs`; compare dataset_hashes.

### S4 - dvc dag viz (DEFERRED)
### S5 - stages vs tracking (DEFERRED)

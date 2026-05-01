# Skill: mlflow-model-registration

**Type:** skill
**Source:** [data/skills/mlflow-model-registration/SKILL.md](../../../data/skills/mlflow-model-registration/SKILL.md)

## Purpose

Registry semantics: register_model from a run, alias management, Logged Model id vs Registry version.

## Scenarios

### S1 - Register from run
Direct call; report version; no auto-deploy.

### S2 - Logged Model id rejection
m-XXXX ≠ version; explain flow.

### S3 - Register + promote + deploy
Multi-turn; clear ordering.

### S4 - Name selection
`list_registered_models` for consistency; do not pick for user.

### S5 - artifact_path default
Default "model"; override for custom schemes.

### S6 - Cross-project (DEFERRED)
### S7 - Staging gates (DEFERRED)

# Skill: noted-notebook-resolution

**Type:** skill
**Source:** [data/skills/noted-notebook-resolution/SKILL.md](../../../data/skills/noted-notebook-resolution/SKILL.md)

## Purpose

Defines how noted resolves "this cell", "selected", and notebook identity across renames.

## Scenarios

### S1 - Selected cell resolution
Use WORKSPACE CONTEXT's SELECTED marker; do not re-fetch.

### S2 - "This" pronoun
Maps to SELECTED cell(s) in latest context.

### S3 - Selection changes between turns
Always use latest context, not prior conversation.

### S4 - No selection + specific number
`get_notebook_cells` to fetch.

### S5 - No selection + generic "this"
Ask user; do not guess.

### S6 - notebook_uid stability
UUID in .ipynb metadata; stable across renames.

### S7 - Notebook in mount (DEFERRED)
### S8 - UID migration (DEFERRED)

---
name: airflow-scheduling
description: Cron expressions, Airflow Variables, and schedule presets. Use when user asks how to schedule a DAG, set up cron timing, configure periodic runs, or use Airflow Variables for runtime settings.
triggers: [airflow_in_context]
priority: 1
max_tokens: 400
---
Airflow scheduling in noted:

CRON EXPRESSIONS:
- Format: `minute hour day_of_month month day_of_week`.
- Examples:
  - `0 6 * * *` - daily at 6 AM.
  - `0 */4 * * *` - every 4 hours.
  - `0 0 * * 1` - every Monday at midnight.
  - `30 8 1 * *` - 8:30 AM on the first of each month.
- Set in the DAG definition: `@dag(schedule="0 6 * * *")`.

AIRFLOW PRESETS:
- `@daily` - once a day at midnight.
- `@hourly` - once an hour at minute 0.
- `@weekly` - once a week on Sunday at midnight.
- `None` - no automatic schedule (manual trigger only).
- Most noted DAGs use `None` since experiments are triggered manually or via sweeps.

AIRFLOW VARIABLES:
- Key-value pairs stored in Airflow for runtime configuration.
- Access in DAGs: `Variable.get("key_name")`.
- Set via the noted API or Airflow admin.
- Use for environment-level settings that should not live in Hydra configs (e.g., notification URLs, resource limits).

BEST PRACTICES:
- Use `None` for experimental/development DAGs. Schedule only stable pipelines.
- Avoid scheduling at exact round times (e.g., `0 0 * * *`) to prevent resource contention.
- Use catchup=False to prevent backfilling missed runs: `@dag(catchup=False)`.
- For periodic retraining, prefer a weekly or daily schedule with data freshness checks.
- Store schedule-related thresholds in Airflow Variables, not hardcoded.

TIMEZONE:
- Airflow uses UTC by default.
- Set timezone in the DAG: `@dag(schedule="0 6 * * *", start_date=datetime(..., tzinfo=...))`.

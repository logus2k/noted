"""Assistant test harness.

Components:
  - scenario_loader: parses .yaml scenario files
  - fixtures: idempotent state staging (serving + MLflow)
  - driver: POST to noted /api/llm/chat, consume SSE
  - stream_parser: SSE -> (tool_calls, reasoning, answer)
  - judge: format envelope, POST to noted_judge, parse JSON verdict
  - run_tests: CLI entry point

See ../architecture/harness_design.md for the authoritative design doc.
"""

#!/bin/bash
# Run the chat-driven Playwright probe N times, wipe between runs, and
# tabulate pass / fail / failure-mode. Mirrors the user's actual UI test
# path (chat input -> request_new_tool -> create_tool workflow) so the
# pass rate measured here = the pass rate they would experience.
set -u

N=${1:-5}
LOGDIR=/tmp/passrate_$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOGDIR"
echo "Logging to $LOGDIR"
# Wipe ALL workflow snapshots ONCE up front so this measurement starts
# with a clean slate; the per-run loop below preserves snapshots so
# llm_calls.jsonl is available for post-hoc analysis of failures.
docker exec noted bash -c 'rm -rf /app/data/tenants/default/user_tools/* /app/data/tenants/default/workflows/* /app/data/skills/_archive/*' >/dev/null 2>&1
docker exec noted bash -c 'find /app/data/skills -maxdepth 2 -name SKILL.md -exec grep -l "^provenance: user" {} \; 2>/dev/null | xargs -r dirname | xargs -r -I{} rm -rf {}'
docker restart noted-tools >/dev/null 2>&1
sleep 5
echo

PASS=0
FAIL=0
declare -a SUMMARY

for i in $(seq 1 $N); do
  echo "===== run $i / $N ====="
  LOG="$LOGDIR/run_${i}.log"

  # Pre-run cleanup: ABORT suspended workflows so the runtime threads release,
  # but DO NOT delete the workflow snapshots — we want to preserve
  # llm_calls.jsonl for post-hoc analysis. Only wipe the published tool/skill
  # artifacts so the next run starts with empty toolset / skill registry.
  curl -sS http://localhost:8123/api/workflows 2>/dev/null | python3 -c "
import sys, json
for w in json.load(sys.stdin).get('workflows') or []:
    if w['status'] == 'suspended':
        print(w['workflow_id'])" | while read id; do
    curl -sS -m 5 -X POST http://localhost:8123/api/workflows/$id/abort >/dev/null 2>&1
  done
  # Wipe published artifacts only (tool dirs + skill folders + archives).
  # Workflow snapshot dirs (containing llm_calls.jsonl) are PRESERVED.
  docker exec noted bash -c 'rm -rf /app/data/tenants/default/user_tools/* /app/data/skills/_archive/*' >/dev/null 2>&1
  docker exec noted bash -c 'find /app/data/skills -maxdepth 2 -name SKILL.md -exec grep -l "^provenance: user" {} \; 2>/dev/null | xargs -r dirname | xargs -r -I{} rm -rf {}'
  docker restart noted-tools >/dev/null 2>&1
  sleep 5
  curl -sS -m 5 -X POST http://localhost:8123/api/llm/mcp-tools/refresh >/dev/null 2>&1

  # Run the chat-driven probe
  docker run --rm --network noted-network \
    -v /home/logus/env/assets/noted/data/playwright_runs:/probes \
    --entrypoint python noted-test /probes/request_new_tool_probe.py 2>&1 | tee "$LOG" | tail -5
  RC=${PIPESTATUS[0]}

  # Classify outcome from probe's exit code:
  #   0 = PASS (workflow completed + turn-2 returned weather data)
  #   1 = FAIL (no workflow appeared after turn 1)
  #   2 = FAIL (workflow didn't terminate within timeout)
  #   3 = FAIL (workflow ended in non-completed status)
  #   4 = PARTIAL (workflow completed but turn 2 didn't return real data)
  WF_ID=$(grep -oE 'wf_[0-9a-z_]+' "$LOG" | head -1)
  STATUS=""
  if [ -n "$WF_ID" ]; then
    STATUS=$(curl -sS http://localhost:8123/api/workflows/$WF_ID 2>/dev/null | \
             python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('status','?'))" 2>/dev/null)
  fi
  FAIL_STEP=$(grep -oE '\[[0-9]\] [a-z_]+: failed' "$LOG" | head -1)

  if [ "$RC" = "0" ]; then
    PASS=$((PASS+1))
    SUMMARY+=("run $i: PASS  wf=$WF_ID")
    echo "  -> PASS"
  else
    FAIL=$((FAIL+1))
    SUMMARY+=("run $i: FAIL  rc=$RC  wf_status=$STATUS  failed_at=$FAIL_STEP")
    echo "  -> FAIL  rc=$RC  wf_status=$STATUS  failed_at=$FAIL_STEP"
  fi
  echo
done

echo
echo "=========================="
echo "PASS RATE: $PASS / $N"
echo "FAIL RATE: $FAIL / $N"
echo "=========================="
for line in "${SUMMARY[@]}"; do echo "$line"; done
echo
echo "Logs at $LOGDIR/"

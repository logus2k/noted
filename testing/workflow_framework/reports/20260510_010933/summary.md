# Workflow framework test run

Generated 2026-05-10T01:09:33+00:00

## Overall: 8/12 (67%)

| Scenario | API family | Pass | Fail | Avg duration (s) | First failed step | First failure tail |
|---|---|---|---|---|---|---|
| github_issue | code_hosting | 3 | 0 | 33.4 |  |  |
| open_meteo | weather | 3 | 0 | 41.4 |  |  |
| sapo_weather | weather | 2 | 1 | 49.4 | run_smoke_tests | ', ...}, {'D...{'Description': 'Nuvens com abertas', 'High': '16', 'Icon': 'http://imgs.sapo.pt/meteo/04.gif', 'Low': '8 |
| wikipedia_summary | reference | 0 | 3 | 90.7 | run_smoke_tests | edia_summary/venv/bin/python', 'tool.py'], returncode=1, stdout=b'', stderr=b'Error: API request failed with status 403. |

## Per-trial detail

### ✓ `github_issue` trial 1 — completed
- workflow_id: `wf_1778374697059_5f44bedb`
- duration: 32.04s · smoke_rewinds: 0
- probe: PASS

### ✓ `github_issue` trial 2 — completed
- workflow_id: `wf_1778374733099_6e50d168`
- duration: 36.03s · smoke_rewinds: 0
- probe: PASS

### ✓ `github_issue` trial 3 — completed
- workflow_id: `wf_1778374773139_753050d7`
- duration: 32.02s · smoke_rewinds: 0
- probe: PASS

### ✓ `open_meteo` trial 1 — completed
- workflow_id: `wf_1778374809179_c7eb3d36`
- duration: 44.04s · smoke_rewinds: 0
- probe: PASS

### ✓ `open_meteo` trial 2 — completed
- workflow_id: `wf_1778374857235_fd106a7d`
- duration: 36.03s · smoke_rewinds: 0
- probe: PASS

### ✓ `open_meteo` trial 3 — completed
- workflow_id: `wf_1778374897285_2fec2f3b`
- duration: 44.03s · smoke_rewinds: 0
- probe: PASS

### ✓ `sapo_weather` trial 1 — completed
- workflow_id: `wf_1778374945343_b3e24c69`
- duration: 32.03s · smoke_rewinds: 0
- probe: PASS

### ✗ `sapo_weather` trial 2 — suspended
- workflow_id: `wf_1778374981403_f837230f`
- duration: 88.07s · smoke_rewinds: 2
- failed_step: `run_smoke_tests`
- failed_tail: `', ...}, {'D...{'Description': 'Nuvens com abertas', 'High': '16', 'Icon': 'http://imgs.sapo.pt/meteo/04.gif', 'Low': '8', ...}, ...]})  smoke.py:38: AssertionError =========================== short test summary info ============================ FAILED smoke.py::test_successful_weather_fetch - Asser`

### ✓ `sapo_weather` trial 3 — completed
- workflow_id: `wf_1778375069476_b229c709`
- duration: 28.03s · smoke_rewinds: 0
- probe: PASS

### ✗ `wikipedia_summary` trial 1 — suspended
- workflow_id: `wf_1778375101536_a7175740`
- duration: 84.07s · smoke_rewinds: 2
- failed_step: `run_smoke_tests`
- failed_tail: `edia_summary/venv/bin/python', 'tool.py'], returncode=1, stdout=b'', stderr=b'Error: API request failed with status 403.\n').returncode  smoke.py:28: AssertionError =========================== short test summary info ============================ FAILED smoke.py::test_successful_summary_retrieval - A`

### ✗ `wikipedia_summary` trial 2 — suspended
- workflow_id: `wf_1778375185602_40f1ebc0`
- duration: 96.09s · smoke_rewinds: 2
- failed_step: `run_smoke_tests`
- failed_tail: `od...a from Wikipedia API: 403 Client Error: Forbidden for url: https://en.wikipedia.org/api/rest_v1/page/summary/Lisbon\n').returncode  smoke.py:28: AssertionError =========================== short test summary info ============================ FAILED smoke.py::test_successful_summary_retrieval - A`

### ✗ `wikipedia_summary` trial 3 — suspended
- workflow_id: `wf_1778375281700_1aaa88ce`
- duration: 92.07s · smoke_rewinds: 2
- failed_step: `run_smoke_tests`
- failed_tail: `od...equest failed with status 403. Details: Forbidden for url: https://en.wikipedia.org/api/rest_v1/page/summary/Lisbon\n').returncode  smoke.py:32: AssertionError =========================== short test summary info ============================ FAILED smoke.py::test_successful_summary_retrieval - A`


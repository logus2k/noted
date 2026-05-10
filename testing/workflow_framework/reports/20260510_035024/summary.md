# Workflow framework test run

Generated 2026-05-10T03:50:24+00:00

## Overall: 12/15 (80%)

| Scenario | API family | Pass | Fail | Avg duration (s) | First failed step | First failure tail |
|---|---|---|---|---|---|---|
| github_issue | code_hosting | 3 | 0 | 30.0 |  |  |
| open_meteo | weather | 3 | 0 | 34.0 |  |  |
| pokemon_lookup | reference | 0 | 3 | 84.4 | run_smoke_tests |   where False = isinstance({'pokemon_names': ['bulbasaur', 'ivysaur', 'venusaur', 'charmander', 'charmeleon', 'charizard |
| sapo_weather | weather | 3 | 0 | 34.0 |  |  |
| wikipedia_summary | reference | 3 | 0 | 35.3 |  |  |

## Per-trial detail

### ✓ `github_issue` trial 1 — completed
- workflow_id: `wf_1778384316781_c4dfdba9`
- duration: 28.69s · smoke_rewinds: 0
- probe: PASS

### ✓ `github_issue` trial 2 — completed
- workflow_id: `wf_1778384349611_74bb1e8b`
- duration: 32.64s · smoke_rewinds: 0
- probe: PASS

### ✓ `github_issue` trial 3 — completed
- workflow_id: `wf_1778384386374_296ac561`
- duration: 28.66s · smoke_rewinds: 0
- probe: PASS

### ✓ `open_meteo` trial 1 — completed
- workflow_id: `wf_1778384419143_97e324c2`
- duration: 32.66s · smoke_rewinds: 0
- probe: PASS

### ✓ `open_meteo` trial 2 — completed
- workflow_id: `wf_1778384455930_af878b0e`
- duration: 36.66s · smoke_rewinds: 0
- probe: PASS

### ✓ `open_meteo` trial 3 — completed
- workflow_id: `wf_1778384496714_0e318032`
- duration: 32.66s · smoke_rewinds: 0
- probe: PASS

### ✗ `pokemon_lookup` trial 1 — suspended
- workflow_id: `wf_1778384533504_7ec0ad70`
- duration: 114.59s · smoke_rewinds: 2
- failed_step: `run_smoke_tests`
- failed_tail: `  where False = isinstance({'pokemon_names': ['bulbasaur', 'ivysaur', 'venusaur', 'charmander', 'charmeleon', 'charizard', ...]}, list)  smoke.py:35: AssertionError =========================== short test summary info ============================ FAILED smoke.py::test_successful_index_lookup_no_name `

### ✗ `pokemon_lookup` trial 2 — suspended
- workflow_id: `wf_1778384648094_6b0a13a1`
- duration: 93.93s · smoke_rewinds: 2
- failed_step: `validate_smoke_contract`
- failed_tail: `ke.py is missing asserts for output keys ['types'] that the acceptance_criteria pin. Add asserts that check for these keys in the tool's output. asserted=[] acceptance_criteria=['Input is a JSON object with an optional string field named name.', "When name is provided, successful output JSON contain`

### ✗ `pokemon_lookup` trial 3 — completed
- workflow_id: `wf_1778384742027_f63d5bd7`
- duration: 44.65s · smoke_rewinds: 0
- probe: FAIL · verify_tool_round_trip preview missing key(s): ['types']

### ✓ `sapo_weather` trial 1 — completed
- workflow_id: `wf_1778384790819_d4ff8c2c`
- duration: 36.65s · smoke_rewinds: 0
- probe: PASS

### ✓ `sapo_weather` trial 2 — completed
- workflow_id: `wf_1778384831617_6a21ede6`
- duration: 32.64s · smoke_rewinds: 0
- probe: PASS

### ✓ `sapo_weather` trial 3 — completed
- workflow_id: `wf_1778384869025_ac3b13d5`
- duration: 32.65s · smoke_rewinds: 0
- probe: PASS

### ✓ `wikipedia_summary` trial 1 — completed
- workflow_id: `wf_1778384905826_e5bffce6`
- duration: 32.65s · smoke_rewinds: 0
- probe: PASS

### ✓ `wikipedia_summary` trial 2 — completed
- workflow_id: `wf_1778384942623_7fdfb43b`
- duration: 36.66s · smoke_rewinds: 0
- probe: PASS

### ✓ `wikipedia_summary` trial 3 — completed
- workflow_id: `wf_1778384983431_4b6a3976`
- duration: 36.65s · smoke_rewinds: 0
- probe: PASS


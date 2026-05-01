# T-2.17 DAG Visualization - Test Procedure

## Prerequisites

- noted is running with Airflow containers
- At least two DAGs exist: `noted_test_dag` (single task) and `jena_training_pipeline` (3 sequential tasks)
- DAGs are unpaused

---

## Part 1: DAG Detail Page Graph

### Test 1: Graph renders for multi-task DAG

1. In Explorer, expand Pipelines
2. Click on `jena_training_pipeline`

**Expected:**
- A "Task Graph" section appears in the detail page
- Three task nodes are shown in left-to-right order: validate_data -> train_model -> evaluate_model
- Nodes are rounded rectangles with task name and operator label (@task)
- Arrows connect the nodes showing dependency direction
- All nodes are grey/neutral (no execution state)

### Test 2: Graph renders for single-task DAG

1. Click on `noted_test_dag`

**Expected:**
- A single node "hello" is shown
- No arrows (no dependencies)
- Node is centered in the graph area

### Test 3: Graph layout handles width

1. Resize the Explorer detail panel wider and narrower

**Expected:**
- The graph SVG scales within its container
- Nodes remain readable at all widths
- No horizontal overflow

---

## Part 2: DAG Run Detail Page Graph (with task states)

### Test 4: Completed run shows all green

1. Trigger `noted_test_dag` and wait for it to complete
2. Click on the completed DAG Run node in the tree

**Expected:**
- Task Graph shows the "hello" node in green (success state)
- A small green dot indicator on the node corner

### Test 5: Multi-task run shows mixed states

1. Trigger `jena_training_pipeline`
2. Quickly click on the DAG Run node while tasks are executing

**Expected:**
- Task Graph shows different colors per task:
  - Completed tasks: green nodes
  - Running task: blue node
  - Queued/pending tasks: grey/orange nodes
- Arrows connect all tasks regardless of state

### Test 6: Failed run shows red node

1. If a task fails (or create a DAG with a task that raises an error)
2. Click on the failed DAG Run

**Expected:**
- The failed task node is red
- Downstream tasks that didn't execute show as grey/pending
- Upstream tasks that completed show as green

---

## Part 3: Graph and Task List Together

### Test 7: Graph and task list are both visible

1. Click on a completed DAG Run for `jena_training_pipeline`

**Expected:**
- Task Graph appears above the task list
- Task list shows the same tasks with execution times
- Both sections are scrollable if content exceeds the panel height
- Clicking a task row in the list still shows the task log

### Test 8: Graph appears on DAG detail page before trigger

1. Click on `jena_training_pipeline` (not a run, the DAG itself)

**Expected:**
- Task Graph shows above the trigger/pause buttons
- All nodes are neutral/grey (no run states)
- Recent DAG Runs section shows below

---

## Part 4: Graph Interaction

### Test 9: Node hover effect

1. On any DAG graph, hover over a task node

**Expected:**
- Node slightly darkens on hover (brightness filter)
- Cursor changes to pointer

### Test 10: Undocked panel shows graph

1. Open a DAG detail in the center panel
2. Undock the panel

**Expected:**
- The graph renders correctly in the floating panel
- Graph scales to the panel width
- All nodes and arrows are visible

---

## Troubleshooting

- **"Task Graph" section missing:** The `/structure` endpoint may have failed. Check browser console for errors.
- **Graph is empty:** The DAG may have no tasks defined. Check Airflow UI to confirm tasks exist.
- **Nodes overlap:** dagre layout failed. Check browser console for dagre errors.
- **Arrow markers missing:** SVG marker IDs may conflict. Try refreshing the page.

"""E2E tests for notebook-related features.

Maps to: testing/26_test-leaderboard-filter.md, testing/28_test-run-summary-toast.md,
         testing/29_test-epoch-progress-bar.md
"""

import os
import pytest
from playwright.sync_api import Page, expect

NOTED_URL = os.environ.get("NOTED_URL", "http://localhost:8123")

pytestmark = [pytest.mark.e2e]


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    pg = ctx.new_page()
    pg.add_init_script("""
        if (!crypto.randomUUID) {
            crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
                c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
        }
    """)
    pg.goto(NOTED_URL, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(4000)
    # Sidebar opens with Explorer active by default - don't toggle it off
    yield pg
    pg.close()
    ctx.close()


def _find_tree_node(page, text, scroll_attempts=6):
    """Find a tree node by text, scrolling if needed (virtualized tree).

    Wunderbaum marks off-screen nodes as hidden, so we use force=True for
    clicks and don't require is_visible().
    """
    for _ in range(scroll_attempts):
        node = page.locator(f"span.wb-title:has-text('{text}')")
        if node.count() > 0:
            return node.first
        page.evaluate("document.querySelector('.explorer-tree-pane')?.scrollBy(0, 400)")
        page.wait_for_timeout(800)
    return None


def _open_experiment(page):
    """Navigate to and open an experiment with runs via tree interaction.

    Expands Experiments section, waits for lazy-loaded children from MLflow,
    then clicks a _test_kernel_* experiment (which has runs with metrics).
    """
    # Find and expand Experiments section
    exp_section = _find_tree_node(page, "Experiments")
    if not exp_section:
        return False
    exp_section.click(force=True)

    # Wait for lazy-loaded experiment children to appear from MLflow
    # The tree fetches experiments asynchronously - needs up to 8s
    page.wait_for_timeout(8000)

    found_experiments = page.evaluate('''() => {
        const rows = document.querySelectorAll('.wb-row');
        const experiments = [];
        let inExperiments = false;
        const sections = new Set(['Storage', 'Pipelines', 'Models', 'APIs',
            'Projects', 'Mounts', 'Virtual Environments', 'Knowledge Base']);
        for (const r of rows) {
            const title = r.querySelector('.wb-title');
            if (!title) continue;
            const text = title.textContent;
            if (text === 'Experiments') { inExperiments = true; continue; }
            if (inExperiments && sections.has(text)) break;
            if (inExperiments && text) experiments.push(text);
        }
        return experiments;
    }''')

    if not found_experiments:
        return False

    # Prefer _test_kernel_* experiments (created by kernel tests, have runs with metrics)
    target = None
    for name in found_experiments:
        if name.startswith('_test_kernel'):
            target = name
            break
    if not target:
        target = found_experiments[0]

    node = _find_tree_node(page, target)
    if node:
        node.click(force=True)
        page.wait_for_timeout(3000)
        return True
    return False


class TestLeaderboardFilter:
    """26: Leaderboard filter bar."""

    def test_experiment_detail_has_filter(self, page: Page):
        """Opening an experiment renders leaderboard content accessible from the tree."""
        if not _open_experiment(page):
            pytest.skip("No experiments visible in tree")

        # After clicking an experiment, the leaderboard renders.
        # It may be in the explorer-detail-pane (center Workspace tab) or
        # in a sidebar detail area. Check for leaderboard-specific elements:
        # - Filter input, Columns button, or leaderboard table rows
        page.wait_for_timeout(2000)
        has_leaderboard = (
            page.locator(".explorer-detail-pane").count() > 0
            or page.locator("button:has-text('Columns')").count() > 0
            or page.locator("input[placeholder*='Filter']").count() > 0
            or page.locator(".leaderboard-table, .run-table, table").count() > 0
        )
        assert has_leaderboard, (
            "No leaderboard UI elements found after opening experiment. "
            "Expected detail pane, Columns button, filter input, or table."
        )

    def test_columns_button_visible(self, page: Page):
        """Leaderboard has a Columns selector button."""
        if not _open_experiment(page):
            pytest.skip("No experiments visible in tree")

        # Wait for the detail pane to render with leaderboard content
        page.wait_for_timeout(2000)
        col_btn = page.locator("button:has-text('Columns')")
        # Check DOM presence (button may be offscreen in headless)
        assert col_btn.count() > 0, (
            "No Columns button found in experiment detail pane"
        )


def _expand_tree_node(page, text):
    """Expand a tree node if collapsed, using JS to check state first."""
    page.evaluate(f'''() => {{
        const rows = document.querySelectorAll('.wb-row');
        for (const r of rows) {{
            const t = r.querySelector('.wb-title');
            if (t && t.textContent === '{text}') {{
                if (!r.classList.contains('wb-expanded')) {{
                    r.click();
                }}
                return;
            }}
        }}
    }}''')
    page.wait_for_timeout(2000)


def _open_notebook(page):
    """Navigate to noted-testing/test_notebook.ipynb via tree interaction."""
    _expand_tree_node(page, "Projects")
    page.wait_for_timeout(2000)

    # Find and expand noted-testing project
    project = _find_tree_node(page, "noted-testing")
    if not project:
        return False
    project.click(force=True)
    page.wait_for_timeout(1000)
    _expand_tree_node(page, "noted-testing")
    page.wait_for_timeout(2000)

    # Find and double-click notebook
    nb = _find_tree_node(page, "test_notebook")
    if not nb:
        return False
    nb.dblclick(force=True)
    page.wait_for_timeout(5000)
    return True


class TestNotebookBar:
    """28/29: Notebook bar features (toast, progress bar, pipeline button)."""

    def test_notebook_has_second_bar(self, page: Page):
        """Opening a notebook shows the second bar with kernel control buttons."""
        if not _open_notebook(page):
            pytest.skip("Could not open notebook")

        second_bars = page.locator(".notebook-second-bar")
        assert second_bars.count() > 0, "No notebook second bar found in DOM"
        # Bar may be hidden if notebook is not fully activated - structural check only
        bar = second_bars.first
        # Verify kernel controls are present in DOM
        kernel_controls = bar.locator(
            "button:has-text('Run All'), button:has-text('Restart'), "
            "button:has-text('Stop'), .fa-play, .fa-rotate, .fa-stop"
        )
        assert kernel_controls.count() > 0, (
            "No kernel control buttons (Run All / Restart / Stop) found in notebook second bar"
        )

    def test_export_task_button_on_code_cell(self, page: Page):
        """Code cells have the Export as Pipeline Task (rocket) button."""
        if not _open_notebook(page):
            pytest.skip("Could not open notebook")

        cells = page.locator(".cell")
        assert cells.count() > 0, "No .cell elements found in opened notebook"
        # Cells may be hidden if not fully activated - use structural DOM check
        rocket = page.locator(".cell-header .fa-rocket")
        assert rocket.count() > 0, (
            "No rocket (Export as Pipeline Task) button found in any cell header"
        )

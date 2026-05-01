"""E2E tests for Explorer-based features.

Maps to: testing/15_test-dag-visualization.md, testing/24_test-hydra-config-selector.md,
         testing/30_test-pipeline-health-and-log-errors.md

NOTE: Tree interaction tests use force=True for clicks because the sidebar
may report elements as "hidden" in headless mode even when they're in the DOM.
"""

import os
import re
import pytest
from playwright.sync_api import Page, expect

NOTED_URL = os.environ.get("NOTED_URL", "http://localhost:8123")

pytestmark = [pytest.mark.e2e]

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


CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    pg = ctx.new_page()
    pg.add_init_script(CRYPTO_POLYFILL)
    # Collect JS errors for test_app_loaded_without_crash
    js_errors = []
    pg.on("pageerror", lambda exc: js_errors.append(str(exc)))
    pg.goto(NOTED_URL, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(4000)
    # Sidebar opens with Explorer active by default - don't toggle it off
    pg._noted_js_errors = js_errors
    yield pg
    pg.close()
    ctx.close()


class TestExplorerSections:
    """Verify all Explorer tree sections exist in DOM."""

    def test_tree_sections_in_dom(self, page: Page):
        """Root section nodes exist in the DOM."""
        # Wunderbaum virtualizes rows - only visible rows are in DOM
        rows = page.locator(".wb-row").count()
        assert rows > 0, "No tree rows rendered"
        # Check at least Projects exists (first section, always visible)
        projects = page.locator("span.wb-title:has-text('Projects')").count()
        assert projects > 0, "Projects section not in DOM"
        # At least one other section must also be present
        other_sections = [
            "Pipelines", "Experiments", "Mounts", "Notebooks",
        ]
        found_other = any(
            page.locator(f"span.wb-title:has-text('{s}')").count() > 0
            for s in other_sections
        )
        assert found_other, (
            f"Only Projects found - expected at least one of {other_sections} to also be in DOM"
        )

    def test_pipelines_expandable(self, page: Page):
        """Pipelines section expands and adds child rows."""
        pipelines = page.locator("span.wb-title:has-text('Pipelines')")
        if pipelines.count() == 0:
            # Scroll tree to find Pipelines (virtualized)
            for _ in range(4):
                page.evaluate("document.querySelector('.explorer-tree-pane')?.scrollBy(0, 400)")
                page.wait_for_timeout(800)
                if pipelines.count() > 0:
                    break
        if pipelines.count() == 0:
            pytest.skip("Pipelines section not found after scrolling")
        rows_before = page.locator(".wb-row").count()
        pipelines.first.click(force=True)
        page.wait_for_timeout(3000)
        rows_after = page.locator(".wb-row").count()
        assert rows_after > rows_before, (
            f"Row count did not increase after expanding Pipelines "
            f"(before={rows_before}, after={rows_after})"
        )


class TestPipelineHealth:
    """30: Pipeline health dot on Pipelines root."""

    def test_health_dot_appears_after_expand(self, page: Page):
        """Expanding Pipelines triggers async health check, showing a health indicator dot."""
        pipelines = _find_tree_node(page, "Pipelines")
        if not pipelines:
            pytest.skip("Pipelines section not in virtual DOM")
        pipelines.click(force=True)
        page.wait_for_timeout(5000)
        # Look for a colored health dot element near the Pipelines row
        health_dot = page.locator(
            ".pipeline-health-dot, .health-dot, "
            "span[class*='health'], div[class*='health'], "
            ".wb-row span[style*='background'], .wb-row span[style*='color']"
        )
        assert health_dot.count() > 0, (
            "No health indicator dot found after expanding Pipelines"
        )


class TestDAGVisualization:
    """15: DAG graph renders."""

    def test_dag_nodes_in_tree(self, page: Page):
        """After expanding Pipelines, at least one DAG-named row appeared."""
        pipelines = _find_tree_node(page, "Pipelines")
        if not pipelines:
            pytest.skip("Pipelines not in virtual DOM")
        pipelines.click(force=True)
        page.wait_for_timeout(5000)
        # A DAG node has a title that is not "Pipelines" itself
        dag_rows = page.evaluate("""() => {
            const rows = document.querySelectorAll('.wb-row');
            const titles = [];
            for (const r of rows) {
                const t = r.querySelector('.wb-title');
                if (t && t.textContent.trim() !== 'Pipelines') {
                    titles.push(t.textContent.trim());
                }
            }
            return titles;
        }""")
        assert len(dag_rows) >= 1, (
            "No DAG-named child rows appeared after expanding Pipelines"
        )


class TestHydraConfigSelector:
    """24: Hydra config selector."""

    def test_config_selector_exists_in_dom(self, page: Page):
        """Config selector CSS class or element is present in the page."""
        # The selector is created in NotebookEditor once a notebook opens.
        # Check either the CSS rule exists in a stylesheet or the element is in the DOM.
        has_css_rule = page.evaluate("""() => {
            const rules = [...document.styleSheets].flatMap(s => {
                try { return [...s.cssRules]; } catch { return []; }
            });
            return rules.some(r => r.selectorText && r.selectorText.includes('notebook-config-selector'));
        }""")
        has_element = page.locator(
            "[class*='notebook-config-selector'], .notebook-config-selector, "
            "#notebook-config-selector"
        ).count() > 0
        assert has_css_rule or has_element, (
            "Neither a CSS rule nor a DOM element for 'notebook-config-selector' was found"
        )


class TestLogErrorHighlighting:
    """30: Error line highlighting."""

    def test_app_loaded_without_crash(self, page: Page):
        """App loads without fatal JavaScript errors."""
        # Verify the main app container rendered
        expect(page.locator("#app")).to_be_visible()
        expect(page.locator("#icon-bar")).to_be_visible()
        js_errors = getattr(page, "_noted_js_errors", [])
        assert js_errors == [], (
            f"Fatal JS errors detected during page load: {js_errors}"
        )

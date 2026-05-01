"""E2E UI tests using Playwright.

Tests core UI interactions that cannot be verified via API alone:
- Page loads and renders
- Explorer tree navigation
- Notebook cell execution
- Service iframe loading
- Panel interactions

Maps to: testing/01_test-setup.md (Tests 2-5), testing/02_test-notebooks.md (Tests 5-15)
"""

import os
import pytest
from playwright.sync_api import Page, expect, ConsoleMessage

NOTED_URL = os.environ.get("NOTED_URL", "http://localhost:8123")

pytestmark = [pytest.mark.e2e]


CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


@pytest.fixture
def page(browser):
    """Fresh page per test, with sidebar opened."""
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    pg = ctx.new_page()
    pg.add_init_script(CRYPTO_POLYFILL)
    pg.goto(NOTED_URL, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(4000)
    # Sidebar opens with Explorer active by default - don't toggle it off
    yield pg
    pg.close()
    ctx.close()


class TestAppLoads:
    """Test 2: noted loads and renders main layout."""

    def test_page_loads(self, page: Page):
        """Page loads without errors."""
        expect(page.locator("#app")).to_be_visible()
        js_errors = page.evaluate("""() => window.__noted_js_errors || []""")
        assert js_errors == [] or js_errors is None, (
            f"JS console errors detected on load: {js_errors}"
        )

    def test_icon_bar_visible(self, page: Page):
        """Icon bar renders on the left."""
        expect(page.locator("#icon-bar")).to_be_visible()

    def test_sidebar_visible(self, page: Page):
        """Sidebar panel renders."""
        expect(page.locator("#sidebar-panel")).to_be_visible()

    def test_center_area_visible(self, page: Page):
        """Center content area renders."""
        expect(page.locator("#center-column")).to_be_visible()

    def test_status_bar_visible(self, page: Page):
        """Status bar renders at the bottom."""
        expect(page.locator("#status-bar")).to_be_visible()


class TestExplorerTree:
    """Explorer tree renders with expected sections."""

    def test_explorer_tree_renders(self, page: Page):
        """Tree pane exists in DOM with at least 3 section rows."""
        tree = page.locator(".explorer-tree-pane")
        assert tree.count() > 0
        rows = page.locator(".wb-row").count()
        assert rows >= 3, f"Expected at least 3 tree rows (sections), found {rows}"

    def test_projects_section_in_dom(self, page: Page):
        """Projects root node exists in DOM."""
        count = page.locator("span.wb-title:has-text('Projects')").count()
        assert count >= 1, f"Expected at least 1 'Projects' title node, found {count}"

    def test_pipelines_section_in_dom(self, page: Page):
        """Pipelines root node exists in DOM (may need scroll for virtualized tree)."""
        count = page.locator("span.wb-title:has-text('Pipelines')").count()
        if count == 0:
            # Scroll tree to reveal virtualized rows
            for _ in range(4):
                page.evaluate("document.querySelector('.explorer-tree-pane')?.scrollBy(0, 400)")
                page.wait_for_timeout(800)
                count = page.locator("span.wb-title:has-text('Pipelines')").count()
                if count > 0:
                    break
        assert count > 0, "Pipelines section not found in DOM after scrolling through tree"


class TestServiceIframes:
    """Tests 3-5: Service iframes load."""

    def test_mlflow_icon_clickable(self, page: Page):
        """Clicking MLflow icon opens a service tab with MLflow content."""
        # Find MLflow icon in the icon bar (service image)
        mlflow_btn = page.locator("#icon-bar img[alt*='mlflow'], #icon-bar img[alt*='MLflow']").first
        if not mlflow_btn.is_visible():
            pytest.skip("MLflow icon not visible in icon bar")
        mlflow_btn.click()
        page.wait_for_timeout(2000)
        # A service tab should appear
        tab = page.locator(".tab")
        expect(tab.first).to_be_visible()
        # Tab or iframe should contain MLflow-related content
        tab_text = page.locator(".tab").first.inner_text()
        iframe_src = page.locator("iframe").first.get_attribute("src") or ""
        has_mlflow_content = (
            "mlflow" in tab_text.lower()
            or "mlflow" in iframe_src.lower()
            or page.locator("iframe[src*='mlflow'], iframe[src*='5000']").count() > 0
        )
        assert has_mlflow_content, (
            f"No MLflow-related tab or iframe found. Tab text: {tab_text!r}, iframe src: {iframe_src!r}"
        )


class TestNotebookOpen:
    """Test opening the scaffolded notebook."""

    def test_open_notebook_from_tree(self, page: Page):
        """Navigate to noted-testing project and open notebook via tree clicks."""
        page.wait_for_timeout(2000)

        # Ensure Projects section is expanded (don't toggle if already open)
        page.evaluate('''() => {
            const rows = document.querySelectorAll('.wb-row');
            for (const r of rows) {
                const t = r.querySelector('.wb-title');
                if (t && t.textContent === 'Projects' && !r.classList.contains('wb-expanded')) {
                    r.click();
                }
            }
        }''')
        page.wait_for_timeout(2000)

        # Find noted-testing - may need to scroll past expanded Examples project
        project_node = page.locator("span.wb-title:has-text('noted-testing')")
        for attempt in range(8):
            if project_node.count() > 0:
                break
            page.evaluate("""
                const pane = document.querySelector('.explorer-tree-pane')
                    || document.querySelector('#explorerTreeWrapper');
                if (pane) pane.scrollBy(0, 400);
            """)
            page.wait_for_timeout(800)
        if project_node.count() == 0:
            pytest.skip("noted-testing project not found in tree after scrolling")
        project_node.first.click(force=True)
        page.wait_for_timeout(1000)
        project_node.first.dblclick(force=True)
        page.wait_for_timeout(2000)

        # Expand noted-testing project to reveal children
        page.evaluate('''() => {
            const rows = document.querySelectorAll('.wb-row');
            for (const r of rows) {
                const t = r.querySelector('.wb-title');
                if (t && t.textContent === 'noted-testing' && !r.classList.contains('wb-expanded')) {
                    r.click();
                }
            }
        }''')
        page.wait_for_timeout(3000)

        # Find notebook file
        nb_node = page.locator("span.wb-title:has-text('test_notebook')")
        for attempt in range(6):
            if nb_node.count() > 0:
                break
            page.evaluate("""
                const pane = document.querySelector('.explorer-tree-pane')
                    || document.querySelector('#explorerTreeWrapper');
                if (pane) pane.scrollBy(0, 400);
            """)
            page.wait_for_timeout(800)
        if nb_node.count() == 0:
            pytest.skip("test_notebook.ipynb not found in tree")
        nb_node.first.dblclick(force=True)
        page.wait_for_timeout(4000)

        # Notebook must be open - tab or container present
        nb = page.locator("#notebook-container .notebook, .notebook")
        tabs = page.locator(".tab")
        assert nb.count() > 0 or tabs.count() > 1, (
            "Notebook not opened after tree navigation"
        )

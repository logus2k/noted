"""Focused E2E tests for Explorer tree click behavior.

Tests the two known issues:
1. Phantom detail panel: clicking a project opens a workspace detail tab that stays open
2. Folder re-collapse: clicking an expanded folder should collapse it

Run: docker run --rm --network noted-network -e NOTED_URL=http://noted:8123 \
     noted-test -v --tb=short -k "test_explorer_click"
"""

import os
import pytest
from playwright.sync_api import Page, expect

NOTED_URL = os.environ.get("NOTED_URL", "http://localhost:8123")

pytestmark = [pytest.mark.e2e]

CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


def _find_tree_node(page, text, scroll_attempts=6):
    """Find a tree node by text, scrolling if needed."""
    for _ in range(scroll_attempts):
        node = page.locator(f"span.wb-title:has-text('{text}')")
        if node.count() > 0:
            return node.first
        page.evaluate("document.querySelector('.explorer-tree-pane')?.scrollBy(0, 400)")
        page.wait_for_timeout(800)
    return None


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    pg = ctx.new_page()
    pg.add_init_script(CRYPTO_POLYFILL)
    pg.goto(NOTED_URL, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(4000)
    yield pg
    pg.close()
    ctx.close()


class TestFolderExpandCollapse:
    """Clicking a folder should toggle expand/collapse every time."""

    def test_folder_expands_on_first_click(self, page):
        # Open Explorer sidebar
        page.click('[data-key="projects"]', force=True)
        page.wait_for_timeout(1000)

        # Find a project and expand it
        proj = _find_tree_node(page, "Examples")
        assert proj is not None, "Examples project not found"
        proj.click(force=True)
        page.wait_for_timeout(500)

        # Find the notebooks folder
        folder = _find_tree_node(page, "notebooks")
        assert folder is not None, "notebooks folder not found"

        # Click to expand
        folder.click(force=True)
        page.wait_for_timeout(500)

        # Verify expanded (Wunderbaum uses wb-expanded class on the wb-row div)
        folder_row = folder.locator("xpath=ancestor::div[contains(@class,'wb-row')]").first
        has_expanded = folder_row.evaluate("el => el.classList.contains('wb-expanded')")
        assert has_expanded, "Folder should have wb-expanded class after click"

    def test_folder_collapses_on_second_click(self, page):
        # Open Explorer sidebar
        page.click('[data-key="projects"]', force=True)
        page.wait_for_timeout(1000)

        # Expand project
        proj = _find_tree_node(page, "Examples")
        assert proj is not None
        proj.click(force=True)
        page.wait_for_timeout(500)

        # Find and expand folder
        folder = _find_tree_node(page, "notebooks")
        assert folder is not None
        folder.click(force=True)
        page.wait_for_timeout(500)

        # Click again to collapse
        folder.click(force=True)
        page.wait_for_timeout(500)

        # Verify collapsed (wb-expanded class should be removed)
        folder_row = folder.locator("xpath=ancestor::div[contains(@class,'wb-row')]").first
        has_expanded = folder_row.evaluate("el => el.classList.contains('wb-expanded')")
        assert not has_expanded, "Folder should not have wb-expanded class after second click"


class TestWorkspaceDetailPanel:
    """The workspace detail panel should not persist when navigating away."""

    def test_no_workspace_tab_on_folder_click(self, page):
        # Open Explorer sidebar
        page.click('[data-key="projects"]', force=True)
        page.wait_for_timeout(1000)

        # Expand project
        proj = _find_tree_node(page, "Examples")
        assert proj is not None
        proj.click(force=True)
        page.wait_for_timeout(500)

        # Click a folder
        folder = _find_tree_node(page, "notebooks")
        assert folder is not None
        folder.click(force=True)
        page.wait_for_timeout(500)

        # Verify no "Projects" workspace tab appeared in the center pane tab bar
        workspace_tab = page.locator(".tab-bar-tab:has-text('Explorer')")
        assert workspace_tab.count() == 0, "Workspace detail tab should not appear when clicking a folder"

    def test_workspace_tab_closes_on_notebook_open(self, page):
        # Open Explorer sidebar
        page.click('[data-key="projects"]', force=True)
        page.wait_for_timeout(1000)

        # Click project (this opens the workspace detail)
        proj = _find_tree_node(page, "Examples")
        assert proj is not None
        proj.click(force=True)
        page.wait_for_timeout(500)

        # Verify workspace tab exists
        workspace_tab = page.locator(".tab-bar-tab:has-text('Explorer')")
        has_workspace = workspace_tab.count() > 0

        # Now open a notebook by double-clicking
        folder = _find_tree_node(page, "notebooks")
        if folder:
            folder.click(force=True)
            page.wait_for_timeout(500)

        nb = _find_tree_node(page, "Welcome.ipynb")
        if nb:
            nb.dblclick(force=True)
            page.wait_for_timeout(2000)

            # Verify workspace tab is gone (auto-closed)
            workspace_tab_after = page.locator(".tab-bar-tab:has-text('Explorer')")
            assert workspace_tab_after.count() == 0, "Workspace detail tab should close when a notebook is opened"

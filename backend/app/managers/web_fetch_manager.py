"""Persistent stealth browser for web fetching.

Uses Camoufox (anti-detect Firefox) as a long-running singleton.
The browser launches once at first use and stays warm for subsequent requests.
Session refreshes every 50 requests or 1 hour to prevent memory leaks and tracking.
Falls back to httpx if Camoufox is not available.
"""

import asyncio
import logging
import re
import time
import threading
import urllib.parse

logger = logging.getLogger(__name__)

# Session refresh thresholds
MAX_REQUESTS_PER_SESSION = 50
MAX_SESSION_AGE_SECONDS = 3600  # 1 hour


class StealthBrowser:
    """Singleton persistent browser for anti-detect web fetching."""

    def __init__(self):
        self._browser_manager = None
        self._browser = None
        self._page = None
        self._lock = threading.Lock()
        self._request_count = 0
        self._session_start = 0
        self._available = None  # None = not checked yet

    def _is_available(self) -> bool:
        """Check if Camoufox is installed (cached after first check)."""
        if self._available is None:
            try:
                from camoufox.sync_api import Camoufox
                self._available = True
            except ImportError:
                self._available = False
                logger.info("Camoufox not installed - web fetch will use httpx fallback")
        return self._available

    def _ensure_browser(self):
        """Start or refresh the browser if needed."""
        needs_refresh = (
            self._browser is None
            or self._request_count >= MAX_REQUESTS_PER_SESSION
            or (time.monotonic() - self._session_start) > MAX_SESSION_AGE_SECONDS
        )
        if not needs_refresh:
            return

        # Shut down existing session
        self._shutdown_browser()

        from camoufox.sync_api import Camoufox
        logger.info("Starting Camoufox browser (request_count=%d)", self._request_count)
        self._browser_manager = Camoufox(headless=True)
        self._browser = self._browser_manager.start()
        self._page = self._browser.new_page()
        self._request_count = 0
        self._session_start = time.monotonic()
        logger.info("Camoufox browser ready")

    def _shutdown_browser(self):
        """Stop the current browser session.

        Camoufox is a context manager (uses __enter__ / __exit__) — there is
        no public `.stop()` method. Calling .stop() raised AttributeError
        previously, leaving the underlying Playwright sync loop alive in
        the process; the next session-refresh `start()` then failed with
        "you are using Playwright Sync API inside the asyncio loop" because
        Playwright detected the orphan loop. Using __exit__ gives Camoufox
        the standard cleanup path.
        """
        if self._browser_manager:
            try:
                self._browser_manager.__exit__(None, None, None)
            except Exception as e:
                logger.warning("Error stopping Camoufox: %s", e)
            self._browser_manager = None
            self._browser = None
            self._page = None

    def fetch_sync(self, url: str) -> str:
        """Fetch a URL using the persistent browser. Thread-safe."""
        with self._lock:
            self._ensure_browser()
            self._page.goto(url, timeout=20000)
            self._page.wait_for_load_state("domcontentloaded")
            self._request_count += 1
            return self._page.content()

    def search_sync(self, query: str, top_n: int = 8) -> list[dict]:
        """Run a DuckDuckGo HTML search and return parsed result list.

        DDG's html.duckduckgo.com endpoint serves a JS-free results page,
        so we can scrape it deterministically. Each result is a `.result`
        block with `.result__a` (title link) and `.result__snippet`.
        Hrefs come wrapped as `//duckduckgo.com/l/?uddg=<encoded-real-url>`,
        so we unwrap the `uddg` param to get the real destination.
        """
        with self._lock:
            self._ensure_browser()
            search_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
            self._page.goto(search_url, timeout=20000)
            self._page.wait_for_load_state("domcontentloaded")
            self._request_count += 1

            results: list[dict] = []
            for el in self._page.query_selector_all(".result"):
                title_el = el.query_selector(".result__a")
                if not title_el:
                    continue
                title = (title_el.inner_text() or "").strip()
                href = title_el.get_attribute("href") or ""
                snippet_el = el.query_selector(".result__snippet")
                snippet = (snippet_el.inner_text() or "").strip() if snippet_el else ""
                results.append({
                    "title": title,
                    "url": _unwrap_ddg_url(href),
                    "snippet": snippet,
                })
                if len(results) >= top_n:
                    break
            return results

    def shutdown(self):
        """Shut down the browser. Call on application exit."""
        with self._lock:
            self._shutdown_browser()


# Module-level singleton
_instance = StealthBrowser()


def _html_to_text(html: str) -> str:
    """Strip HTML to readable text."""
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _unwrap_ddg_url(href: str) -> str:
    """Pull the real destination URL out of DDG's redirect wrapper."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        uddg = params.get("uddg")
        if uddg:
            return uddg[0]
    except Exception:
        pass
    return href


async def fetch_url(url: str, max_chars: int = 10000) -> str:
    """Fetch a URL and return its text content.

    Uses Camoufox (persistent anti-detect browser) if available,
    falls back to httpx otherwise.
    """
    if not url:
        return "Error: url is required"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    if _instance._is_available():
        try:
            loop = asyncio.get_event_loop()
            html = await loop.run_in_executor(None, _instance.fetch_sync, url)
            text = _html_to_text(html)
        except Exception as e:
            return f"Error fetching URL: {type(e).__name__}: {e}"
    else:
        try:
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                text = resp.text
                if "html" in resp.headers.get("content-type", ""):
                    text = _html_to_text(text)
        except Exception as e:
            return f"Error fetching URL: {type(e).__name__}: {e}"

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[Truncated at {max_chars} chars. Use max_chars to increase.]"

    return f"URL: {url}\nContent ({len(text)} chars):\n\n{text}"


async def web_search(query: str, top_n: int = 8) -> str:
    """Run a web search via DuckDuckGo HTML and return formatted results.

    Returns a numbered text block ready to feed back to the LLM. Each
    result has title, url, snippet. Camoufox is required — if it's not
    installed we surface that explicitly rather than silently degrading.
    """
    if not query or not query.strip():
        return "Error: query is required"
    top_n = max(1, min(int(top_n), 25))

    if not _instance._is_available():
        return "Error: web search requires Camoufox; not installed in this environment"

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _instance.search_sync, query, top_n)
    except Exception as e:
        return f"Error running web search: {type(e).__name__}: {e}"

    if not results:
        return f"No web results for: {query}"

    lines = [f"Web search results for {query!r} ({len(results)} hits):", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        if r.get("url"):
            lines.append(f"   URL: {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def shutdown():
    """Shut down the persistent browser. Call on app exit."""
    _instance.shutdown()

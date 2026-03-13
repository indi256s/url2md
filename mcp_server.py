"""url2md MCP server — exposes url2md as a tool for Claude Desktop and other MCP clients."""

import logging
import sys

logging.disable(logging.CRITICAL)

from mcp.server.fastmcp import FastMCP
from scrapling import Fetcher
from url2md import (
    normalize_url, fetch_page, extract_title, extract_page, crawl,
    FetchError, ExtractionError,
)

mcp = FastMCP("url2md")


@mcp.tool()
def url2md(url: str, raw: bool = False, selector: str | None = None,
           timeout: int = 30, depth: int = 0, max_pages: int = 20) -> str:
    """Fetch a URL and convert its content to clean markdown.

    Args:
        url: URL to fetch (https:// added automatically if missing)
        raw: Skip smart extraction, convert the full body
        selector: CSS selector for content container
        timeout: Request timeout in seconds
        depth: Follow internal links N levels deep (0 = single page)
        max_pages: Max pages to fetch during crawl
    """
    try:
        url = normalize_url(url)
        fetcher = Fetcher()

        if depth > 0:
            return crawl(fetcher, url, depth, max_pages, timeout, selector, raw)

        resp = fetch_page(fetcher, url, timeout)
        title = extract_title(resp)
        page_md = extract_page(resp, selector, raw)

        parts = []
        if title:
            parts.append(f"# {title}\n")
        final_url = resp.url if hasattr(resp, "url") else url
        parts.append(f"> Source: {final_url}\n")
        parts.append(page_md)
        return "\n".join(parts)
    except (FetchError, ExtractionError) as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")

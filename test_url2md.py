"""Tests for url2md import safety and MCP tool behavior."""

import importlib
import logging
import logging.handlers
import subprocess
import sys

import pytest

import url2md as url2md_module
from url2md import ExtractionError, crawl


# ---------- Step 1: url2md.py import safety ----------


def test_crawl_raises_on_no_pages():
    """crawl() should raise ExtractionError, not sys.exit(), when no pages are fetched."""
    from scrapling import Fetcher

    fetcher = Fetcher()
    with pytest.raises(ExtractionError, match="no pages fetched"):
        crawl(fetcher, "https://nonexistent.invalid", 1, 5, 5, None, False)


def test_import_does_not_disable_logging():
    """Importing url2md as a module must not suppress logging globally."""
    logging.disable(logging.NOTSET)  # reset
    importlib.reload(url2md_module)
    logger = logging.getLogger("test_import")
    logger.setLevel(logging.DEBUG)
    handler = logging.handlers.MemoryHandler(capacity=10)
    logger.addHandler(handler)
    logger.warning("test message")
    assert len(handler.buffer) > 0


# ---------- Step 2: MCP server ----------


def test_mcp_tool_returns_markdown():
    """The url2md MCP tool should return markdown with a title and source."""
    from mcp_server import url2md as mcp_url2md

    result = mcp_url2md("https://example.com")
    assert "# " in result
    assert "> Source:" in result


def test_mcp_tool_returns_error_for_bad_url():
    """The url2md MCP tool should return an error string, not raise."""
    from mcp_server import url2md as mcp_url2md

    result = mcp_url2md("https://nonexistent.invalid", timeout=5)
    assert result.startswith("Error:")


def test_cli_still_works():
    """url2md CLI should still produce markdown output."""
    result = subprocess.run(
        ["python3", "url2md.py", "https://example.com"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "Example Domain" in result.stdout

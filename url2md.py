#!/usr/bin/env python3
"""url2md — Fetch a URL and convert its content to clean Markdown."""

import argparse
import copy
import logging
import re
import sys
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse

logging.disable(logging.CRITICAL)

from lxml import etree
from scrapling import Fetcher
from markdownify import markdownify


# Tags to strip from the content tree
STRIP_TAGS = {
    "script", "style", "noscript", "svg", "nav", "footer",
    "header", "aside", "iframe", "form",
}

# Regex for class/id attributes that indicate noise
NOISE_PATTERN = re.compile(
    r"cookie|banner|sidebar|widget|social|share|comment|newsletter|ad-|promo|popup|modal",
    re.IGNORECASE,
)

# Pre-compiled regexes for slugify
_SLUG_STRIP = re.compile(r"[^\w\s-]")
_SLUG_HYPHENS = re.compile(r"[\s]+")

# CSS selectors to try for main content, in priority order
CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".entry-content",
    ".markdown-body",
    ".prose",
    ".content",
    ".post-body",
    ".article-body",
    ".page-content",
]


class FetchError(Exception):
    pass


class ExtractionError(Exception):
    pass


def css_first(resp, selector: str):
    """Return the first match for a CSS selector, or None."""
    results = resp.css(selector)
    return results[0] if results else None


def fetch_page(fetcher: Fetcher, url: str, timeout: int = 30):
    """Fetch a URL and return the Scrapling response, or raise FetchError."""
    try:
        resp = fetcher.get(url, timeout=timeout, verify=False)
    except Exception as e:
        raise FetchError(f"failed to fetch {url}: {e}") from e
    if resp.status != 200:
        raise FetchError(f"HTTP {resp.status} for {url}")
    return resp


def extract_title(resp) -> str:
    """Extract page title from response."""
    title_el = css_first(resp, "title")
    if title_el:
        return title_el.text.strip()
    h1 = css_first(resp, "h1")
    if h1:
        return h1.text.strip()
    return ""


def find_content_element(resp, selector: str | None = None):
    """Find the main content element using CSS selectors."""
    if selector:
        el = css_first(resp, selector)
        if el:
            return el
        print(f"Warning: selector '{selector}' not found, falling back", file=sys.stderr)

    for sel in CONTENT_SELECTORS:
        el = css_first(resp, sel)
        if el:
            return el

    return css_first(resp, "body")


def strip_noise(tree):
    """Remove noisy elements from an lxml tree (in place)."""
    etree.strip_elements(tree, *STRIP_TAGS)

    # Snapshot into list to avoid mutating during iteration
    to_remove = []
    for el in tree.iter():
        for attr in ("class", "id"):
            val = el.get(attr, "")
            if val and NOISE_PATTERN.search(val):
                to_remove.append(el)
                break
    for el in to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)


def to_markdown(html_content: str) -> str:
    """Convert HTML string to clean markdown."""
    md = markdownify(
        html_content,
        heading_style="ATX",
        bullets="-",
        strip=["img"],
    )
    return post_process(md)


def post_process(md: str) -> str:
    """Clean up generated markdown."""
    md = re.sub(r"[^\S\n]+$", "", md, flags=re.MULTILINE)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def extract_page(resp, selector: str | None = None, raw: bool = False) -> str:
    """Extract and convert a single page to markdown. Raises ExtractionError."""
    if raw:
        content_el = css_first(resp, "body")
        if not content_el:
            raise ExtractionError("no <body> found")
    else:
        content_el = find_content_element(resp, selector)
        if not content_el:
            raise ExtractionError("no content element found")

    # Get the lxml element and work on a deep copy
    tree = copy.deepcopy(content_el._root)
    strip_noise(tree)

    html_str = etree.tostring(tree, encoding="unicode", method="html")
    return to_markdown(html_str)


def collect_internal_links(resp, seed_url: str, parsed_seed, seed_path: str) -> list[str]:
    """Collect internal links that share domain and path prefix with seed URL."""
    links = []
    seen = set()

    for a in resp.css("a[href]"):
        href = a.attrib.get("href", "")
        if not href or href.startswith(("#", "javascript:")):
            continue
        full_url = urldefrag(urljoin(seed_url, href))[0]
        parsed = urlparse(full_url)
        if parsed.netloc != parsed_seed.netloc:
            continue
        if not parsed.path.startswith(seed_path):
            continue
        if full_url not in seen:
            seen.add(full_url)
            links.append(full_url)

    return links


def slugify(text: str) -> str:
    """Create a markdown-compatible anchor slug from text."""
    slug = text.lower()
    slug = _SLUG_STRIP.sub("", slug)
    slug = _SLUG_HYPHENS.sub("-", slug)
    return slug.strip("-")


def crawl(fetcher: Fetcher, seed_url: str, depth: int, max_pages: int,
          timeout: int, selector: str | None, raw: bool) -> str:
    """BFS crawl from seed URL and return combined markdown."""
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()
    queue.append((seed_url, 0))
    visited.add(seed_url)

    parsed_seed = urlparse(seed_url)
    seed_path = parsed_seed.path.rsplit("/", 1)[0] + "/"

    pages: list[tuple[str, str, str]] = []  # (url, title, markdown)

    while queue and len(pages) < max_pages:
        url, current_depth = queue.popleft()
        try:
            resp = fetch_page(fetcher, url, timeout)
        except (FetchError, Exception) as e:
            print(f"Warning: {e}", file=sys.stderr)
            continue

        try:
            title = extract_title(resp) or url
            md = extract_page(resp, selector, raw)
        except ExtractionError as e:
            print(f"Warning: {e} on {url}", file=sys.stderr)
            continue

        pages.append((url, title, md))

        if current_depth < depth:
            for link in collect_internal_links(resp, seed_url, parsed_seed, seed_path):
                if link not in visited:
                    visited.add(link)
                    queue.append((link, current_depth + 1))

    if not pages:
        sys.exit("Error: no pages fetched")

    # Build combined document
    seed_title = pages[0][1]
    parts = [f"# {seed_title}\n"]
    parts.append(f"> Crawled {len(pages)} pages from {parsed_seed.netloc}\n")

    # Table of contents
    parts.append("## Table of Contents")
    for url, title, _ in pages:
        slug = slugify(title)
        parts.append(f"- [{title}](#{slug})")
    parts.append("")

    # Page sections
    for url, title, md in pages:
        parts.append("---\n")
        parts.append(f"## {title}")
        parts.append(f"> Source: {url}\n")
        parts.append(md)
        parts.append("")

    return post_process("\n".join(parts))


def normalize_url(url: str) -> str:
    """Add https:// if no scheme present."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def main():
    parser = argparse.ArgumentParser(
        description="Fetch a URL and convert its content to clean Markdown."
    )
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("-o", "--output", help="Write to file instead of stdout")
    parser.add_argument("--raw", action="store_true",
                        help="Skip content extraction, convert full <body>")
    parser.add_argument("--selector", help="CSS selector for content container")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Request timeout in seconds (default: 30)")
    parser.add_argument("--depth", type=int, default=0,
                        help="Follow internal links N levels deep (default: 0)")
    parser.add_argument("--max-pages", type=int, default=20,
                        help="Max pages to fetch during crawl (default: 20)")

    args = parser.parse_args()
    url = normalize_url(args.url)
    fetcher = Fetcher()

    if args.depth > 0:
        md = crawl(fetcher, url, args.depth, args.max_pages, args.timeout,
                   args.selector, args.raw)
    else:
        try:
            resp = fetch_page(fetcher, url, args.timeout)
        except FetchError as e:
            sys.exit(f"Error: {e}")

        title = extract_title(resp)
        try:
            page_md = extract_page(resp, args.selector, args.raw)
        except ExtractionError as e:
            sys.exit(f"Error: {e}")

        final_url = resp.url if hasattr(resp, "url") else url
        parts = []
        if title:
            parts.append(f"# {title}\n")
        parts.append(f"> Source: {final_url}\n")
        parts.append(page_md)
        md = "\n".join(parts)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()

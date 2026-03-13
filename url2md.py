#!/usr/bin/env python3
"""url2md — Fetch a URL and convert its content to clean Markdown."""

import argparse
import copy
import logging
import re
import sys
from collections import deque
from urllib.parse import urljoin, urlparse

logging.disable(logging.WARNING)

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


def css_first(resp, selector: str):
    """Return the first match for a CSS selector, or None."""
    results = resp.css(selector)
    return results[0] if results else None


def fetch_page(url: str, timeout: int = 30):
    """Fetch a URL and return the Scrapling response."""
    fetcher = Fetcher()
    resp = fetcher.get(url, timeout=timeout, verify=False)
    if resp.status != 200:
        print(f"Error: HTTP {resp.status} for {url}", file=sys.stderr)
        sys.exit(1)
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
    # Remove unwanted tags
    for tag in STRIP_TAGS:
        for el in tree.iter(tag):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    # Remove elements with noisy class/id attributes
    for el in tree.iter():
        for attr in ("class", "id"):
            val = el.get(attr, "")
            if val and NOISE_PATTERN.search(val):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
                break


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
    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in md.splitlines()]
    # Collapse 3+ blank lines into 2
    result = []
    blank_count = 0
    for line in lines:
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)
    return "\n".join(result).strip() + "\n"


def extract_page(resp, selector: str | None = None, raw: bool = False) -> str:
    """Extract and convert a single page to markdown."""
    if raw:
        body = css_first(resp, "body")
        if not body:
            print("Error: no <body> found", file=sys.stderr)
            sys.exit(1)
        content_el = body
    else:
        content_el = find_content_element(resp, selector)
        if not content_el:
            print("Error: no content element found", file=sys.stderr)
            sys.exit(1)

    # Get the lxml element and work on a deep copy
    lxml_el = content_el._root
    tree = copy.deepcopy(lxml_el)
    strip_noise(tree)

    html_str = etree.tostring(tree, encoding="unicode", method="html")
    return to_markdown(html_str)


def collect_internal_links(resp, seed_url: str) -> list[str]:
    """Collect internal links that share domain and path prefix with seed URL."""
    parsed_seed = urlparse(seed_url)
    seed_path = parsed_seed.path.rsplit("/", 1)[0] + "/"
    links = []
    seen = set()

    for a in resp.css("a[href]"):
        href = a.attrib.get("href", "")
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full_url = urljoin(seed_url, href)
        # Strip fragment
        full_url = full_url.split("#")[0]
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
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug.strip("-")


def crawl(seed_url: str, depth: int, max_pages: int, timeout: int,
          selector: str | None, raw: bool) -> str:
    """BFS crawl from seed URL and return combined markdown."""
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()
    queue.append((seed_url, 0))
    visited.add(seed_url)

    pages: list[tuple[str, str, str]] = []  # (url, title, markdown)

    while queue and len(pages) < max_pages:
        url, current_depth = queue.popleft()
        try:
            resp = fetch_page(url, timeout)
        except SystemExit:
            continue
        except Exception as e:
            print(f"Warning: failed to fetch {url}: {e}", file=sys.stderr)
            continue

        title = extract_title(resp) or url
        md = extract_page(resp, selector, raw)
        pages.append((url, title, md))

        if current_depth < depth:
            for link in collect_internal_links(resp, seed_url):
                if link not in visited:
                    visited.add(link)
                    queue.append((link, current_depth + 1))

    if not pages:
        print("Error: no pages fetched", file=sys.stderr)
        sys.exit(1)

    # Build combined document
    seed_title = pages[0][1]
    parsed = urlparse(seed_url)
    parts = [f"# {seed_title}\n"]
    parts.append(f"> Crawled {len(pages)} pages from {parsed.netloc}\n")

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

    if args.depth > 0:
        md = crawl(url, args.depth, args.max_pages, args.timeout,
                   args.selector, args.raw)
    else:
        resp = fetch_page(url, args.timeout)
        title = extract_title(resp)
        page_md = extract_page(resp, args.selector, args.raw)

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

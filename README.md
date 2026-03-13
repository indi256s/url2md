# url2md

Fetch any URL. Get clean markdown. No noise.

Web pages are drowning in navbars, cookie banners, and ad wrappers. You want the content. `url2md` strips everything else and hands you readable markdown — ready for LLMs, note-taking, or offline reading.

## How it works

Point it at a URL. It fetches the page, finds the main content (`<article>`, `<main>`, or the best container it can find), strips the noise, and converts the rest to markdown.

```bash
url2md https://en.wikipedia.org/wiki/Web_scraping
```

Output goes to stdout. Pipe it, redirect it, or save it with `-o`:

```bash
url2md https://example.com/blog/post -o post.md
```

## Install

Python 3.10+ required.

```bash
pip install "scrapling[shell]"
```

Then either alias it or run directly:

```bash
alias url2md='python3 /path/to/url2md.py'
```

## Usage

```
url2md URL [-o FILE] [--raw] [--selector CSS] [--timeout SECS] [--depth N] [--max-pages N]
```

| Flag | What it does |
|---|---|
| `-o FILE` | Write to file instead of stdout |
| `--raw` | Skip smart extraction, convert the full `<body>` |
| `--selector CSS` | Target a specific container (e.g. `"article.post-content"`) |
| `--timeout SECS` | Request timeout, default 30 |
| `--depth N` | Follow internal links N levels deep (default: 0, single page) |
| `--max-pages N` | Cap total pages during crawl (default: 20) |

No scheme in the URL? It adds `https://` automatically.

## Multi-page crawl

Need more than one page? `--depth` follows internal links from the seed URL.

```bash
url2md https://docs.python.org/3/library/asyncio.html --depth 1 -o asyncio-docs.md
```

This fetches the seed page, finds all same-domain links sharing the URL path prefix, and crawls one level deep. The output is a single document with a table of contents and section dividers between pages.

Pages are capped at 20 by default. Override with `--max-pages`.

## What gets stripped

**Tags removed:** `script`, `style`, `noscript`, `svg`, `nav`, `footer`, `header`, `aside`, `iframe`, `form`

**Elements matching these patterns in class/id:** `cookie`, `banner`, `sidebar`, `widget`, `social`, `share`, `comment`, `newsletter`, `ad-`, `promo`, `popup`, `modal`

## Content detection

The tool tries these selectors in order and picks the first match:

`article` > `main` > `[role="main"]` > `.post-content` > `.entry-content` > `.markdown-body` > `.prose` > `.content` > `.post-body` > `.article-body` > `.page-content` > `body`

Override with `--selector` when you know exactly where the content lives.

## Claude Code skill

Works as a `/url2md` slash command in Claude Code and Cowork. The page content gets injected directly into conversation context — no copy-paste needed.

## Dependencies

Built on [Scrapling](https://github.com/D4Vinci/Scrapling) for fetching/parsing, with `markdownify` for HTML-to-markdown conversion and `lxml` for tree manipulation.

# url2md

Fetch any URL. Get clean markdown. No noise.

`url2md` fetches a web page, extracts the main content, strips navigation/ads/noise, and outputs clean markdown.

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
git clone https://github.com/indi256s/url2md.git
cd url2md
pip install -r requirements.txt
```

Optionally add an alias to your shell config (`.zshrc` / `.bashrc`):

```bash
alias url2md='python3 /absolute/path/to/url2md.py'
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

## Integration with Claude

### Claude Code & Cowork

Two ways to use url2md with Claude Code:

**Option A — MCP server (recommended)**

Register the tool so Claude can use it automatically:

```bash
claude mcp add url2md -- python3 /absolute/path/to/mcp_server.py
```

This registers the tool for the current project. To make it available across all projects, add `--scope user`.

**Option B — Custom slash command**

Create `.claude/commands/url2md.md` in your project:

```markdown
Use the Bash tool to run: python3 /absolute/path/to/url2md.py $ARGUMENTS

Return the stdout output as markdown.
```

Then use it with `/url2md https://example.com`.

For team use with Claude Cowork, commit `.claude/commands/url2md.md` to your shared repository — all team members get the `/url2md` command automatically.

### Claude Desktop

1. Install dependencies:
   ```bash
   pip install "scrapling[shell]" mcp
   ```
2. Find your Python path:
   ```bash
   which python3
   ```
3. Add to `claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "url2md": {
         "command": "/absolute/path/to/python3",
         "args": ["/absolute/path/to/mcp_server.py"]
       }
     }
   }
   ```
4. Config file locations:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`
5. Restart Claude Desktop.

**Important:** Use absolute paths for both the Python interpreter and `mcp_server.py`. Claude Desktop does not inherit your shell PATH.

## Dependencies

Built on [Scrapling](https://github.com/D4Vinci/Scrapling) for fetching/parsing, with `markdownify` for HTML-to-markdown conversion and `lxml` for tree manipulation.

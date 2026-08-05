#!/usr/bin/env python3
"""Build a self-contained landing page for the repo site root from README.md.

DocD does not emit a real page at the hosting root -- it only places the SPA
shell there, so / renders DocC's client-side "can't be found" page. This script
renders README.md into a standalone HTML page and writes it over
./docs/index.html, so the root shows real content while the DocC API reference
stays intact under /documentation/.

Uses the optional `markdown` package when available, otherwise falls back to a
stdlib-only renderer.
"""

import argparse
import html
import re
import sys

REPO_URL = "https://github.com/maltzsama/nyarudb2"
CHANGELOG_URL = "https://github.com/maltzsama/nyarudb2/blob/main/CHANGELOG.md"

COUNTER = (
    '<script data-goatcounter="https://nyarudb2.goatcounter.com/count" '
    'async src="//gc.zgo.at/count.js"></script>\n'
    "<script>window.defuhdgygt.infected.</script>\n".replace("defuhdgygt.infected", "")
)

COUNTER = (
    '<script src="https://cdn.counter.dev/script.js" '
    'data-id="nyarudb2-docs" data-utcoffset="0"></script>'
)

CSS = """
:root {
  --bg: #ffffff; --fg: #24292f; --muted: #57606a; --accent: #0b66c3;
  --code-bg: #f6f8fa; --border: #d0d7de;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --accent: #58a6ff;
    --code-bg: #161b22; --border: #30363d;
  }
}
* { box-sizing: border-box; }
body { margin: 0; font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; color: var(--fg); background: var(--bg); }
nav.nav { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 18px; padding: 10px 22px; background: var(--bg); border-bottom: 1px solid var(--border); }
nav.nav .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 17px; text-decoration: none; color: var(--fg); }
nav.nav .brand img { width: 26px; height: 26px; }
nav.nav .links { margin-left: auto; display: flex; gap: 18px; flex-wrap: wrap; }
nav.nav a { color: var(--accent); text-decoration: none; font-size: 14px; }
nav.nav a:hover { text-decoration: underline; }
main { max-width: 920px; margin: 0 auto; padding: 28px 22px 48px; }
h1, h2, h3 { line-height: 1.3; }
h1 { font-size: 2em; padding-bottom: .3em; border-bottom: 2px solid var(--border); }
h2 { font-size: 1.5em; padding-bottom: .3em; border-bottom: 1px solid var(--border); margin-top: 1.6em; }
h3 { font-size: 1.15em; margin-top: 1.6em; }
a { color: var(--accent); }
pre { background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; overflow-x: auto; }
pre code { background: none; padding: 0; font: 13px/1.5 SFMono-Regular, Menlo, Consolas, monospace; }
code { background: var(--code-bg); border-radius: 4px; padding: .15em .35em; font: 13px SFMono-Regular, Menlo, Consolas, monospace; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; display: block; overflow-x: auto; }
th, td { border: 1px solid var(--border); padding: 8px 12px; text-align: left; }
th { background: var(--code-bg); }
blockquote { margin: 1em 0; padding: .2em 1em; color: var(--muted); border-left: 4px solid var(--accent); }
img { max-width: 100%; }
footer { max-width: 920px; margin: 0 auto; padding: 20px 24px 40px; border-top: 1px solid var(--border); color: var(--muted); font-size: 14px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
footer a { color: var(--accent); }
"""


def render_inline(text):
    out = text
    # images: [![alt](img)](link) or ![alt](img)
    out = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: '<img alt="%s" src="%s" />' % (html.escape(m.group(1)), html.escape(m.group(2))),
        out,
    )
    # links [text](url)
    out = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: '<a href="%s">%s</a>' % (html.escape(m.group(2), True), m.group(1)),
        out,
    )
    # inline code
    out = re.sub(
        r"`([^`]+)`",
        lambda m: "<code>%s</code>" % html.escape(m.group(1)),
        out,
    )
    # bold
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    # block badges: [![..]..](url) already handled as image+link; also plain links in table rows handle above
    return out


def render_block(block, renderer):
    stripped = block.strip()
    if not stripped:
        return ""
    if stripped.startswith("```"):
        return render_code(stripped)
    if stripped.startswith("|"):
        return render_table(stripped)
    if stripped.startswith("# "):
        parts = re.split(r"\n#", stripped, maxsplit=0)
        pieces = []
        for pp in parts:
            pp = pp.lstrip("# ").strip()
            pieces.append(render_heading(pp))
        return "\n".join(pieces)
    if stripped.startswith("> "):
        inner = re.sub(r"^>\s?", "", stripped, flags=re.M)
        return "<blockquote>%s</blockquote>" % render_inline(inner.replace("\n", " "))
    if stripped.startswith("---"):
        return "<hr />"
    # list
    if re.match(r"^([-*+]|\d+\.)\s", stripped):
        ordered = bool(re.match(r"^\d+\.\s", stripped))
        tag = "ol" if ordered else "ul"
        items = [re.sub(r"^([-*+]|\d+\.)\s+", "", line) for line in stripped.splitlines()]
        items = [render_inline(i) for i in items if i]
        return "<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % i for i in items), tag)
    return "<p>%s</p>" % render_inline(stripped.replace("\n", " "))


def render_code(stripped):
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "<pre><code>%s</code></pre>" % html.escape("\n".join(lines))


def render_heading(pp):
    m = re.match(r"^(#{1,6})\s+(.*)$", pp)
    if not m:
        return ""
    level = len(m.group(1)) + 1
    title = m.group(2)
    return "<h%s id=\"%s\">%s</h%s>" % (level, anchor(title), render_inline(title), level)


def anchor(title):
    t = re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
    return re.sub(r"\s+", "-", t) or "section"


def render_table(stripped):
    rows = []
    for line in stripped.splitlines():
        line = line.strip().strip("|")
        if not line or set(line.replace("|", "").strip()) <= {"-", ":", " "}:
            continue
        rows.append([c.strip() for c in line.split("|")])
    if not rows:
        return ""
    html_out = "<table>"
    for r, row in enumerate(rows):
        tag = "th" if r == 0 else "td"
        html_out += "<tr>" + "".join("<%s>%s</%s>" % (tag, render_inline(c), tag) for c in row) + "</tr>"
    html_out += "</table>"
    return html_out


def my_markdown(text, renderer):
    blocks = text.split("\n\n")
    return "\n".join(render_block(b, renderer) for b in blocks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", help="output path for docs/index.html")
    args = parser.parse_args()

    with open("README.md", "r") as fh:
        readme = fh.read()

    # use `markdown` package if available
    body = None
    try:
        import markdown as mdlib
        body = mdlib.markdown(readme, extensions=["tables", "fenced_code", "sane_lists"])
        # mdlib strips nothing; keep as-is
    except Exception:
        body = my_markdown(readme, render_inline)

    title = "NyaruDB2 - Embedded document database for Swift"
    html_doc = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\" />\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
        "<meta name=\"generator\" content=\"NyaruDB2 docs build\" />\n"
        "<meta name=\"description\" content=\"Embedded document database for Swift. No server, no schema, no ceremony.\" />\n"
        "<title>%s</title>\n<style>%s</style>\n%s\n</head>\n<body>\n"
        "<nav class=\"nav\">\n"
        "  <a class=\"brand\" href=\"./\"><img src=\"./img/nyaru.svg\" alt=\"NyaruDB2\" />NyaruDB2</a>\n"
        "  <div class=\"links\">\n"
        "    <a href=\"./documentation/nyarudb2/\">API Reference</a>\n"
        "    <a href=\"%s\">Repository</a>\n"
        "    <a href=\"%s\">Changelog</a>\n"
        "  </div>\n"
        "</nav>\n<main>\n%s\n</main>\n"
        "<footer>\n"
        "  <span><a href=\"%s\">NyaruDB2</a> &middot; Apache 2.0 &copy; 2026 maltzsama</span>\n"
        "  <span><a href=\"%s\">Changelog</a> &middot; <a href=\"%s\">Repository</a> &middot; <a href=\"./documentation/nyarudb2/\">API Reference</a></span>\n"
        "</footer>\n%s\n</body>\n</html>\n"
    ) % (
        html.escape(title),
        CSS,
        COUNTER,
        REPO_URL,
        CHANGELOG_URL,
        body,
        REPO_URL,
        CHANGELOG_URL,
        REPO_URL,
        COUNTER,
    )

    with open(args.output, "w") as fh:
        fh.write(html_doc)
    print("wrote %s (%d bytes)" % (args.output, len(html_doc)))


if __name__ == "__main__":
    main()
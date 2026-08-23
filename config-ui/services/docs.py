"""Renders the project's Markdown documentation (README.md + docs/*.md) for
display inside the admin UI. The same files are also meant to be read
directly on GitHub or any git viewer; this just re-renders them in place."""

import re
from pathlib import Path

import markdown

PROJECT_ROOT = Path("/workspace")
DOCS_DIR = PROJECT_ROOT / "docs"

# (slug, nav title, file path); order here is the sidebar order.
PAGES = [
    ("overview", "Overview", PROJECT_ROOT / "README.md"),
    ("architecture", "Architecture", DOCS_DIR / "architecture.md"),
    ("configuration", "Configuration Reference", DOCS_DIR / "configuration.md"),
    ("admin-ui", "Admin UI Guide", DOCS_DIR / "admin-ui-guide.md"),
    ("cloudflare-tunnel-setup", "Cloudflare Tunnel Setup", DOCS_DIR / "cloudflare-tunnel-setup.md"),
    ("troubleshooting", "Troubleshooting", DOCS_DIR / "troubleshooting.md"),
]

_BY_SLUG = {slug: (title, path) for slug, title, path in PAGES}
# The docs cross-reference each other with plain relative filenames (e.g.
# "configuration.md#foundry-vtt") so that they still work as normal links on
# GitHub/any git viewer. Rewrite those to /docs/<slug> so they also work when
# rendered inside this app, which routes by slug rather than by filename.
_FILENAME_TO_SLUG = {path.name: slug for slug, _title, path in PAGES}
_MD_LINK_RE = re.compile(r'href="(?:[^"#]*/)?([^"#/]+\.md)(#[^"]*)?"')

_MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br", "toc"]


def _rewrite_doc_links(html: str) -> str:
    def repl(match: "re.Match[str]") -> str:
        filename, fragment = match.groups()
        slug = _FILENAME_TO_SLUG.get(filename)
        if slug is None:
            return match.group(0)
        return f'href="/docs/{slug}{fragment or ""}"'

    html = _MD_LINK_RE.sub(repl, html)
    return html.replace('href="docs/"', 'href="/docs"').replace('href="docs"', 'href="/docs"')


def render_page(slug: str):
    """Returns (title, html) for a doc slug, or None if the slug is unknown."""
    entry = _BY_SLUG.get(slug)
    if entry is None:
        return None
    title, path = entry
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return title, f"<p><em>Could not load this page ({path.name}): {exc}</em></p>"
    html = _rewrite_doc_links(markdown.markdown(text, extensions=_MD_EXTENSIONS))
    return title, html

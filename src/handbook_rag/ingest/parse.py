"""Find handbook markdown files, clean them and map them to public URLs."""

import logging
import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import yaml

logger = logging.getLogger(__name__)

CONTENT_ROOT = PurePosixPath("content/handbook")
BASE_URL = "https://handbook.gitlab.com/"
# Sections where only `.md` files directly in the section dir are used (no subdirs).
TOP_LEVEL_ONLY_SECTIONS = frozenset({"engineering"})

_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
# Shortcode tags only; the content between paired tags ({{% a %}}...{{% /a %}}) is kept.
_SHORTCODE_RE = re.compile(r"\{\{<.*?>\}\}|\{\{%.*?%\}\}", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_FENCED_BLOCK_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.MULTILINE | re.DOTALL)
# Removed with their contents: no prose inside.
_HTML_ELEMENT_RE = re.compile(r"<(svg|style|script)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE)
# Tags removed, inner text kept. <br> becomes a space so table rows stay on one line.
_HTML_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
# Known tags only, so placeholders like <your-name> survive. The lookahead (not \b) stops
# `a` from matching `<a-custom>` or `<abbr>`.
_HTML_TAG_RE = re.compile(
    r"</?(?:div|details|summary|span|a|p|i|b|em|strong|table|tr|td|th|ul|ol|li"
    r"|option|select|img|iframe)(?=[\s/>])[^>]*>",
    re.IGNORECASE,
)
_WHITESPACE_LINE_RE = re.compile(r"^[ \t]+$", re.MULTILINE)
_CUSTOM_ID_RE = re.compile(r"\s*\{#([\w-]+)\}\s*$")


def iter_source_files(handbook_root: Path, sections: Iterable[str]) -> list[Path]:
    """Markdown files for the given sections, sorted. A missing section dir is an error."""
    files: list[Path] = []
    for section in sorted(sections):
        section_dir = handbook_root / CONTENT_ROOT / section
        if not section_dir.is_dir():
            raise FileNotFoundError(f"Section dir not found (run `make data`?): {section_dir}")
        pattern = section_dir.glob if section in TOP_LEVEL_ONLY_SECTIONS else section_dir.rglob
        files.extend(sorted(pattern("*.md")))
    return files


def section_of(source_path: PurePosixPath) -> str:
    """`content/handbook/<section>/...` -> `<section>`."""
    return source_path.relative_to(CONTENT_ROOT).parts[0]


def split_front_matter(text: str) -> tuple[str | None, str]:
    """Return (title from YAML front matter, body without front matter)."""
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return None, text
    body = text[match.end() :]
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        logger.warning("front_matter.parse_failed", extra={"error_type": type(exc).__name__})
        return None, body
    title = meta.get("title") if isinstance(meta, dict) else None
    return (str(title).strip() or None) if title else None, body


def _strip_html(text: str) -> str:
    text = _HTML_ELEMENT_RE.sub("", text)
    text = _HTML_BR_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub("", text)
    return _WHITESPACE_LINE_RE.sub("", text)


def strip_html_outside_code(text: str) -> str:
    """Apply `_strip_html` to everything except fenced code blocks, which stay verbatim."""
    parts: list[str] = []
    pos = 0
    for block in _FENCED_BLOCK_RE.finditer(text):
        parts += [_strip_html(text[pos : block.start()]), block.group()]
        pos = block.end()
    parts.append(_strip_html(text[pos:]))
    return "".join(parts)


def clean_markdown(body: str) -> str:
    """Drop Hugo shortcodes, HTML comments and HTML markup; collapse leftover blank lines."""
    body = _HTML_COMMENT_RE.sub("", body)
    body = _SHORTCODE_RE.sub("", body)
    body = strip_html_outside_code(body)
    return _BLANK_LINES_RE.sub("\n\n", body).strip()


def source_url(source_path: PurePosixPath) -> str:
    """`content/handbook/a/b/_index.md` -> `.../handbook/a/b/`; `.../a/b/c.md` -> `.../a/b/c/`.

    Hugo leaf bundles (`a/b/index.md`) map to the directory URL like `_index.md`.
    """
    parts = source_path.relative_to("content").with_suffix("").parts
    if parts[-1] in ("_index", "index"):
        parts = parts[:-1]
    return BASE_URL + "/".join(parts) + "/"


def heading_anchor(heading: str) -> tuple[str, str]:
    """Return (heading text, anchor id). Honours Hugo `{#custom-id}`, else Hugo's auto id."""
    match = _CUSTOM_ID_RE.search(heading)
    if match:
        return heading[: match.start()].strip(), match.group(1)
    slug = re.sub(r"[^\w\- ]", "", heading.lower()).strip().replace(" ", "-")
    return heading.strip(), slug

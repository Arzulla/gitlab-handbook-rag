"""Split cleaned handbook markdown into heading-based chunks with access metadata."""

import hashlib
import itertools
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from handbook_rag.access import AccessConfig, access_group_for_section
from handbook_rag.ingest.parse import (
    clean_markdown,
    heading_anchor,
    iter_source_files,
    section_of,
    source_url,
    split_front_matter,
)

MAX_CHARS = 1500  # longer sections are split on paragraph boundaries
MIN_CHARS = 100  # shorter pieces (heading prefix excluded) are dropped as noise

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_PARAGRAPH_SEP_RE = re.compile(r"\n\s*\n")
_ANY_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+\S")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str  # heading path + "\n\n" + content
    title: str
    heading_path: str  # "Title > H2 > H3"
    section: str
    access_group: str
    url: str
    source_path: str
    commit_sha: str


class Section(NamedTuple):
    headings: tuple[str, ...]  # (), (h2,) or (h2, h3)
    anchor: str | None
    body: str


def split_by_headings(markdown: str) -> list[Section]:
    """Split on H2/H3 lines (ignoring code fences). Text before the first H2 has no heading."""
    sections: list[Section] = []
    headings: tuple[str, ...] = ()
    anchor: str | None = None
    lines: list[str] = []
    in_fence = False

    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING_RE.match(line)
        if not match:
            lines.append(line)
            continue
        sections.append(Section(headings, anchor, "\n".join(lines).strip()))
        text, anchor = heading_anchor(match.group(2))
        headings = (text,) if len(match.group(1)) == 2 else (*headings[:1], text)
        lines = []

    sections.append(Section(headings, anchor, "\n".join(lines).strip()))
    return [s for s in sections if s.body]


def _ends_with_heading(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    return bool(lines) and bool(_ANY_HEADING_RE.match(lines[-1]))


def _drop_trailing_headings(text: str) -> str:
    """Remove heading lines that have no content after them (end of section)."""
    lines = text.rstrip().splitlines()
    while lines and (not lines[-1].strip() or _ANY_HEADING_RE.match(lines[-1])):
        lines.pop()
    return "\n".join(lines)


def _pack(parts: list[str], sep: str, max_chars: int) -> list[str]:
    """Greedily join consecutive parts with `sep` while the result fits in `max_chars`.

    On a cut, trailing heading parts move forward to the next piece, so a heading always
    stays with the content that follows it.
    """
    pieces: list[list[str]] = [[]]
    for part in parts:
        current = pieces[-1]
        if current and len(sep.join([*current, part])) > max_chars:
            carry: list[str] = []
            while current and _ends_with_heading(current[-1]):
                carry.insert(0, current.pop())
            if current:
                pieces.append(carry)
            else:  # nothing but headings so far: keep them together with this part
                current.extend(carry)
        pieces[-1].append(part)
    return [sep.join(piece) for piece in pieces if piece]


def _table_header(lines: list[str]) -> str | None:
    """Header row + separator row of the first markdown table in `lines`, if any."""
    for row, separator in itertools.pairwise(lines):
        if row.lstrip().startswith("|") and _TABLE_SEPARATOR_RE.match(separator):
            return f"{row}\n{separator}"
    return None


def _split_lines(paragraph: str, max_chars: int) -> list[str]:
    """Split one oversized paragraph on lines; table continuations repeat the table header."""
    lines = paragraph.splitlines()
    header = _table_header(lines)
    if header is None:
        return _pack(lines, "\n", max_chars)
    pieces = _pack(lines, "\n", max_chars - len(header) - 1)
    return pieces[:1] + [
        f"{header}\n{piece}" if piece.lstrip().startswith("|") else piece for piece in pieces[1:]
    ]


def split_long(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split on paragraph boundaries; a paragraph that alone is too long is split on lines."""
    text = _drop_trailing_headings(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    paragraphs: list[str] = []
    for paragraph in _PARAGRAPH_SEP_RE.split(text):
        if len(paragraph) > max_chars:
            paragraphs.extend(_split_lines(paragraph, max_chars))
        elif paragraph.strip():
            paragraphs.append(paragraph)
    return _pack(paragraphs, "\n\n", max_chars)


def chunk_id(source_path: str, heading_path: str, index: int) -> str:
    return hashlib.sha256(f"{source_path}|{heading_path}|{index}".encode()).hexdigest()[:16]


def chunk_document(
    source_path: PurePosixPath, raw_text: str, access: AccessConfig, commit_sha: str
) -> list[Chunk]:
    """Turn one markdown file into chunks. Raises if its section is not in the access config."""
    section = section_of(source_path)
    access_group = access_group_for_section(section, access)  # fail closed, before any work
    url = source_url(source_path)
    front_title, body = split_front_matter(raw_text)
    is_dir_page = source_path.stem in ("_index", "index")
    fallback = source_path.parent.name if is_dir_page else source_path.stem
    title = front_title or fallback

    chunks: list[Chunk] = []
    seen: Counter[str] = Counter()  # index per heading path keeps ids unique and stable
    for headings, anchor, section_body in split_by_headings(clean_markdown(body)):
        heading_path = " > ".join((title, *headings))
        for piece in split_long(section_body):
            if len(piece) < MIN_CHARS:
                continue
            index = seen[heading_path]
            seen[heading_path] += 1
            chunks.append(
                Chunk(
                    id=chunk_id(str(source_path), heading_path, index),
                    text=f"{heading_path}\n\n{piece}",
                    title=title,
                    heading_path=heading_path,
                    section=section,
                    access_group=access_group,
                    url=f"{url}#{anchor}" if anchor else url,
                    source_path=str(source_path),
                    commit_sha=commit_sha,
                )
            )
    return chunks


def build_chunks(handbook_root: Path, access: AccessConfig, commit_sha: str) -> list[Chunk]:
    """Chunk every source file of every section in the access config."""
    chunks: list[Chunk] = []
    for path in iter_source_files(handbook_root, access.sections):
        source_path = PurePosixPath(path.relative_to(handbook_root).as_posix())
        chunks.extend(
            chunk_document(source_path, path.read_text(encoding="utf-8"), access, commit_sha)
        )
    return chunks

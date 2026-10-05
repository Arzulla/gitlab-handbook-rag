"""Parse + chunk tests over small fixture markdown files in tests/fixtures/handbook."""

import re
from pathlib import Path, PurePosixPath

import pytest

from handbook_rag.access import AccessConfig
from handbook_rag.ingest.chunk import (
    MAX_CHARS,
    MIN_CHARS,
    Chunk,
    build_chunks,
    chunk_document,
    split_by_headings,
    split_long,
)
from handbook_rag.ingest.parse import (
    clean_markdown,
    iter_source_files,
    source_url,
    split_front_matter,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "handbook"
SHA = "0" * 40


@pytest.fixture
def access() -> AccessConfig:
    return AccessConfig(
        sections={"company": "public", "engineering": "public", "people-group": "people"},
        roles={"employee": ["public"], "people_ops": ["public", "people"]},
    )


@pytest.fixture
def chunks(access: AccessConfig) -> list[Chunk]:
    return build_chunks(FIXTURE_ROOT, access, SHA)


# --- URL mapping -------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "url"),
    [
        ("content/handbook/a/b/_index.md", "https://handbook.gitlab.com/handbook/a/b/"),
        ("content/handbook/a/b/c.md", "https://handbook.gitlab.com/handbook/a/b/c/"),
        ("content/handbook/a/b/index.md", "https://handbook.gitlab.com/handbook/a/b/"),
    ],
)
def test_source_url(path: str, url: str) -> None:
    assert source_url(PurePosixPath(path)) == url


def test_chunk_url_gets_heading_anchor(chunks: list[Chunk]) -> None:
    by_heading = {c.heading_path: c.url for c in chunks}

    assert by_heading["About GitLab"] == "https://handbook.gitlab.com/handbook/company/"
    assert by_heading["About GitLab > Mission"].endswith("/handbook/company/#mission")
    assert by_heading["About GitLab > Mission > Everyone can contribute"].endswith("#contribute")


# --- Cleaning ----------------------------------------------------------------


def test_front_matter_is_stripped_and_title_kept() -> None:
    title, body = split_front_matter('---\ntitle: "Hello"\nweight: 3\n---\n\nBody text\n')

    assert title == "Hello"
    assert body.strip() == "Body text"


def test_missing_front_matter_keeps_body() -> None:
    assert split_front_matter("## Heading\ntext") == (None, "## Heading\ntext")


def test_shortcodes_and_html_comments_are_removed() -> None:
    raw = (
        '{{< label name="x" >}}\nKeep me.\n<!-- hidden\nmultiline -->\n'
        "{{% alert %}}\nInner text stays.\n{{% /alert %}}"
    )

    cleaned = clean_markdown(raw)

    assert "{{" not in cleaned
    assert "<!--" not in cleaned
    assert "hidden" not in cleaned
    assert "Keep me." in cleaned
    assert "Inner text stays." in cleaned


def test_known_html_tags_are_stripped_but_unknown_tags_and_code_are_kept() -> None:
    raw = (
        '<p>See <a href="/x">the <strong>guide</strong></a> and <em>ask</em>.</p>\n'
        '<ul><li><b>One</b></li><li><i>Two</i></li></ul> <img src="a.png" alt="x"/>\n'
        "<table><tr><th>H</th><td>D</td></tr></table>\n"
        '<select><option value="1">Pick</option></select><iframe src="v"></iframe>\n'
        "Email <your-name>@gitlab.com, not <abbr>.\n"
        '```html\n<p><a href="/y">raw</a></p>\n```'
    )

    cleaned = clean_markdown(raw)

    assert "See the guide and ask." in cleaned
    for kept in ("One", "Two", "H", "D", "Pick", "<your-name>@gitlab.com", "<abbr>"):
        assert kept in cleaned
    for gone in ("<p>", "<a ", "<li>", "<img", "<table>", "<td>", "<option", "<iframe"):
        assert gone not in cleaned.split("```")[0]
    assert '```html\n<p><a href="/y">raw</a></p>\n```' in cleaned


def test_fixture_chunks_contain_no_markup(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        assert "{{" not in chunk.text
        assert "<!--" not in chunk.text
        assert "title:" not in chunk.text


# --- Splitting ---------------------------------------------------------------


def test_split_by_h2_and_h3_keeps_heading_path() -> None:
    md = "Intro\n\n## A\ntext a\n### A1\ntext a1\n## B\ntext b\n#### deep\nstill b"

    sections = split_by_headings(md)

    assert [s.headings for s in sections] == [(), ("A",), ("A", "A1"), ("B",)]
    assert sections[3].body == "text b\n#### deep\nstill b"


def test_headings_inside_code_fences_do_not_split() -> None:
    md = "## Real\n```bash\n## not a heading\n```\nafter"

    sections = split_by_headings(md)

    assert len(sections) == 1
    assert "## not a heading" in sections[0].body


def test_long_section_is_split_on_paragraph_boundaries() -> None:
    paragraphs = [f"Paragraph {i} " + "x" * 400 for i in range(6)]

    pieces = split_long("\n\n".join(paragraphs))

    assert len(pieces) > 1
    assert all(len(p) <= MAX_CHARS for p in pieces)
    assert "\n\n".join(pieces) == "\n\n".join(paragraphs)  # nothing lost, no mid-paragraph cut


def test_short_section_stays_whole() -> None:
    assert split_long("short text") == ["short text"]


def test_short_chunks_are_dropped(chunks: list[Chunk]) -> None:
    assert not any("Tiny" in c.heading_path for c in chunks)
    assert all(len(c.text) - len(c.heading_path) - 2 >= MIN_CHARS for c in chunks)


def test_chunk_text_is_prefixed_with_heading_path(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        assert chunk.text.startswith(chunk.heading_path + "\n\n")


# --- Discovery and access ----------------------------------------------------


def test_engineering_subdirectories_are_excluded(access: AccessConfig) -> None:
    files = iter_source_files(FIXTURE_ROOT, access.sections)
    names = [f.relative_to(FIXTURE_ROOT / "content" / "handbook").as_posix() for f in files]

    assert "engineering/workflow.md" in names
    assert "engineering/sub/deep.md" not in names


def test_every_chunk_has_a_configured_access_group(
    chunks: list[Chunk], access: AccessConfig
) -> None:
    assert {c.section for c in chunks} == {"company", "engineering", "people-group"}
    for chunk in chunks:
        assert chunk.access_group
        assert chunk.access_group == access.sections[chunk.section]
        assert chunk.commit_sha == SHA


def test_unknown_section_fails_closed(access: AccessConfig) -> None:
    path = PurePosixPath("content/handbook/marketing/page.md")
    text = "## Heading\n" + "Some marketing content. " * 10

    with pytest.raises(ValueError, match="marketing"):
        chunk_document(path, text, access, SHA)


def test_chunk_ids_are_unique_and_stable(access: AccessConfig) -> None:
    first = build_chunks(FIXTURE_ROOT, access, SHA)
    second = build_chunks(FIXTURE_ROOT, access, SHA)

    assert len({c.id for c in first}) == len(first)
    assert [c.id for c in first] == [c.id for c in second]


# --- Chunking regressions (fixtures in tests/fixtures/chunking) ---------------

CHUNKING_FIXTURES = Path(__file__).parent / "fixtures" / "chunking"


def _chunk_fixture(name: str, access: AccessConfig) -> list[Chunk]:
    path = PurePosixPath(f"content/handbook/company/{name}")
    return chunk_document(path, (CHUNKING_FIXTURES / name).read_text(), access, SHA)


def test_split_table_repeats_header_in_every_chunk(access: AccessConfig) -> None:
    chunks = _chunk_fixture("long_table.md", access)

    assert len(chunks) >= 2
    for chunk in chunks:
        body = chunk.text.removeprefix(chunk.heading_path + "\n\n")
        assert body.startswith("| Benefit | Eligibility | Coverage |\n| ------- |")
    rows = [
        line for c in chunks for line in c.text.splitlines() if re.match(r"\| Benefit \d", line)
    ]
    assert len(rows) == 30  # every data row kept exactly once


def test_no_chunk_ends_with_a_heading(access: AccessConfig) -> None:
    chunks = _chunk_fixture("orphan_heading.md", access)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert not chunk.text.rstrip().splitlines()[-1].lstrip().startswith("#")
    follow_up = next(c for c in chunks if "#### Follow-up steps" in c.text)
    assert follow_up.text.index("#### Follow-up steps") < follow_up.text.index("Team members")
    assert not any("Nothing after this" in c.text for c in chunks)


def test_html_is_stripped_outside_code_blocks(access: AccessConfig) -> None:
    [chunk] = _chunk_fixture("html_noise.md", access)
    text = chunk.text

    for gone in ("<svg", "<path", "display: none", "tracking", '<div class="row', "<details"):
        assert gone not in text
    for gone in ("<summary", "<br", "<span", "</div>\n</div>"):
        assert gone not in text
    for kept in (
        "All-remote since inception, GitLab hires globally.",
        "Eligibility details",
        "first day. No waiting period applies.",
        "Updated quarterly by the Total Rewards team.",
    ):
        assert kept in text
    assert '```html\n<div class="example">Code samples keep their markup.</div>\n```' in text

"""Load the NorthStar policy corpus and split it into retrievable chunks.

Chunking is section-aware (split on markdown '## ' headers) rather than a
fixed character window, because the single most load-bearing chunk in this
corpus -- the Tier Benefits table in loyalty-program-terms.md -- must never
be cut mid-table. A fixed-width splitter would eventually slice through it
and make every tier-benefit claim unretrievable.
"""

import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHUNK_CHARS = 1200

_DOC_ID_RE = re.compile(r"\*\*Document ID:\*\*\s*(\S+)")
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    heading: str
    text: str

    def labeled_text(self) -> str:
        """Self-identifying text for use as a RAGAS context entry -- the
        harness's track-b-examples.md evidence requires reporting retrieved
        chunk IDs, so the chunk's provenance travels with its content."""
        return f"[{self.doc_id} § {self.heading}]\n{self.text}"


def load_raw_documents(corpus_dir: str = "northstar-policy-docs") -> list[dict]:
    """Read every .md file in corpus_dir, extracting its Document ID and title."""
    docs = []
    for path in sorted(Path(corpus_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        doc_id_match = _DOC_ID_RE.search(text)
        if not doc_id_match:
            raise ValueError(f"{path} has no '**Document ID:** ...' line")
        title_match = _TITLE_RE.search(text)
        docs.append({
            "doc_id": doc_id_match.group(1),
            "title": title_match.group(1).strip() if title_match else path.stem,
            "text": text,
            "path": str(path),
        })
    if not docs:
        # A missing or wrong-cwd corpus_dir silently returned [] here, which
        # flowed into build_index([]) as an opaque numpy IndexError/AxisError
        # three calls later -- raise where the actual cause is, not where it
        # happens to blow up.
        raise ValueError(
            f"no .md documents found in {corpus_dir!r} -- check the path and "
            f"that you're running from the repo root"
        )
    return docs


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    """Split on '## ' (level-2) headers. Content before the first such header
    (title, Document ID block, the '---' rule) has no heading and is dropped --
    it carries no retrievable policy content."""
    lines = markdown.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current_heading and current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_heading and current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return [(h, b) for h, b in sections if b]


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _split_paragraphs_preserving_tables(body: str) -> list[str]:
    """Split on blank lines, but a contiguous run of '|' table lines is kept
    as ONE paragraph regardless of length, so a table is never split later."""
    paragraphs: list[str] = []
    current: list[str] = []
    in_table = False
    for line in body.splitlines():
        if _is_table_line(line):
            in_table = True
            current.append(line)
            continue
        if line.strip() == "":
            if in_table:
                current.append(line)  # blank line inside a table run: keep together
                continue
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        in_table = False
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    return [p for p in paragraphs if p]


def chunk_document(doc_id: str, doc_title: str, markdown: str,
                    max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    section_index = 0

    def _emit(heading: str, text: str):
        nonlocal section_index
        section_index += 1
        chunks.append(Chunk(
            chunk_id=f"{doc_id}-{section_index}",
            doc_id=doc_id, doc_title=doc_title,
            heading=heading, text=text,
        ))

    for heading, body in _split_sections(markdown):
        if len(body) <= max_chars:
            _emit(heading, body)
            continue

        paragraphs = _split_paragraphs_preserving_tables(body)
        current = ""
        for para in paragraphs:
            candidate = f"{current}\n\n{para}".strip() if current else para
            if len(candidate) > max_chars and current:
                _emit(heading, current)
                current = para
            else:
                current = candidate
        if current:
            _emit(heading, current)

    return chunks


def load_and_chunk_corpus(corpus_dir: str = "northstar-policy-docs") -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in load_raw_documents(corpus_dir):
        chunks.extend(chunk_document(doc["doc_id"], doc["title"], doc["text"]))
    return chunks

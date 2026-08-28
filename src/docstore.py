"""Läser och listar dokument i kunskapsbank-repositoriet.

Används både av webb-GUI:t (bläddring) och av indexeraren (för att veta
vilka .md-filer som finns och vad de innehåller).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Document:
    path: Path             # absolut sökväg till .md-filen
    rel_path: str          # sökväg relativt kunskapsbank-roten, "/" som separator
    title: str
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    source_file: str = ""
    source_hash: str = ""
    source_type: str = ""
    converted_at: str = ""
    body: str = ""
    modified_at: float = 0.0
    search_excerpt: str = ""


def parse_markdown_file(path: Path) -> tuple[dict, str]:
    """Delar upp en .md-fil i (frontmatter-dict, brödtext)."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                meta = {}
            body = parts[2].lstrip("\n")
            return meta, body
    return {}, text


def load_document(kb_root: Path, path: Path) -> Document:
    meta, body = parse_markdown_file(path)
    rel = path.relative_to(kb_root).as_posix()
    return Document(
        path=path,
        rel_path=rel,
        title=meta.get("title") or path.stem,
        tags=meta.get("tags") or [],
        summary=meta.get("summary") or "",
        source_file=meta.get("source_file") or "",
        source_hash=meta.get("source_hash") or "",
        source_type=meta.get("source_type") or "",
        converted_at=meta.get("converted_at") or "",
        body=body,
        modified_at=path.stat().st_mtime,
    )


def list_documents(kb_root: Path) -> list[Document]:
    """Listar alla .md-dokument i kunskapsbanken (rekursivt, images/ hoppas över)."""
    if not kb_root.exists():
        return []
    docs = []
    for p in sorted(kb_root.rglob("*.md")):
        rel_parts = p.relative_to(kb_root).parts
        if rel_parts and rel_parts[0] == "images":
            continue
        docs.append(load_document(kb_root, p))
    return docs


def all_tags(docs: list[Document]) -> list[str]:
    seen: set[str] = set()
    for d in docs:
        seen.update(d.tags)
    return sorted(seen)

"""Genererar YAML frontmatter för konverterade Markdown-filer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


def build_frontmatter(
    *,
    title: str,
    source_file: str,
    source_hash: str,
    author: str = "",
    tags: list[str] | None = None,
    summary: str | None = None,
    extra: dict | None = None,
) -> str:
    """Bygger ett YAML frontmatter-block enligt kunskapsbankens metadataformat."""
    data = {
        "title": title,
        "source_file": source_file,
        "source_hash": source_hash,
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "tags": tags or [],
    }
    if author:
        data["author"] = author
    if summary:
        data["summary"] = summary
    if extra:
        data.update(extra)

    yaml_block = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_block}---\n\n"


def write_markdown_with_frontmatter(output_path: Path, frontmatter: str, body: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(frontmatter + body, encoding="utf-8")

"""Skapar och läser användardefinierade bearbetningsskills.

En skill innehåller beskrivning, instruktioner och valfria dokumentförval.
Kunskapstratten anropar aldrig någon skill-generator.
"""
from __future__ import annotations

import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import yaml

from .config import Config
from .docstore import Document, list_documents

CUSTOM_SKILLS_DIR = "_custom"


def validate_skill_documents(config: Config, paths, *, require_existing=True) -> list[str]:
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        raise ValueError("document_paths måste vara en lista med relativa .md-sökvägar.")
    root = config.paths.output.resolve()
    result = []
    for value in paths:
        value = value.replace("\\", "/")
        path = Path(value)
        full = (root / path).resolve()
        if not value or path.is_absolute() or ":" in value or ".." in path.parts or root not in full.parents or path.suffix.lower() != ".md":
            raise ValueError(f"Ogiltig dokumentsökväg: {value}")
        if require_existing and not full.is_file():
            raise ValueError(f"Dokumentet saknas: {value}. Uppdatera skillens dokumentval.")
        normalized = path.as_posix()
        if normalized not in result:
            result.append(normalized)
    return result


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")


def list_custom_skills(config: Config) -> list[dict]:
    """Läser användarskapade bearbetningsskills."""
    root = config.paths.skills / CUSTOM_SKILLS_DIR
    result = []
    if not root.exists():
        return result
    for path in sorted(root.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(meta, dict):
            continue
        document_error = ""
        try:
            document_paths = validate_skill_documents(config, meta.get("document_paths", []), require_existing=False)
        except ValueError as exc:
            document_paths = []
            document_error = str(exc)
        body = parts[2].lstrip() if len(parts) > 2 else ""
        result.append({
            "id": f"custom:{path.parent.name}",
            "slug": path.parent.name,
            "name": meta.get("display_name") or meta.get("name") or path.parent.name,
            "description": meta.get("description") or "",
            "instructions": body,
            "document_paths": document_paths,
            "document_error": document_error,
            "path": path,
            "rel_path": path.relative_to(config.paths.skills).as_posix(),
        })
    return result


def create_custom_skill(
    config: Config,
    *,
    name: str,
    description: str,
    instructions: str,
    document_paths: list[str] | None = None,
) -> dict:
    """Skapar en bearbetningsskill med valfria dokumentförval."""
    slug = _slugify(name)
    if not slug:
        raise ValueError("Namnet måste innehålla bokstäver eller siffror.")

    skill_dir = config.paths.skills / CUSTOM_SKILLS_DIR / slug
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        raise FileExistsError(f"En skill med sökvägen {slug} finns redan.")

    meta = {
        "name": slug,
        "display_name": name.strip(),
        "description": description.strip(),
        "custom": True,
        "document_paths": validate_skill_documents(config, document_paths or []),
    }
    lines = [
        "---",
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip(),
        "---",
        "",
        f"# {name.strip()}",
        "",
        instructions.strip() or "Bearbeta de valda dokumenten enligt användarens uppdrag.",
        "",
    ]

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("\n".join(lines), encoding="utf-8")
    return {"slug": slug, "path": skill_path}


def _parent_of(rel_dir: str) -> str:
    if not rel_dir:
        return ""
    parent = str(Path(rel_dir).parent)
    return "" if parent == "." else parent


def _skill_name(rel_dir: str) -> str:
    return Path(rel_dir).name if rel_dir else "oversikt"


def _group_by_folder(docs: list[Document]) -> dict[str, list[Document]]:
    groups: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        groups[_parent_of(d.rel_path)].append(d)
    return groups


def _all_dirs(groups: dict[str, list[Document]]) -> set[str]:
    dirs = set(groups.keys()) | {""}
    for rel_dir in list(dirs):
        parts = [p for p in rel_dir.split("/") if p]
        for i in range(len(parts)):
            dirs.add("/".join(parts[:i]))
    return dirs


def _direct_children(all_dirs: set[str], rel_dir: str) -> list[str]:
    return sorted(d for d in all_dirs if d != rel_dir and _parent_of(d) == rel_dir)


def _build_description(rel_dir: str, docs: list[Document], total_under: int) -> str:
    tags = sorted({t for d in docs for t in d.tags})
    titles = [d.title for d in docs[:4]]
    location = f"kunskapsbank/{rel_dir}" if rel_dir else "kunskapsbankens rot"
    desc = f"Underlag från {location} ({total_under} dokument totalt)."
    if titles:
        desc += " Bland annat: " + ", ".join(titles) + "."
    if tags:
        desc += f" Taggar: {', '.join(tags[:8])}."
    return desc


def _render_skill_md(
    rel_dir: str,
    docs_here: list[Document],
    children: list[str],
    kb_root: Path,
    skills_root: Path,
    total_under: int,
) -> str:
    skill_dir = skills_root / rel_dir if rel_dir else skills_root
    name = _skill_name(rel_dir)
    description = _build_description(rel_dir, docs_here, total_under)

    lines = ["---", f"name: {name}", f"description: {description}", "---", "", f"# {name}", ""]

    if rel_dir:
        lines.append(f"Automatiskt genererat underlag ur kunskapsbanken (`kunskapsbank/{rel_dir}`).")
    else:
        lines.append("Automatiskt genererat underlag ur kunskapsbankens rotnivå.")
    lines.append("Öppna ett dokument nedan för det fullständiga innehållet.")
    lines.append("")

    if docs_here:
        lines.append("## Dokument")
        lines.append("")
        for d in sorted(docs_here, key=lambda x: x.title.lower()):
            target = (kb_root / d.rel_path).resolve()
            rel_link = os.path.relpath(target, start=skill_dir.resolve())
            tag_part = f" (taggar: {', '.join(d.tags)})" if d.tags else ""
            summary = f" — {d.summary}" if d.summary else ""
            lines.append(f"- [{d.title}]({rel_link}){tag_part}{summary}")
        lines.append("")

    if children:
        lines.append("## Underkategorier")
        lines.append("")
        for child in children:
            child_skill_md = (skills_root / child / "SKILL.md").resolve()
            rel_link = os.path.relpath(child_skill_md, start=skill_dir.resolve())
            lines.append(f"- [{_skill_name(child)}]({rel_link})")
        lines.append("")

    if not docs_here and not children:
        lines.append("_Inga dokument här ännu._")
        lines.append("")

    return "\n".join(lines)


def _totals(dirs: set[str], groups: dict[str, list[Document]]) -> dict[str, int]:
    totals: dict[str, int] = {d: 0 for d in dirs}
    for rel_dir, docs_here in groups.items():
        node = rel_dir
        while True:
            totals[node] = totals.get(node, 0) + len(docs_here)
            if not node:
                break
            node = _parent_of(node)
    return totals


def skill_tree(config: Config) -> list[dict]:
    """Samma gruppering som build_skills(), men som data - för GUI:t att
    rendera med sina egna (korrekta) interna länkar istället för de
    filsystem-relativa länkarna i själva SKILL.md-filerna."""
    docs = list_documents(config.paths.output)
    groups = _group_by_folder(docs)
    dirs = _all_dirs(groups)
    totals = _totals(dirs, groups)

    nodes = []
    for rel_dir in sorted(dirs):
        docs_here = sorted(groups.get(rel_dir, []), key=lambda d: d.title.lower())
        nodes.append({
            "rel_dir": rel_dir,
            "name": _skill_name(rel_dir),
            "description": _build_description(rel_dir, docs_here, totals.get(rel_dir, 0)),
            "docs": docs_here,
            "children": _direct_children(dirs, rel_dir),
            "total": totals.get(rel_dir, 0),
        })
    return nodes


def skill_doc_paths(config: Config) -> dict[str, list[str]]:
    """Rel_path-lista med ALLA dokument i en skills undanträ (rekursivt).

    Används av chattens "lägg till skill"-funktion: när användaren lägger
    till en skill i kontexten ska hela dess dokumentträd följa med, inte
    bara dokumenten direkt i den mappen.
    """
    docs = list_documents(config.paths.output)
    groups = _group_by_folder(docs)
    dirs = _all_dirs(groups)

    result: dict[str, list[str]] = {}
    for rel_dir in dirs:
        prefix = f"{rel_dir}/" if rel_dir else ""
        paths: list[str] = []
        for other_dir, docs_here in groups.items():
            if other_dir == rel_dir or other_dir.startswith(prefix):
                paths.extend(d.rel_path for d in docs_here)
        result[rel_dir] = sorted(set(paths))
    return result


def build_skills(config: Config) -> dict:
    """Äldre kompatibilitetsfunktion; anropas inte av pipeline, GUI eller CLI."""
    docs = list_documents(config.paths.output)
    groups = _group_by_folder(docs)
    dirs = _all_dirs(groups)
    totals = _totals(dirs, groups)

    skills_root = config.paths.skills
    skills_root.mkdir(parents=True, exist_ok=True)
    kb_root = config.paths.output.resolve()

    written: list[str] = []
    for rel_dir in sorted(dirs):
        docs_here = groups.get(rel_dir, [])
        children = _direct_children(dirs, rel_dir)
        skill_dir = skills_root / rel_dir if rel_dir else skills_root
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md_path = skill_dir / "SKILL.md"

        content = _render_skill_md(
            rel_dir, docs_here, children, kb_root, skills_root.resolve(), totals.get(rel_dir, 0)
        )
        skill_md_path.write_text(content, encoding="utf-8")
        written.append(str(skill_md_path.relative_to(skills_root.parent)))

    return {"skills": len(written), "documents": len(docs), "paths": written}

"""Huvudpipeline: skannar inboxen, konverterar filer och uppdaterar registret.

Flöde per fil (motsvarar tratten i arkitekturbilden):
  1. Inbox / Landningsbrygga  -> discover_files()
  2. LLM Wiki-motor           -> Converter (MarkItDown) + Enricher (metadata)
  3. Kunskapsbank-repositorium -> .md-fil med YAML frontmatter skrivs till output
  4. Registret uppdateras så filen inte processas igen nästa körning
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .converter import Converter
from .enrich import Enricher
from .frontmatter import build_frontmatter, write_markdown_with_frontmatter
from .registry import Registry, hash_file

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: Config):
        self.config = config
        self.config.paths.ensure_exist()
        self.registry = Registry(config.paths.registry_db)
        self.converter = Converter(config)
        self.enricher = Enricher(config)

    def close(self) -> None:
        self.registry.close()

    def discover_files(self) -> list[Path]:
        """Listar alla filer i inboxen med en filändelse pipelinen känner till."""
        inbox = self.config.paths.inbox
        exts = {e.lower() for e in self.config.supported_extensions}
        return sorted(
            p for p in inbox.rglob("*")
            if p.is_file() and p.suffix.lower() in exts
        )

    def process_all(self, *, force: bool = False) -> dict:
        """Bearbetar alla nya/ändrade filer i inboxen. Returnerar en statistik-dict."""
        stats = {"processed": 0, "skipped": 0, "errors": 0}
        files = self.discover_files()
        logger.info("Hittade %d fil(er) i inboxen (%s)", len(files), self.config.paths.inbox)

        for source_path in files:
            content_hash = hash_file(source_path)
            if not force and self.registry.already_processed(source_path, content_hash):
                stats["skipped"] += 1
                continue

            self.registry.mark_pending(source_path, content_hash)
            try:
                self._process_file(source_path, content_hash)
                stats["processed"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Fel vid bearbetning av %s", source_path)
                self.registry.mark_error(source_path, content_hash, str(exc))
                stats["errors"] += 1

        return stats

    def _process_file(self, source_path: Path, content_hash: str) -> None:
        rel = source_path.relative_to(self.config.paths.inbox)
        images_dir = self.config.paths.images

        result = self.converter.convert(source_path, images_dir)
        meta = self.enricher.enrich(
            result.markdown, fallback_title=result.title_guess or source_path.stem
        )

        tags = list(dict.fromkeys([*self.config.frontmatter.default_tags, *meta["tags"]]))
        frontmatter = build_frontmatter(
            title=meta["title"],
            source_file=str(rel).replace("\\", "/"),
            source_hash=content_hash,
            author=self.config.frontmatter.author,
            tags=tags,
            summary=meta["summary"],
            extra={"source_type": source_path.suffix.lower().lstrip(".")},
        )

        output_path = (self.config.paths.output / rel).with_suffix(".md")
        write_markdown_with_frontmatter(output_path, frontmatter, result.markdown)

        # Flytta originalfilen till arkivet så inboxen hålls ren och filen
        # inte hittas igen av discover_files() nästa körning.
        archive_path = self.config.paths.processed_archive / rel
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.replace(archive_path)

        self.registry.mark_done(source_path, content_hash, output_path)
        logger.info("Klar: %s -> %s", rel, output_path)

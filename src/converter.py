"""Konverterar filer till Markdown med MarkItDown, inklusive bildhantering.

MarkItDown kan, om den får en llm_client + llm_model, generera en
AI-beskrivning av bilder (både fristående bildfiler och bilder inbäddade i
t.ex. pptx/docx) direkt i markdown-texten. Utöver det sparar den här
modulen även undan själva bildfilen i kunskapsbankens images/-mapp så att
originalbilden finns kvar och kan visas/länkas, inte bara AI-textbeskrivningen.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .ai_client import build_openai_client
from .config import Config

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}


@dataclass
class ConversionResult:
    markdown: str
    saved_images: list[Path] = field(default_factory=list)
    title_guess: str | None = None


class Converter:
    """Wrapper runt MarkItDown som även sparar undan bildfiler lokalt."""

    def __init__(self, config: Config):
        self.config = config
        self._markitdown = None
        self._client = None

    def _get_markitdown(self):
        if self._markitdown is not None:
            return self._markitdown

        from markitdown import MarkItDown

        llm_client = None
        llm_model = None
        if self.config.ai.enabled and self.config.ai.use_for_image_description:
            try:
                self._client = build_openai_client(self.config.ai)
                llm_client = self._client
                llm_model = self.config.ai.model
            except RuntimeError as exc:
                logger.warning("AI-bildbeskrivning avstängd: %s", exc)

        self._markitdown = MarkItDown(llm_client=llm_client, llm_model=llm_model)
        return self._markitdown

    def convert(self, source_path: Path, images_out_dir: Path) -> ConversionResult:
        """Konverterar en fil till markdown och hanterar ev. bildexport."""
        md = self._get_markitdown()
        result = md.convert(str(source_path))
        markdown_text = result.text_content or ""

        saved_images: list[Path] = []
        if source_path.suffix.lower() in IMAGE_EXTENSIONS:
            # Fristående bildfil: spara originalet i kunskapsbankens
            # bildmapp och länka in den ovanför AI-beskrivningen som
            # MarkItDown redan skrivit in i markdown-texten.
            images_out_dir.mkdir(parents=True, exist_ok=True)
            dest = self._unique_path(images_out_dir / source_path.name)
            shutil.copy2(source_path, dest)
            saved_images.append(dest)
            rel = f"images/{dest.name}"
            markdown_text = f"![{source_path.stem}]({rel})\n\n{markdown_text}"

        title_guess = self._guess_title(markdown_text, source_path)
        return ConversionResult(markdown=markdown_text, saved_images=saved_images, title_guess=title_guess)

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """Undviker att skriva över en befintlig fil med samma namn."""
        if not path.exists():
            return path
        stem, suffix = path.stem, path.suffix
        i = 1
        while True:
            candidate = path.with_name(f"{stem}_{i}{suffix}")
            if not candidate.exists():
                return candidate
            i += 1

    @staticmethod
    def _guess_title(markdown_text: str, source_path: Path) -> str:
        for line in markdown_text.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return source_path.stem

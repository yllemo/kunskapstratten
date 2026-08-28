"""Metadataberikning (titel, taggar, sammanfattning) via lokal AI.

Detta är separat från bildbeskrivningen i converter.py: här skickas hela
(det konverterade) dokumentets textinnehåll till den lokala modellen för
att föreslå bättre titel, en kort sammanfattning och taggar till
frontmatter. Om AI:n är avstängd eller inte svarar används enkla
fallback-värden så att pipelinen aldrig stoppas av detta steg.
"""
from __future__ import annotations

import json
import logging

from .ai_client import build_openai_client, chat_completion
from .config import Config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Du är en assistent som analyserar dokument för en kunskapsbank. "
    "Svara ENDAST med giltig JSON, utan markdown-kodblock, i formatet: "
    '{"title": "...", "summary": "...", "tags": ["...", "..."]}. '
    "Håll summary till max två meningar och föreslå 3-6 taggar på svenska."
)


class Enricher:
    def __init__(self, config: Config):
        self.config = config
        self._client = None
        if config.ai.enabled and config.ai.use_for_metadata_enrichment:
            try:
                self._client = build_openai_client(config.ai)
            except RuntimeError as exc:
                logger.warning("Metadataberikning avstängd: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def enrich(self, markdown_text: str, fallback_title: str) -> dict:
        """Returnerar {"title", "summary", "tags"} — via AI om möjligt, annars fallback."""
        if not self._client:
            return {"title": fallback_title, "summary": "", "tags": []}

        excerpt = markdown_text[:4000]
        try:
            raw = chat_completion(
                self._client,
                self.config.ai.model,
                SYSTEM_PROMPT,
                f"Dokumentets innehåll:\n\n{excerpt}",
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            data = json.loads(raw)
            return {
                "title": data.get("title") or fallback_title,
                "summary": data.get("summary", ""),
                "tags": data.get("tags", []),
            }
        except Exception as exc:  # noqa: BLE001 - AI-fel ska aldrig stoppa pipelinen
            logger.warning("AI-berikning misslyckades, använder fallback: %s", exc)
            return {"title": fallback_title, "summary": "", "tags": []}

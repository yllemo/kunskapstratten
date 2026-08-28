"""Konfigurationshantering för Kunskapstratten."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AIConfig:
    """Inställningar för den lokala AI:n (OpenAI-kompatibelt API).

    Används bara i ingest-steget (bildbeskrivningar + metadataberikning),
    inte för frågesvar - det sköts av skills-konceptet istället, se
    skillbuilder.py.
    """
    enabled: bool = True
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "not-needed"
    model: str = "gemma4:26b"
    context_window: int = 32768
    use_for_image_description: bool = True
    use_for_metadata_enrichment: bool = True
    timeout: int = 120


@dataclass
class GuiConfig:
    """Inställningar för det lokala webb-GUI:t (bläddra kunskapsbank + skills)."""
    host: str = "127.0.0.1"
    port: int = 5000


@dataclass
class PathsConfig:
    """Alla mappar pipelinen jobbar mot."""
    inbox: Path = Path("./inbox")
    processed_archive: Path = Path("./processed")
    output: Path = Path("./kunskapsbank")
    images: Path = Path("./kunskapsbank/images")
    skills: Path = Path("./skills")
    registry_db: Path = Path("./data/registry.db")
    logs: Path = Path("./logs")

    def ensure_exist(self) -> None:
        for p in (self.inbox, self.processed_archive, self.output,
                  self.images, self.skills, self.registry_db.parent, self.logs):
            Path(p).mkdir(parents=True, exist_ok=True)


@dataclass
class FrontmatterConfig:
    author: str = ""
    default_tags: list[str] = field(default_factory=list)


@dataclass
class Config:
    paths: PathsConfig
    ai: AIConfig
    frontmatter: FrontmatterConfig
    gui: GuiConfig = field(default_factory=GuiConfig)
    supported_extensions: list[str] = field(default_factory=lambda: [
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
        ".txt", ".md", ".html", ".htm", ".csv", ".json", ".xml",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
        ".mp3", ".wav", ".zip", ".epub",
    ])

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Config":
        """Läser config.yaml. Saknas filen används inbyggda standardvärden."""
        path = Path(path)
        raw: dict[str, Any] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}

        paths_raw = raw.get("paths", {})
        paths = PathsConfig(
            inbox=Path(paths_raw.get("inbox", "./inbox")),
            processed_archive=Path(paths_raw.get("processed_archive", "./processed")),
            output=Path(paths_raw.get("output", "./kunskapsbank")),
            images=Path(paths_raw.get("images", "./kunskapsbank/images")),
            skills=Path(paths_raw.get("skills", "./skills")),
            registry_db=Path(paths_raw.get("registry_db", "./data/registry.db")),
            logs=Path(paths_raw.get("logs", "./logs")),
        )

        ai_raw = raw.get("ai", {})
        ai = AIConfig(
            enabled=ai_raw.get("enabled", True),
            base_url=ai_raw.get("base_url", "http://localhost:11434/v1"),
            api_key=ai_raw.get("api_key", "not-needed"),
            model=ai_raw.get("model", "gemma4:26b"),
            context_window=int(ai_raw.get("context_window", 32768)),
            use_for_image_description=ai_raw.get("use_for_image_description", True),
            use_for_metadata_enrichment=ai_raw.get("use_for_metadata_enrichment", True),
            timeout=ai_raw.get("timeout", 120),
        )

        fm_raw = raw.get("frontmatter", {})
        frontmatter = FrontmatterConfig(
            author=fm_raw.get("author", ""),
            default_tags=fm_raw.get("default_tags", []),
        )

        gui_raw = raw.get("gui", {})
        gui = GuiConfig(
            host=gui_raw.get("host", "127.0.0.1"),
            port=gui_raw.get("port", 5000),
        )

        cfg = cls(paths=paths, ai=ai, frontmatter=frontmatter, gui=gui)
        if "supported_extensions" in raw:
            cfg.supported_extensions = raw["supported_extensions"]
        return cfg

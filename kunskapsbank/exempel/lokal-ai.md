---
title: Ansluta en lokal AI
source_file: levereras med paketet
source_hash: ''
converted_at: '2026-08-28T08:53:29.828208+00:00'
tags:
- ai
- konfiguration
author: Kunskapstratten-projektet
summary: Så pekar du config.yaml mot LM Studio, Ollama eller vLLM för bildbeskrivningar
  och metadataberikning vid ingest.
source_type: exempel
---

## Konfiguration

Öppna `config.yaml` och peka `ai.base_url` mot din lokala server:

```yaml
ai:
  enabled: true
  base_url: "http://localhost:1234/v1"   # LM Studio
  # base_url: "http://localhost:11434/v1"  # Ollama
  # base_url: "http://localhost:8000/v1"   # vLLM
  model: "local-model"
  use_for_image_description: true
  use_for_metadata_enrichment: true
```

Servern måste exponera ett OpenAI-kompatibelt `/v1/chat/completions`-API.
Modellnamnet i `model` ska matcha det din server förväntar sig.

## Vad AI:n används till

Den lokala AI:n används bara i **ingest-steget** (steg 2 i tratten, se
*Arkitekturen*): bildbeskrivningar som vävs in i markdown-texten, samt
förslag på titel, sammanfattning och taggar till frontmatter. Är AI:n
avstängd eller otillgänglig fungerar allt ändå - pipelinen faller
tillbaka på filnamnet som titel och lämnar sammanfattning/taggar tomma.
Skills-katalogen (steg 4) kräver ingen AI alls för att byggas.

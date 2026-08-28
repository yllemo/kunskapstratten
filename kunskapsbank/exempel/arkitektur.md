---
title: 'Arkitekturen: från inbox till skills'
source_file: levereras med paketet
source_hash: ''
converted_at: '2026-08-28T08:53:29.827368+00:00'
tags:
- arkitektur
- koncept
author: Kunskapstratten-projektet
summary: 'Beskriver flödet: inbox, MarkItDown-konvertering, kunskapsbank-repositorium
  och genererade SKILL.md-filer - helt utan RAG.'
source_type: exempel
---

## Fyra lager

1. **Inbox / landningsbrygga** - filer du lägger in, i valfri mappstruktur.
2. **LLM Wiki-motor** - MarkItDown konverterar varje fil till Markdown. Om en lokal AI är konfigurerad beskrivs bilder automatiskt och ett YAML frontmatter-block med titel, sammanfattning och taggar genereras.
3. **Kunskapsbank-repositorium** - de färdiga `.md`-filerna, med samma mappstruktur som inboxen.
4. **Bearbetningsskills** - återanvändbara funktioner där användaren väljer vilka Markdown-dokument som ska behandlas vid varje körning.

## Varför inte RAG?

Ingen embedding-sökning, inget vektorindex och ingen inbyggd
frågemotor behövs. En AI-agent som redan känner igen SKILL.md-mönstret
(till exempel Claude Code) kan själv läsa `description`-fälten och
avgöra vilken `SKILL.md` som är relevant för en given uppgift, och
bara öppna de dokument den faktiskt behöver. Det håller lösningen
enkel, helt lokal och lätt att felsöka - du kan alltid öppna en
`SKILL.md`-fil i en vanlig textredigerare och se exakt vad en agent
skulle se.

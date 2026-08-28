---
title: Vad är en bearbetningsskill?
source_file: levereras med paketet
source_hash: ''
converted_at: '2026-08-28T00:00:00+00:00'
tags:
- skills
- koncept
source_type: md
author: Kunskapstratten-projektet
summary: Förklarar hur en skill definierar en återanvändbar AI-funktion som körs mot dokument användaren väljer.
---

# Vad är en bearbetningsskill?

En skill i Kunskapstratten är en återanvändbar funktion för att behandla valda
delar av kunskapsbanken. Skillen definieras i en `SKILL.md` med:

- `name` och `description` i YAML-frontmatter,
- instruktioner för hur AI:n ska arbeta,
- eventuella krav på resultatets struktur och kvalitet.

Skillen innehåller inte en fast lista med kunskapsdokument. När den körs väljer
användaren exakt vilka `.md`-filer som ska ingå. Samma skill kan därför användas
för olika projekt, ämnen och dokumenturval.

## Exempel

Den medföljande skillen **Sammanfatta dokument** kan köras mot ett enda
mötesprotokoll eller en hel grupp rapporter. Instruktionen är densamma, medan
underlaget väljs för den aktuella körningen.

Resultatet strömmas som Markdown och kan kopieras eller sparas tillbaka som ett
nytt dokument i kunskapsbanken.

Kunskapstratten genererar aldrig skills automatiskt från mappstrukturen. Nya
skills skapas i GUI:t och kan redigeras som kod med Monaco Editor.

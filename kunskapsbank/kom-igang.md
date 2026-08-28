---
title: Kom igång med Kunskapstratten
source_file: levereras med paketet
source_hash: ''
converted_at: '2026-08-28T08:53:29.826340+00:00'
tags:
- guide
- kom-igång
author: Kunskapstratten-projektet
summary: Kort guide för hur du lägger till egna filer, bearbetar dem och håller skills-katalogen
  uppdaterad.
source_type: exempel
---

## Så fungerar det

1. **Lägg filer i `inbox/`** - PDF, Word, PowerPoint, Excel, bilder, HTML, textfiler m.m. Mappstrukturen bevaras i kunskapsbanken.
2. **Kör `python run.py process`** (eller klicka **Uppdatera** i det här GUI:t). Varje fil konverteras till Markdown med MarkItDown, får ett YAML frontmatter-block och flyttas till `processed/`.
3. **Välj en bearbetningsskill i GUI:t** och markera vilka Markdown-dokument som ska behandlas. Kunskapstratten skapar inga skills automatiskt.
4. **Bläddra eller låt en agent läsa `skills/`.** Du kan själv utforska innehållet här i GUI:t, eller peka en lokal AI-agent (t.ex. Claude Code) mot `skills/`-mappen så den kan navigera strukturen själv.

## Ta bort exempeldokumenten

De fyra dokument du ser nu (det här, samt de tre under *exempel/*) är
medskickade som startdata så att GUI:t inte känns tomt direkt efter
uppackning. Ta bort dem när du är redo för dina egna:

```bash
rm -rf kunskapsbank/kom-igang.md kunskapsbank/exempel
python run.py skills
```

---
name: fornnordisk-pseudonymisering
display_name: Fornnordisk pseudonymisering (demo)
description: Ett humoristiskt demoexempel som letar efter personuppgifter och ersätter personnamn med påhittade fornnordiska namn. Inte för seriös produktion.
custom: true
demo_only: true
production_ready: false
---

# Fornnordisk pseudonymisering

> **Varning: roligt demoexempel – inte för seriös produktion.** AI-baserad
> identifiering kan missa personuppgifter eller förändra innehållets betydelse.
> Resultatet är pseudonymiserat, inte garanterat anonymiserat, och måste alltid
> granskas manuellt. Använd inte denna skill som grund för juridiska,
> säkerhetsmässiga eller regulatoriska beslut.

Analysera samtliga valda dokument och leta efter uppgifter som kan identifiera
en fysisk person, exempelvis:

- fullständiga namn, förnamn, efternamn, initialer och smeknamn,
- personnummer, födelsedatum, telefonnummer och e-postadresser,
- bostadsadresser och andra exakta kontaktuppgifter,
- användarnamn, kundnummer, anställningsnummer och liknande identifierare,
- kombinationer av yrkesroll, arbetsplats, ort, relationer eller händelser som
  indirekt kan peka ut en person.

## Bearbetningsregler

1. Ersätt varje identifierad person med ett påhittat och lättsamt fornnordiskt
   namn, exempelvis **Torulf Skäggstorm**, **Sigrid Runristare**, **Freja
   Fjordblick**, **Ragnvald Korpaxel** eller **Astrid Mjödviskare**.
2. Använd samma ersättningsnamn konsekvent för samma person i alla valda
   dokument. Ge olika personer olika namn.
3. Ersätt övriga direkta identifierare med tydliga kategoriska platshållare,
   exempelvis `[PERSONNUMMER BORTTAGET]`, `[E-POST BORTTAGEN]`,
   `[TELEFONNUMMER BORTTAGET]` och `[ADRESS BORTTAGEN]`.
4. Bevara dokumentets sakliga innebörd, struktur och ton så långt det går.
   Ändra inte organisationer, produkter eller geografiska namn om de inte i
   sammanhanget fungerar som en direkt eller indirekt personidentifierare.
5. Gissa inte känsliga uppgifter och lägg aldrig till nya personuppgifter.
6. Om en uppgift är osäker, markera den med `[MÖJLIG PERSONUPPGIFT – GRANSKA]`
   istället för att låtsas att bedömningen är säker.

## Resultat

Returnera:

1. den bearbetade texten i Markdown,
2. en separat granskningsrapport med kategorier och antal ersättningar,
3. en lista över osäkra eller indirekta identifierare som behöver manuell
   kontroll,
4. den tydliga slutvarningen: **Detta är ett humoristiskt demoresultat och inte
   verifierad anonymisering. Använd inte i seriös produktion.**

Visa inte en nyckel som kopplar originalnamn till ersättningsnamn i resultatet.

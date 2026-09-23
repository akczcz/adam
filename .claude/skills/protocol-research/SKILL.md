---
name: protocol-research
description: Postup pro průzkum a porovnání AI protokolů pro multiagentní platformy (MCP, A2A, A2UI, AG-UI, MCP Apps, AP2 a další) a pro aktualizaci znalostní báze v knowledge/protocols/. Použij vždy, když Adam chce zjistit aktuální stav protokolu, porovnat protokoly, navrhnout jejich kombinaci v architektuře, prozkoumat nový protokol, nebo když se ptá na agent-to-agent komunikaci, přístup agentů k nástrojům či agentní UI – i když slovo "protokol" výslovně nezazní.
---

# Průzkum AI protokolů

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/protocols/overview.md` a soubory dotčených protokolů.
- Zkontroluj `naposledy_overeno`. Údaje o verzích starší než ~3 měsíce ber jako neověřené.

## 2. Ověř aktuální stav z primárních zdrojů
Pořadí důvěryhodnosti:
1. Oficiální specifikace a changelog (a2a-protocol.org, modelcontextprotocol.io, docs.ag-ui.com, github.com/google/A2UI).
2. Oficiální blogy a roadmapy maintainerů.
3. Release notes SDK (GitHub releases, package registry).
4. Články komunity (Medium, dev.to) – jen pro orientaci a praktické zkušenosti, nikdy jako jediný zdroj faktu.

Pro každý protokol zjisti: aktuální verzi a datum, co se změnilo od posledního ověření,
co je deprecated, co je na roadmapě.

## 3. Analyzuj architektonicky
Pro každý protokol / srovnání odpověz:
- Kterou vrstvu řeší a co naopak neřeší?
- Jak zralý je (spec, SDK, reálná adopce)?
- Bezpečnost: autentizace, autorizace, důvěra, útočná plocha.
- Provoz: škálování, stavovost, observabilita.
- Vendor lock-in a governance (kdo protokol řídí).
- Jak se kombinuje s ostatními vrstvami, kde se překrývá.

## 4. Výstup
- Odpověď Adamovi: stručně, česky, s odkazy na zdroje; fakta odděl od doporučení.
- Pokud se změnilo něco podstatného: navrhni úpravu znalostních souborů jako diff
  (dodrž konvence z `knowledge/README.md`, aktualizuj `naposledy_overeno` a Changelog).
- Soubory změň až po Adamově souhlasu.

## 5. Nový protokol
Když narazíš na protokol, který ve znalostní bázi chybí:
vytvoř `knowledge/protocols/<nazev>.md` podle šablony z `knowledge/README.md`
a doplň ho do tabulky v `overview.md`.

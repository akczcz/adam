---
name: framework-research
description: Postup pro průzkum, licenční prověrku a porovnání agentních frameworků a runtimů pro multiagentní platformy (kagent, Dapr Agents, LangGraph, Microsoft Agent Framework, Google ADK, CrewAI, Pydantic AI, Temporal, Restate, LiteLLM a další) a pro aktualizaci knowledge/frameworks/. Použij vždy, když Adam řeší volbu frameworku nebo runtimu, ptá se na licenci či governance open-source projektu, na durable execution, na přenositelnost mezi cloudy a on-premises, na vendor lock-in, nebo chce porovnat či benchmarkovat agentní frameworky – i když slovo "framework" výslovně nezazní.
---

# Průzkum agentních frameworků

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/frameworks/overview.md`, `kriteria.md` a `licencni-vzorce.md`.
- U dotčených kandidátů i jejich vlastní soubor.
- Zkontroluj `naposledy_overeno`. Tahle oblast stárne rychleji než protokoly – cokoliv
  staršího než ~2 měsíce ber jako neověřené, obzvlášť licence a stupně zralosti u nadací.

## 2. Licenci ověřuj u produkčního runtimu, ne u repozitáře

**Nejčastější chyba je přečíst `LICENSE` v kořeni repa a skončit.** Postup:

1. Zjisti, které balíčky se reálně nasazují do produkce – ne které se importují v prototypu.
2. U každého ověř licenci v **package registry** (PyPI, npm, Maven), ne jen v repu.
   Registry uvádí licenci publikovaného artefaktu.
3. Hledej v repu adresáře `enterprise/`, `ee/`, `pro/` – skoro jistě mají vlastní licenci.
4. Ověř, jestli projekt vyžaduje **CLA** (`CONTRIBUTING.md`, bot u pull requestů).
5. Zjisti, kdo vlastní copyright a jestli je projekt pod nadací. U CNCF i stupeň
   zralosti (Sandbox / Incubating / Graduated).

Pořadí důvěryhodnosti zdrojů:
1. Package registry a soubor `LICENSE` v repu daného balíčku.
2. Oficiální dokumentace projektu a stránky nadace (cncf.io, apache.org, lfaidata.foundation).
3. Oficiální blogy a oznámení maintainerů.
4. Články komunity – jen pro orientaci a jako vodítko, kam se podívat. **Nikdy jako zdroj licenčního faktu.**

## 3. Prověř podle kritérií
Projdi kandidáta proti `knowledge/frameworks/kriteria.md`:
- Nejdřív vyřazovací A1–A5. Kdo neprojde, dál se nebodovává.
- Pak bodovaná B1–B8.

U licencí typu BUSL, ELv2 a SSPL nerozhoduj sám – označ to jako **otázku na právníka**
a popiš, čeho přesně se omezení týká.

## 4. Analyzuj architektonicky
- Kterou vrstvu kandidát řeší a kterou naopak nechává na tobě? (viz vrstvy v `overview.md`)
- Sedí za protokolovou hranicí A2A / MCP / AG-UI, nebo vnucuje vlastní API?
- Kde je uložený stav běhu a jak drahé je ho vzít jinam?
- Jaká je cena odchodu – co zůstane funkční, když se komponenta vymění?

## 5. Výstup
- Odpověď Adamovi: česky, závěr první, fakta odděl od doporučení, u každého faktu zdroj a datum.
- Licenční zjištění vždy s odkazem na **primární** zdroj.
- Návrh úpravy souborů v `knowledge/frameworks/` jako diff (konvence z `knowledge/README.md`,
  aktualizuj `naposledy_overeno` a Changelog).
- Soubory měň až po Adamově souhlasu.

## 6. Nový kandidát
Založ `knowledge/frameworks/<nazev>.md` podle šablony z `knowledge/README.md`
a doplň řádek do tabulky síta v `overview.md`.

## 7. Čemu se vyhni
- Neporovnávej frameworky podle veřejných agentních benchmarků – měří model, ne framework.
  Důvod a alternativa jsou v `kriteria.md`.
- Neuváděj počet hvězd na GitHubu jako argument o zralosti.
- Netvrď nic o aktuální licenci z paměti. Vždy ověř.

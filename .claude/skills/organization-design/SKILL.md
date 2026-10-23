---
name: organization-design
description: Návrhová metoda pro organizační vrstvu multiagentní platformy – jak z procesů virtuální IT firmy odvodit role agentů, jejich oprávnění, rozpočty, scope paměti, sandbox profily, schvalovací body a metriky, a jak to zapsat do knowledge/organization/. Použij vždy, když Adam řeší, jaké role má virtuální firma mít, kdo smí co, kde končí autonomie agenta, kde musí být člověk, jak zakázka teče mezi agenty, předávání práce, eskalace, odpovědnost za proces, registr agentů, risk register, nebo jak změřit, že firma dělá práci dobře – i když slovo "organizace" výslovně nezazní.
---

# Návrh organizační vrstvy

Není to rešerše: nehledá se komponenta, skládá se firma z rozhodnutých vrstev. Licence a síto zde nemají smysl.

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/organization/overview.md` a `kriteria.md` (zásady A1–A6, otázky O1–O4).
- Přečti rozhodnutí v `knowledge/platforma/cilova-architektura.md` – každá role musí jít vyjádřit jen z nich:
  identita (SVID, OPA Rego), rozpočet (gateway klíč per role), paměť (scope tenant/firma, `proposed → approved`),
  sandbox (Kata/gVisor + srt profil, egress allow-list), observabilita (spany, evaly L0–L5, approval policy),
  orchestrace (Dapr Workflow aktivity, HITL), protokoly (A2A úkol = předání s artefaktem, AG-UI = dialog s člověkem).
- Přečti `knowledge/identity/regulace.md` (T1–T15) – čl. 14 lidský dohled, čl. 50 transparentnost, příloha III.

## 2. Postup: procesy → nevratné kroky → role → hranice → metriky
1. **Proces**: stavový diagram (Mermaid stateDiagram), vstup/výstup, předání, vlastník (člověk), SLA.
2. **Nevratné kroky** v procesu: push do main, deploy, komunikace ven, platba, smazání, změna oprávnění, zápis
   faktu do schválené paměti. Každý dostane: kdo schvaluje, timeout, eskalaci, reverzibilní alternativu (pokud je).
3. **Role** = svazek: oprávnění (MCP nástroje, repa, prostředí – jako Rego), rozpočet (per role a zakázku),
   scope paměti, sandbox profil (obraz, egress, approval), evaly (L0–L5 + gate). Zapiš jako YAML podle `role.md`.
4. **Hranice autonomie**: co role dělá sama, co s reviewer-agentem, co s člověkem; stop tlačítko; klasifikační brána.
5. **Metriky a odpovědnost**: per proces (doba cyklu, HITL odmítnutí, cena, incidenty), per role (pass^k, cena per úkol);
   registr agentů a risk register jako data v paměti platformy.

## 3. Pravidla návrhu
- Hranice autonomie do procesu (Dapr aktivita, OPA), nikdy jen do promptu.
- Předání mezi rolemi vždy s artefaktem (zadání, ADR, PR, runbook) – bez artefaktu není audit ani eval.
- Role je přenositelná definice, ne kód agenta; agent = instance role v procesu.
- Odvozuj z procesů a nevratných kroků, ne z org chartu lidské firmy.
- Autonomie se **rozšiřuje měřením** (eval gate, pass^k), ne nastavením.

## 4. Kde se to měří
- Harness O-1: zakázka end-to-end s mock rolemi, Dapr Workflow s HITL, gateway rozpočet, paměť, sandbox; tvrzení:
  nevratný krok bez schválení neprojde, předání nesou artefakty, cena per zakázka je v logu, stop tlačítko zastaví běh.
- Evaly rolí v Inspect (vrstvy L2–L5 z `knowledge/observability/evaluace.md`).

## 5. Výstup
- Česky, závěr první; procesy jako Mermaid, role a hranice jako tabulky/YAML; fakta regulace se zdrojem.
- Návrhy jako diff do `knowledge/organization/`; rozhodnutí do `knowledge/platforma/cilova-architektura.md`.
- Soubory měň až po Adamově souhlasu. Když chybí vstup od Adama (co firma prodává, kde je člověk povinně,
  první zákazník), polož otázku a navrhni výchozí odpověď, ne prázdné místo.

## 6. Čemu se vyhni
- Agentům s osobností a vlastní pamětí; multiagentním „debatám“ bez artefaktu; autonomii jako cíli.
- Kopírování rolí lidské firmy 1:1 (Scrum master, HR…) bez procesu, který je potřebuje.

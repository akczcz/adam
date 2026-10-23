---
tema: Organizační vrstva virtuální IT firmy – procesy, role, hranice autonomie, schvalovací body (návrh)
naposledy_overeno: 2026-10-23
zralost: n/a (návrh v0 – kostra; čeká na Adamovy odpovědi na otázky níže a na kolo 1 návrhu)
primarni_zdroje:
  - knowledge/platforma/cilova-architektura.md
  - knowledge/identity/regulace.md
  - knowledge/observability/evaluace.md
  - knowledge/memory/model-pameti.md
  - knowledge/sandbox/overview.md
---

# Organizační vrstva: virtuální IT firma

Návrhová vrstva nad sedmi rozhodnutými. Zásada z [kriteria.md](kriteria.md): **firma je sada procesů, role jsou
odvozené.** Tento soubor nahrazuje pracovní hypotézu v
[`../platforma/cilova-architektura.md`](../platforma/cilova-architektura.md) a bude se přepisovat po každém kole návrhu.

## Co firma dodává (v0 – k potvrzení Adamem)

Výchozí předpoklad: zákaznické **AI/softwarové zakázky end-to-end** – od poptávky přes návrh, implementaci, review
a nasazení po provoz a podporu; typicky v prostředí zákazníka (Azure výchozí). Tři otázky, bez kterých návrh nejde
uzavřít:

1. **Které služby firma prodává v první verzi?** (a) vývoj a dodání na zakázku, (b) provoz a podpora dodaného,
   (c) konzultace/architektura bez kódu – nebo jen (a)?
2. **Kde je člověk povinně?** jen na nevratných krocích (push do main, deploy, komunikace k zákazníkovi, platba),
   nebo i na vstupu každé zakázky (přijetí) a výstupu (předání)?
3. **Kdo je zákazník první zakázky?** reálný klient, nebo interní dogfooding (platforma staví sama sebe)?
   To určuje tenant model, klasifikační bránu AI Act a první harness.

## Tok zakázky (v0)

```mermaid
stateDiagram-v2
    [*] --> Poptavka
    Poptavka --> Zadani: Account upřesní s člověkem (AG-UI)
    Zadani --> Klasifikace: brána AI Act (příloha III?) + tenant
    Klasifikace --> Navrh: Architekt – ADR, odhad ceny (gateway)
    Navrh --> SchvaleniNavrhu: HITL – člověk zákazníka
    SchvaleniNavrhu --> Implementace: Vývojář v sandboxu per úkol
    Implementace --> Review: PR + evaly L0–L2 (Reviewer/QA)
    Review --> Implementace: změny
    Review --> SchvaleniMerge: HITL – push do main (nevratné)
    SchvaleniMerge --> Nasazeni: SRE – deploy (HITL u produkce)
    Nasazeni --> Provoz: monitoring, incidenty, post-mortem
    Provoz --> Zadani: nový požadavek
    Provoz --> [*]: ukončení
```

Každý přechod = Dapr Workflow aktivita; každý **HITL** = durable approval (dny) přes AG-UI; každé předání mezi
rolemi = A2A úkol s artefaktem (zadání, ADR, PR, runbook). Nevratné kroky: push do main, deploy, komunikace
ven (čl. 50 disclosure), platba, smazání dat – všechny kryté approval policy (hook Agent SDK + OPA) **a** gateway
(403 na `git-receive-pack` mimo schválený kanál – změřeno S1).

## Role (v0 – odvozené z toku; konkrétní oprávnění a rozpočty až v kole 1)

| Role | Proces | Smí (nástroje) | Nesmí bez člověka | Scope paměti | Sandbox profil | Evaly |
|---|---|---|---|---|---|---|
| Account | Poptávka → Zadání | AG-UI dialog, CRM/ticket MCP, čtení paměti zákazníka | slíbit cenu/termín, poslat nabídku | zákazník | žádný (bez kódu) | L3 kvalita zadání |
| Architekt | Návrh | čtení repa, paměť firmy (ADR), cena modelů z gateway, sandbox pro prototyp | schválit návrh | firma + zákazník | lehký (interpreter) | L3 ADR, odhad vs. skutečnost |
| Vývojář | Implementace | sandbox per úkol (Kata + srt), git přes gateway (jen HTTPS, bez push do main), testy, MCP repo/issue | push do main, deploy, egress mimo allow-list | zákazník (kód) + firma (konvence) | plný vývojový | L1–L2 pass^k, cena per úkol |
| Reviewer / QA | Review | čtení PR, spouštění evalů (`inspect_k8s_sandbox`), komentáře | merge, schválení faktů do paměti jen jako `reviewer` role | firma | eval sandbox | L2 shoda s člověkem |
| SRE | Nasazení → Provoz | cloud API přes MCP s krátkodobým tokenem, runbooky, ClickHouse | produkční deploy, smazání, změna oprávnění | zákazník (confidential) | provozní (CLI) | L2 incident uzavřen, MTTR |
| Governance | průřezově | čtení auditu (ClickHouse, OPA decision log), rozpočty, registr agentů, risk register | nic nepíše do faktů ani kódu | platforma | žádný | T11–T15 evidence |
| Člověk (vlastník procesu) | všude | schvaluje HITL, eskalace, stop tlačítko (T6) | – | – | – | – |

## Co vznikne v kole 1 návrhu

1. **Katalog procesů** – tabulka: proces, vstup, výstup, stavy, nevratné kroky, vlastník, SLA (`procesy.md`).
2. **Matice rolí** – YAML definice role (identita/SVID, OPA pravidla, rozpočet, scope paměti, sandbox profil,
   evaly) + šablona (`role.md`, `roles/*.yaml`).
3. **Katalog nevratných akcí a schvalovacích bodů** – kdo schvaluje co, timeouty, eskalace (`autonomie.md`).
4. **Metriky a odpovědnost** – per proces a role; registr agentů a risk register jako data (`metriky.md`).
5. **Harness O-1** – jedna zakázka end-to-end s mock rolemi přes Dapr Workflow, HITL body, gateway, paměť a
   sandbox: změří, že nevratný krok bez schválení neprojde a že předání nesou artefakty.

## Co ověřit dál

- [ ] Adamovy odpovědi na tři otázky výše (služby, kde je člověk povinně, první zákazník).
- [ ] Kolo 1 návrhu: `procesy.md`, `role.md` + `roles/*.yaml`, `autonomie.md`, `metriky.md`.
- [ ] Harness O-1 (Dapr Workflow s HITL, mock role; vyžaduje Dapr lokálně – smoke test v `tools/` existuje).
- [ ] Mapování na AI Act T1–T15 per proces (klasifikační brána, čl. 14, čl. 50).

## Changelog
- 2026-10-23: první verze – kostra: tok zakázky v0, role v0, plán kola 1, tři otázky pro Adama.

---
tema: AG-UI (Agent–User Interaction Protocol)
naposledy_overeno: 2026-09-29
zralost: early / community-driven
primarni_zdroje:
  - https://docs.ag-ui.com/introduction
  - https://www.copilotkit.ai/openmuse
---

# AG-UI – Agent–User Interaction Protocol

## Účel
Obecné obousměrné spojení mezi uživatelskou aplikací a libovolným agentním backendem.
Řeší, že agentní aplikace nezapadají do klasického request/response modelu.

## Aktuální stav
- Vzniklo z produkční praxe CopilotKit; open-source, event-based.
- Integrace: LangGraph, CrewAI, Strands Agents, Pydantic AI, Microsoft Agent Framework, Google ADK a další.
- AWS Bedrock AgentCore Runtime přidal podporu v březnu 2026.
- Standardizace probíhá spíše adopcí komunitou než formálním procesem.

## Klíčové koncepty
- Event stream: zprávy, stav agenta, tool calls, reasoning, aktivity.
- Frontend-executed actions (typované předávání akcí do frontendu a zpět).
- Human-in-the-loop: pauza, schválení, úprava, retry, eskalace bez ztráty stavu.
- Vnořená delegace se scoped stavem, tracingem a zrušením.
- Může přenášet generativní UI specifikace (A2UI, Open-JSON-UI).

## Místo v architektuře
Runtime vrstva agent ↔ frontend. Pro batch/background agenty bez uživatele zbytečná.

## Referenční implementace
**OpenMuse** (CopilotKit, MIT, **alpha**) – osobní agent pro iOS, Android a web, který
AG-UI mluví. Jako runtime pro platformu nepoužitelný (osobní aplikace, viz
[`../frameworks/overview.md`](../frameworks/overview.md#co-do-síta-nepatří-a-proč)),
ale je to **funkční ukázka, jak AG-UI vypadá v praxi**.

Má to praktickou cenu: AG-UI je díra, kterou mají oba dnešní finalisté mezi frameworky –
kagent ji odmítl jako *not planned*, Dapr Agents ji nemají vůbec. Pokud si UI vrstvu
postavíme sami, je OpenMuse použitelný jako referenční kód.

Pozor na roztříštěnost jména: vedle `CopilotKit/OpenMuse` existuje několik dalších
repozitářů téhož jména, z nichž část je archivovaná. Kanonický je ten od CopilotKitu.
Ověřeno 2026-09-29.

## Architektonické důsledky (Pozn. Adam)
- Dobrý kandidát na standardní kanál pro vlastní frontendy platformy.
- Event stream = přirozený zdroj pro observabilitu a audit interakcí.

## Otevřené otázky
- [ ] Verze a stabilita specifikace eventů.
- [ ] Autentizace a multi-tenancy.

## Changelog
- 2026-09-23: první verze.
- 2026-09-29: doplněna referenční implementace OpenMuse.

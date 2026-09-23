---
tema: Model Context Protocol (MCP)
naposledy_overeno: 2026-09-23
zralost: stable
primarni_zdroje:
  - https://modelcontextprotocol.io/specification/2026-07-28
  - https://blog.modelcontextprotocol.io/posts/2026-07-28/
  - https://blog.modelcontextprotocol.io/posts/mcp-roadmap/
---

# MCP – Model Context Protocol

## Účel
Otevřený standard pro připojení AI aplikací k externím nástrojům a zdrojům dat.
Server vystavuje schopnosti (tools, resources, prompts), klient v AI aplikaci je objevuje a používá.

## Aktuální stav
- Aktuální specifikace: **2026-07-28** (finální vydání 28. 7. 2026; RC vyšel 21. 5. 2026).
- Předchozí verze: 2025-11-25.
- Governance: Agentic AI Foundation (AAIF); Core Maintainers + Working Groups, formální deprecation policy.

## Co přinesla 2026-07-28 (největší revize od vzniku)
- **Stateless jádro** – odstraněny sessions a inicializační handshake; vzdálený MCP server je běžná HTTP služba (cacheovatelné, routovatelné).
- Header-based routing, cacheovatelné list výsledky, Multi Round-Trip Requests.
- **Autorizace** sladěná s OAuth / OpenID Connect; Enterprise-Managed Authorization.
- **Extensions framework** – rozšíření mají vlastní release cyklus:
  - **Tasks** – asynchronní dlouhotrvající operace (polling, vstup v průběhu, durable handles).
  - **MCP Apps** – interaktivní UI (grafy, formuláře) vykreslené v konverzaci hostitele; vychází z mcp-ui.
  - **Skills over MCP** – strukturované instrukce pro agentní workflow distribuované přes MCP.
- Deprecated: mimo jiné primitiva, na nichž stojí Roots a Sampling (ověřit přesný seznam v changelogu).

## Roadmapa (8/2026)
- Server Card – `.well-known` metadata pro discovery serveru bez připojení.
- Server-initiated events (webhooky, channels) – aby klienti nemuseli pollovat.
- Dozrání Tasks extension (SEP-2663) do jádra specifikace.

## Místo v architektuře
Vrstva agent → nástroje/data. Ne pro delegaci úkolů autonomním agentům (to je A2A).

## Architektonické důsledky (Pozn. Adam)
- Stateless = horizontální škálování MCP serverů za load balancerem bez sticky sessions.
- Migrace ze starších verzí: zkontrolovat použití deprecated funkcí, změny chybových kódů a auth flow.
- MCP Apps je relevantní pro UI v cizích hostitelích (Claude, ChatGPT), ne nutně pro vlastní frontend.

## Otevřené otázky
- [ ] Přesný seznam deprecated funkcí a migrační cesta.
- [ ] Stav podpory 2026-07-28 v SDK pro náš stack.
- [ ] Jak Server Card ovlivní registr/katalog MCP serverů v platformě.

## Changelog
- 2026-09-23: první verze.

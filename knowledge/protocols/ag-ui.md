---
tema: AG-UI (Agent–User Interaction Protocol)
naposledy_overeno: 2026-10-20
zralost: preview (spec 1.0 od 2026-09-17; ekosystém v migraci na 1.0)
primarni_zdroje:
  - https://docs.ag-ui.com/introduction
  - https://docs.ag-ui.com/spec/1.0/changelog.md
  - https://docs.ag-ui.com/spec/1.0/basic/versioning.md
  - https://github.com/ag-ui-protocol/ag-ui/releases
  - https://www.copilotkit.ai/openmuse
---

# AG-UI – Agent–User Interaction Protocol

## Účel
Obecné obousměrné spojení mezi uživatelskou aplikací a libovolným agentním backendem.
Řeší, že agentní aplikace nezapadají do klasického request/response modelu.

## Aktuální stav
- Vzniklo z produkční praxe CopilotKit; open-source, event-based.
- **Spec 1.0 vydána 2026-09-17** (`ag-ui-protocol` 1.0.0 PyPI, `@ag-ui/core` 1.0.0 npm, `AGUI.*` 1.0.0 NuGet).
  Aktuálně `@ag-ui/core` 1.0.3 (2026-10-16), `ag-ui-protocol` 1.0.0 bez patche. Draft 1.1 existuje, zatím
  prázdný. Ověřeno 2026-10-20 proti PyPI/npm a tagu `release/2026-09-17`.
- Versioning: `MAJOR.MINOR`, minor jen aditivní; `protocolVersion` na `RunAgentInput` (klient) a na
  `RUN_STARTED` (server); chybějící = pre-1.0 peer. Retired shapes přes deprecation registry + překladové
  middleware. Formální záruka stability 1.x explicitně nenapsaná.
- Integrace (10/2026): LangGraph, CrewAI, Mastra, Strands, AWS Bedrock AgentCore, Pydantic AI, Agno,
  LlamaIndex, AG2, Microsoft Agent Framework, Google ADK (Py+JS), Google Antigravity, Spring AI, IBM watsonx,
  Cloudflare Agents, Claude Agent SDK / Claude Managed Agents, Langroid, Omnara, Oracle Agent Spec;
  A2A middleware, MCP Apps middleware. In progress: OpenAI Agent SDK, AWS Bedrock Agents.
- Integrace se v říjnu 2026 hromadně přepínají na 1.0 (ADK 0.8.0, Strands/CrewAI 1.0.0, Mastra 2.0.0 –
  vesměs breaking; ADK 0.9.0 už vyžaduje `protocolVersion` na `RUN_STARTED`).
- AWS Bedrock AgentCore Runtime přidal podporu v březnu 2026.
- Standardizace probíhá spíše adopcí komunitou než formálním procesem.

## Klíčové koncepty
- Event stream: zprávy, stav agenta, tool calls, reasoning (`REASONING_*`, v 1.0 nahrazuje `THINKING_*`),
  aktivity (`ACTIVITY_SNAPSHOT/DELTA`, JSON Patch), subagenti (`SUBAGENT_STARTED/FINISHED/ERROR`, `subagentRunId`).
- `RUN_FINISHED.outcome` = success | interrupt | cancelled; interrupt–resume vzor; token usage na
  `RUN_FINISHED` / `RUN_ERROR`.
- Multimodální vstup (text, image, audio, video, document); `TOOL_CALL_RESULT.content` může být seznam content parts.
- Transport: HTTP+SSE a nově HTTP+Protobuf (length-prefixed frames). Neznámé eventy se zahazují s warningem,
  malformed známá hodnota je fatální (normativní spec, BCP 14).
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

Má to praktickou cenu pro dva ze tří finalistů: kagent AG-UI odmítl jako *not planned*,
Dapr Agents ji nemají vůbec. **Výjimkou je Microsoft Agent Framework** – balíček
`agent-framework-ag-ui` 1.6.0 (2026-10-15) je na PyPI Production/Stable a aktivně se vyvíjí.
**Pozor:** `requires_dist` pinuje `ag-ui-protocol<0.2,>=0.1.19`, tedy stále **0.x**, ne spec 1.0 –
nemá `REASONING_*`, interrupt outcome ani activities. Klient 1.0 ho má tolerovat (chybějící
`protocolVersion` = pre-1.0 peer, překladové middleware), ale je to nejslabší článek řetězu.
Ověřeno 2026-10-20 proti https://pypi.org/pypi/agent-framework-ag-ui/json.

Oprava: zápis z 2026-09-29 „`ag-ui-protocol` je stále 0.x“ byl už tehdy nepřesný – 1.0.0 vyšla
2026-09-17. Platí to jen pro verzi, kterou pinuje MAF.

Pozor na roztříštěnost jména: vedle `CopilotKit/OpenMuse` existuje několik dalších
repozitářů téhož jména, z nichž část je archivovaná. Kanonický je ten od CopilotKitu.
Ověřeno 2026-09-29.

## Architektonické důsledky (Pozn. Adam)
- Dobrý kandidát na standardní kanál pro vlastní frontendy platformy.
- Event stream = přirozený zdroj pro observabilitu a audit interakcí; v 1.0 usage a subagent eventy =
  hotový vstup pro FinOps a audit trail bez vlastního schématu.
- Auth a multi-tenancy ve spec 1.0 nejsou (žádná stránka security/auth v docs); řešit na transportu
  (gateway, token ↔ thread/tenant scoping). Referenční vzory z integrací: `ag_ui_adk` 0.8/0.9 (per-user
  ledger zpracovaných message ID, session state napříč replikami), `ag_ui_strands` 0.4.0 (auth guard
  před parsováním body, `THREAD_BUSY`).
- Pokud MAF zůstane finalistou: frontend (CopilotKit 1.0) a backend (MAF 0.x producent) poběží v mixu →
  otestovat lossy downgrade explicitně, logovat `protocolVersion` obou stran.

## Otevřené otázky
- [x] Verze a stabilita specifikace eventů. → 1.0 od 2026-09-17, minor jen aditivní (2026-10-20).
- [ ] Autentizace a multi-tenancy. → ve spec 1.0 nic (2026-10-20); sledovat draft 1.1.
- [ ] Kdy MAF `agent-framework-ag-ui` uvolní pin `ag-ui-protocol<0.2` a přejde na 1.x.
- [ ] Dokumentované záruky stability 1.x (deprecation registry, expirace překladových middleware).

## Changelog
- 2026-09-23: první verze.
- 2026-09-29: doplněna referenční implementace OpenMuse; opraveno tvrzení o chybějící
  podpoře u finalistů – Microsoft Agent Framework AG-UI má.
- 2026-10-20: spec 1.0 (2026-09-17), nové eventy, versioning policy, rozšířený seznam integrací; opraveno
  tvrzení o 0.x; MAF 1.6.0 stále pinuje `ag-ui-protocol<0.2`; auth/tenancy ve spec nenalezeno.

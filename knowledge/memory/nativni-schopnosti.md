---
tema: Co pro paměť dává Claude (memory tool, CLAUDE.md, auto memory, kompakce, Managed Agents), Dapr (state, Conversation, Vector API), MCP a OTEL – a kde končí „model si pamatuje“
naposledy_overeno: 2026-10-23
zralost: mixed (memory tool GA bez beta hlavičky; context editing, compaction, Managed Agents beta; Dapr Conversation a Vector API alpha; MCP server-memory demo)
primarni_zdroje:
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
  - https://platform.claude.com/docs/en/build-with-claude/context-editing
  - https://platform.claude.com/docs/en/build-with-claude/compaction
  - https://platform.claude.com/docs/en/managed-agents/memory
  - https://code.claude.com/docs/en/memory
  - https://code.claude.com/docs/en/agent-sdk/session-storage
  - https://github.com/dapr/docs (v1.18 @c725c76, v1.19 @3fcd982)
  - https://github.com/dapr/dapr-agents (@8b4cc8d)
  - https://github.com/modelcontextprotocol/modelcontextprotocol (@80041ab)
  - https://github.com/modelcontextprotocol/servers (src/memory @51b6382)
  - https://github.com/open-telemetry/semantic-conventions-genai (@9ffc7e0)
---

# Nativní schopnosti: co platforma dostane zadarmo

**Metodická poznámka (2026-10-23):** docs.dapr.io, modelcontextprotocol.io, EDPB a EUR-Lex nedostupné – Dapr, MCP a OTEL
ověřeno ze zdrojových repozitářů (commit v hlavičce), právo jen ze sekundárních zdrojů (označeno *sek.*).

## Závěr: model si nepamatuje nic

Vše, co Anthropic nabízí, je buď **klientské** (memory tool a Agent SDK ukládají tam, kam ukážeme, ale bez modelu původu
a oprávnění), nebo **hostované u Anthropic** (Managed Agents memory stores + dreams – verzování, redakce, destilace, ale
jen Anthropic cloud / AWS / GCP, **ne Azure**, ne ZDR). Prompt cache a compaction jsou optimalizace kontextu jednoho
běhu, ne paměť. → **Paměť je náš MCP server s PEP nad Dapr state / Vector API; Claude dostane `view/search`, zápis jde
přes schvalovací tok.**

| Druh paměti | Zadarmo (ověřeno) | Postavit |
|---|---|---|
| **Pracovní** | Agent SDK transcript + `SessionStore` → **`DaprSessionStore`** (ETag first-write, dedup `uuid`, sliding TTL, `project_key` = agent); server-side compaction a context editing (beta); prompt caching | jen retence (SDK ze storu nikdy nemaže) |
| **Epizodická** | trace v ClickHouse; Claude Code auto memory (typy `user/feedback/project/reference`, `modified`) – **jen lokální disk, v self-hosted/SDK vypnuto**; Managed Agents memory stores + **dreams** (destilace sessions, research preview, ne Azure) | destilace epizod do poučení **u nás** (vzor = dreams), původ (trace_id, kdo schválil), vyhledání |
| **Sémantická** | memory tool (client-side soubory `/memories`, bez modelu dat, tenantů a původu); Dapr state (tx, ETag, TTL, AES-GCM, prefix per app); **Dapr 1.19 Vector + Search API (alpha, jen Meilisearch a in-memory)**; MCP resources/tools; referenční `server-memory` (JSONL graf, single-user, „basic implementation“) | **vše podstatné**: schéma faktu s původem/datem/tenantem/confidence, PEP v MCP serveru, schvalovací zápis, konflikt faktů, výmaz vč. embeddingů |
| **Procedurální** | CLAUDE.md hierarchie (managed → user → project → local), `.claude/rules/` s `paths`, `@import`, subagent `memory: project`, skills | verzování a vyhledání v platformě (dnes git), distribuce managed CLAUDE.md do podů |

## A. Anthropic / Claude

- **Memory tool** `memory_20250818`: „doesn't require a beta header“, client-side – „`/memories` path is a prefix that your
  handler maps onto real storage“; příkazy `view/create/str_replace/insert/delete/rename`; API přidá do system promptu
  „ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE“. Bezpečnost je „your responsibility“ (path traversal,
  limity, expirace); **memory poisoning docs nezmiňují**. ZDR Yes.
- **Context editing** (beta `context-management-2025-06-27`): `clear_tool_uses_20250919`, `clear_thinking_20251015`;
  čištění invaliduje cache prefix; s memory toolem Claude dostane varování a může si uložit výsledky před vymazáním.
- **Compaction** (beta): on demand `compact-2026-09-04` a threshold `compact_20260112`; doporučeno jako primární strategie,
  memory tool pro to, co musí souhrn přežít.
- **Claude Code memory**: hierarchie managed (`/etc/claude-code/CLAUDE.md`, nelze vyloučit) → user → project (`AGENTS.md`
  alternativa) → local; `.claude/rules/*.md` s `paths`; `@import` do hloubky 4; „context, not enforced configuration“.
  **Auto memory**: `MEMORY.md` index (200 řádků / 25 KB) + topic soubory, `~/.claude/projects/<project>/memory/`,
  `autoMemoryDirectory`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`; **machine-local, v self-hosted/cloud default off**, sweep
  nemaže (`claude purge` ano). Subagent `memory: user|project|local`.
- **Agent SDK**: `setting_sources` ([] vypne CLAUDE.md), `continue_conversation`, `resume`, `fork_session`, `session_store`
  (append/load/delete/list_subkeys; dual-write, dedup `uuid`; „The SDK never deletes from your store on its own“);
  **žádná option pro paměť**. **Dapr Agents `ClaudeAgentExecutorConfig` izoluje hosta**: `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`,
  `ENABLE_CLAUDEAI_MCP_SERVERS=false`, bez `setting_sources` i `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` → v platformě auto memory
  ani CLAUDE.md neběží, dokud to nezapneme.
- **Managed Agents** (beta `managed-agents-2026-04-01`): memory stores (beta `agent-memory-2026-07-22`) – workspace-scoped,
  mount `/mnt/memory/<slug>/`, `read_write|read_only` na FS, max 8 storů, **každá změna immutable verze** (30 dní),
  `redact` pro výmaz, `content_sha256` precondition; **jediné místo, kde Anthropic jmenuje memory poisoning**
  („a successful prompt injection could write malicious content into the store… Use `read_only`“). **Dreams** (research
  preview): asynchronní destilace sessions do nového storu. Jen Anthropic cloud / AWS / GCP, ne ZDR → pro A4 jen **vzor**.

## B. Dapr 1.18 / 1.19

- **State**: CRUD, bulk, **transakce**, ETag, TTL per klíč, outbox, **AES-GCM šifrování na klientu „supported by all state
  stores“**; prefix per app-id. **Query API alpha** v 1.18 i 1.19. Postgres, Redis, Cosmos Stable (tx, ETag, TTL);
  Azure Table/Blob Stable **bez tx a TTL**.
- **Conversation API alpha** (`v1.0-alpha2`): tool calling, `responseFormat`, **PII scrubbing** (regexy: telefon, e-mail,
  IP, karty…, ne NER), response cache v sidecaru; **historii konverzace nedrží** (`ConversationContext` „TODO: rm“);
  komponenta Anthropic neposílá `cache_control`.
- **Vector + Search API jen v 1.19 (alpha)**: kolekce s `dimensions`, metadata filtry (`$eq`, `$in`, `$and`), embeddingy
  mimo scope; komponenty jen **Meilisearch a in-memory**. **dapr-agents pinuje `dapr<1.19`** → zatím nepoužitelné.
- **Dapr Agents**: `ConversationDaprStateMemory` = jedno JSON pole zpráv pod jedním klíčem (append = get+ETag+save),
  bez TTL, tenanta, původu; `ConversationVectorMemory` přes přímé klienty (Chroma, Postgres, Redis), **ne Dapr komponentu**.

## C. MCP 2026-07-28

- Resources: `lastModified` (jediný nativní nosič stáří), `ttlMs`, `cacheScope`; subscriptions přes `subscriptions/listen`;
  listy „MAY vary by the authorization presented“ → per-tenant viditelnost je spec-konformní, realizuje ji server.
- Security Considerations: „Access controls **SHOULD** be implemented for sensitive resources“ – per-resource autorizace
  **není normativní** → agentgateway `mcpAuthorization` + OPA.
- Elicitation (MRTR, `form`/`url`) použitelná pro HITL schválení zápisu; podpora v Claude Agent SDK **neověřena**.
  Roots, Sampling, Logging deprecated (SEP-2577).
- `server-memory` 2.0.0: JSONL graf, substring search, `default_user`, **žádná autentizace**, file lock; licence v přechodu
  MIT → Apache-2.0. **Demo, ne základ.**

## D. OTEL GenAI semconv

Memory spany Development: `create_memory_store`, `search_memory`, `create_memory`, `update_memory`, `upsert_memory`,
`delete_memory`; atributy `gen_ai.memory.store.id`, `gen_ai.memory.record.id`, `record.count`, Opt-In `query.text`,
`records`. **Žádný atribut pro tenanta ani původ** → vlastní `tenant.id`, `enduser.id`, `memory.provenance.trace_id`.
Event `gen_ai.evaluation.result` lze pověsit na `search_memory` span.

## E. Benchmarky – co měří a proč nestačí

| Benchmark | Měří | Proč ne firemní use case |
|---|---|---|
| LoCoMo, LongMemEval (V2 2026), MemoryAgentBench, BEAM | osobní vícesezónní dialogy, temporalita, update, forgetting | jeden uživatel, bez tenantů a původu; vendor skóre self-reported |
| **MemLeak** (NeurIPS 2026), **PiSAs**, AgentLeak, „Authorization Before Context“, GateMem | **cross-user leakage ve sdíleném vektorovém storu**: cosine retrieval vrací cizí paměť bez exploitu; jen „hard post-retrieval ownership gating“ obnoví baseline; instrukce v promptu snižují úniky jen o ~28 % | **náš use case** → filtr tenanta vynucený v DB/PEP, ne v promptu |
| **MINJA** (NeurIPS 2025), MemSecBench | memory injection jen přes dotazy, bez write přístupu | nutná karanténa a schvalování zápisu |

## F. Právo (*sek.*)

- **GDPR čl. 17 vs. embeddingy**: EDPB Opinion 28/2024 – model na osobních datech není automaticky anonymní; praxe:
  embedding osobního údaje = osobní údaj, soft-delete nestačí. Technicky: fakt i embedding sdílejí `subject_id` /
  `tenant_id` jako filtrovatelná metadata; výmaz = záznam + embedding + odvozené fakty (lineage `derived_from`) + záznam
  o výmazu bez obsahu (vzor Managed Agents `redact`).
- **AI Act čl. 10** (text z paměti): data governance vč. „origin of data… original purpose of collection“, přípravné
  operace, bias → **původ, účel a datum jako atributy záznamu**, ne volný text (M1).

## Souhrnná tabulka

| Schopnost | Kdo | Stav | Tenanti / oprávnění | Původ a datum | Výmaz |
|---|---|---|---|---|---|
| Memory tool | Anthropic API, client-side | GA bez beta hlavičky | náš handler, žádný model | ne | náš handler |
| Context editing / compaction | Anthropic API | beta | n/a | n/a | n/a |
| CLAUDE.md + rules + imports | Claude Code | GA | per stroj/repo | git | git |
| Auto memory, subagent memory | Claude Code | GA lokálně, **off v self-hosted a SDK** | machine-local | `modified`, `type` | `claude purge` |
| `SessionStore` / `DaprSessionStore` | Agent SDK / dapr-agents | GA / main (bus factor 1) | `project_key` + `session_id`, bez autorizace | `uuid`, mtime | adaptér, sliding TTL |
| Managed Agents memory stores + dreams | Anthropic cloud / AWS / GCP | beta / research preview | store per user/team, `read_only` | immutable verze 30 dní | delete / `redact` |
| Dapr state | Dapr 1.18 | Stable (query alpha) | prefix per app-id | naše schéma | TTL, delete, AES-GCM |
| Dapr Conversation API | Dapr 1.18 | alpha | ne | ne | bez historie |
| Dapr Vector / Search API | Dapr 1.19 | alpha, Meilisearch / in-memory | filtr `metadata` | `metadata` | delete by id |
| MCP resources / elicitation | MCP 2026-07-28 | spec | „SHOULD access controls“ | `lastModified`, `ttlMs` | n/a |
| `server-memory` | MCP reference | demo | žádné | ne | delete tools |
| Memory spany | OTEL semconv | Development | ne | ne | n/a |

## Co ověřit dál
- [ ] EDPB Opinion 28/2024 a text čl. 10 AI Act z primárních zdrojů.
- [ ] Elicitation a `subscriptions/listen` v Claude Agent SDK jako MCP klientu.
- [ ] Dapr query API per komponenta; kdy dapr-agents zvedne pin na Dapr 1.19 (Vector API).
- [ ] Managed Agents / memory stores v Microsoft Foundry (docs jmenují jen AWS a GCP).
- [ ] Memory tool přes agentgateway (serverově injektovaný prompt – mělo by projít).

## Changelog
- 2026-10-23: první verze z rešerše.

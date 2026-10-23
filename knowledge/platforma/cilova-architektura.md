---
tema: Cílová architektura autonomní multiagentní platformy – živý soubor rozhodnutí
naposledy_overeno: 2026-10-23
zralost: experimental
primarni_zdroje:
  - https://github.com/akczcz/adam/tree/main/knowledge
---

# Cílová architektura

Živý soubor. Každá prověřená vrstva sem vloží **jedno rozhodnutí** se zdůvodněním a riziky,
která Adam vědomě přijímá. Prázdné řádky jsou záměrně prázdné – označují, co ještě není rozhodnuto.
Detail a zdroje jsou vždy ve složce dané vrstvy, tady je jen výsledek.

## Rozhodnutí po vrstvách

| Vrstva | Rozhodnutí | Datum | Přijatá rizika | Detail |
|---|---|---|---|---|
| Agent ↔ nástroje | **MCP** jako jediná hranice k nástrojům a datům | 2026-09-23 | – | [`../protocols/mcp.md`](../protocols/mcp.md) |
| Agent ↔ agent | **A2A**, ale za vlastním adaptérem (vyměnitelné) | 2026-09-23 | A2A v1.1 ve vývoji, SDK verze se liší per framework | [`../protocols/a2a.md`](../protocols/a2a.md) |
| Agent ↔ uživatel | **AG-UI** (vlastní frontend) + **A2UI** jako payload; MCP Apps jen uvnitř cizího hostitele | 2026-09-23 | AG-UI 1.0 čerstvé, ekosystém v migraci; A2UI bez v1.0 rendererů | [`../protocols/overview.md`](../protocols/overview.md) |
| Agentní smyčka | **Claude Agent SDK** | 2026-10-21 | `claude-agent-sdk` pinnutý na 0.2.x v Dapr Agents | [`../frameworks/overview.md`](../frameworks/overview.md) |
| Orchestrace a durable execution | **Dapr Agents** (`ClaudeAgentExecutor` + `DaprSessionStore`) nad Dapr Workflows | 2026-10-21 | Bus factor 1, žádná support policy, A2A/AG-UI nepodporuje – nutný vlastní A2A server; obnovení během nástroje at-least-once → idempotency key | [`../frameworks/dapr-agents.md`](../frameworks/dapr-agents.md) |
| Model gateway a FinOps | **agentgateway** (LF, Apache-2.0, nativní `/v1/messages`, USD rozpočty v OSS); LiteLLM záloha | **2026-10-22 (rozhodnuto, Adam)** – po harnessu G1: mock 21/21, live 2/2 | bus factor 1 (51 % commitů), bez CLA/DCO, rozpočty jen per API klíč (klíč per agent/tým jako pracovní model), persistence rozpočtů mezi replikami neověřena | [`../gateway/overview.md`](../gateway/overview.md) |
| Identita, autorizace, governance | Identita uživatele = OAuth z IdP zákazníka přes **Keycloak**; identita agenta = **SPIRE** SVID jako druhý credential (ne `act` v tokenu); **token exchange v agentgateway** (RFC 8693, scope hlídá config gateway, enforcer ne); PDP = **OPA-Envoy** za `extAuthz` + stejná Rego z hooku Agent SDK, decision log; tajemství **OpenBao** | **2026-10-23 (rozhodnuto, Adam)** – po sítu, kole 2 a harnessu I2 | Keycloak upscope je default (gateway = plně důvěryhodný PEP); `act` delegace v Keycloaku preview → agent v tokenu uživatele není; SPIRE neměřen; A2A delegace není standard → vlastní extension | [`../identity/overview.md`](../identity/overview.md) |
| Observabilita a evaluace | **OTEL Collector** (`gen_ai_normalizer`, `redaction`, routing per tenant) → **ClickHouse** (traces, logy, TTL per tenant) + **Prometheus** (metriky); Grafana jen vyměnitelné UI; **Langfuse** jako druhý konzument OTLP pro datasety a anotace; evaluace **Inspect AI** (role, sandbox, approval policy) + **promptfoo** (CI gate, trajektorie nad spany) + **MLflow** (L4/L5 drift, kalibrace judge); vrstvy L0–L5, metriky pro čl. 15 | **2026-10-23 (rozhodnuto, Adam)** – po sítu a harnessech O1 9/9, O2 6/6 | GenAI semconv vše Development; trace CLI → gateway jen s `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`; Dapr aktivity bez kontextu (Dapr Agents obchází, neměřeno); Foundry bez serverových spanů; Langfuse retence/audit/masking za EE klíčem, EE telemetrie nevypnutelná, ClickHouse Inc. vlastní Langfuse; AGPL u Grafana stacku → právník; L2/L5 judge neměřen | [`../observability/overview.md`](../observability/overview.md) |
| Paměť a znalosti | **Vlastní tenký MCP server paměti s PEP** (tenant a role z tokenu, OPA, embeddingy přes agentgateway) nad **PostgreSQL + pgvector** (RLS per tenant, Dapr PostgreSQL v2 state store), graf jako hrany v Postgresu (**Apache AGE** až při hlubších traverzech); záznam = **fakt s původem** (bi-temporalita, `sources[]` povinné, `verification`, `status proposed → approved` přes Dapr HITL); epizodická = destiláty z ClickHouse; procedurální v gitu; **žádný memory framework** (mem0, Letta, Zep, Cognee, LangMem); Claude memory tool jen pro pracovní poznámky per běh | **2026-10-23 (rozhodnuto, Adam)** – po sítu, modelu paměti a harnessu M1 (11/11: RLS + OPA + karanténa vynutí model mimo prompt, M-E3/M-E4 gate 100 %) | pgvector bus factor 1; výkon nad velkými objemy neměřen (Qdrant záloha); destilační agent a schvalovací tok se píší; OTEL memory spany Development; lidské schválení faktů je úzké hrdlo (dávkově); MemLeak: izolace jen v DB/PEP, ne v promptu | [`../memory/overview.md`](../memory/overview.md) |
| Sandboxy a pracovní prostředí | *návrh po sítu kolo 1:* S1 = **Kata Containers** (AKS Pod Sandboxing `kata-vm-isolation`, jinde `kata-deploy`) s **gVisor `systrap`** jako přenositelnou zálohou; uvnitř podu **Anthropic `sandbox-runtime`** (bwrap + seccomp, síť jen přes proxy, decider → OPA); egress jen přes **agentgateway jako CONNECT forward proxy** (SNI allow-list, terminace TLS pro modely a git s `backendAuth`) za Cilium/NetworkPolicy default-deny; SVID per pod, žádný credential v podu; prostředí = **devcontainer.json + `devcontainer build` v CI**, prohlížeč **Playwright + Playwright MCP**, krátké výpočty **wasmtime/Pyodide**; orchestrace Dapr aktivita → Pod/Job s RuntimeClass (agent-sandbox CRD sledovat); evaly **`inspect_k8s_sandbox`** s vlastním chartem | 2026-10-23 (návrh po sítu, kole 2 a **harnessu S1 11/11 PASS lokálně**; microVM část čeká na měření na AKS – čeká na rozhodnutí Adama) | nested virt = gen2 SKU, bez GPU; Kata na AKS = MS fork 4.1.0, guest bez Landlock, seccomp profil podu se neaplikuje, `hostUsers` ne; srt beta (breaking změny každé 2–3 týdny), sdílený kernel, non-root + vlastní seccomp profil nutné, nekryje MCP/hooky; agentgateway 1.6.0 bez loopback ochrany dynamic backendu → CNP na gateway; git token žije v gateway podu; start Kata VM a hustota neměřeny | [`../sandbox/overview.md`](../sandbox/overview.md) |
| Organizační vrstva | *(hypotéza níže)* | – | – | – |

## Pracovní hypotéza organizační vrstvy

**Pozn. Adam:** tohle není rozhodnutí, je to hypotéza, aby technické vrstvy měly proti čemu
formulovat požadavky. Přepíše se, až se vrstva otevře.

Virtuální IT firma = sada **rolí** (agentů) a **procesů** (workflow), kde každý proces má
definované vstupy, výstupy, schvalovací body a vlastníka.

| Role | Co dělá | Co potřebuje od technických vrstev |
|---|---|---|
| Account / zadání | Přijme požadavek, upřesní ho s člověkem, založí zakázku | AG-UI (dialog), paměť zákazníka, identita zadavatele |
| Architekt | Navrhne řešení, rozhodne o stacku, odhadne cenu | Paměť (co už firma umí), gateway (cena modelů), sandbox (prototyp) |
| Vývojář | Implementuje, testuje, otevírá PR | Sandbox (kód, git, CI), MCP (repo, issue tracker), durable execution (dlouhé běhy) |
| Reviewer / QA | Kontroluje kvalitu, spouští evaly | Observabilita a evaluace, oprávnění jen pro čtení + komentáře |
| Provoz / SRE | Nasazuje, hlídá, eskaluje incidenty | MCP (cloud API), identita (produkční oprávnění jen po schválení), observabilita |
| Governance / compliance | Audituje, hlídá rozpočty a AI Act | Identita a audit log, FinOps data, evaluace |
| Člověk | Schvaluje na definovaných bodech, řeší eskalace | AG-UI, durable HITL (dny až týdny) |

Z hypotézy plynou tři požadavky, které se zatím opakují napříč vrstvami:

1. **Každá akce agenta má identitu, rozpočet a stopu.** Identita (kdo), gateway (za kolik),
   observabilita (co a proč). Žádná z těch tří vrstev to nesmí řešit jen pro sebe.
2. **Hranice autonomie jsou v procesu, ne v promptu.** Schvalovací body drží durable vrstva
   (Dapr Workflows), ne instrukce modelu.
3. **Paměť je firemní, ne agentní.** Co se agent naučí o zákazníkovi nebo o kódu, patří firmě
   a řídí se oprávněním, ne instancí agenta.
4. **Agent se představí.** Čl. 50 AI Act platí od 2.8.2026: každý kanál k lidem (chat, e-mail, PR komentář,
   ticket) architektonicky oznamuje „jsem AI, jednám za X“ (viz [`../identity/regulace.md`](../identity/regulace.md), T7).
5. **Klasifikační brána při onboardingu.** Přidělování práce lidem nebo provoz u kritické infrastruktury
   překlopí use case zákazníka do přílohy III; platforma se počítá jako jeden systém (T9).

## Changelog
- 2026-10-23: sandbox – kolo 2 + harness S1 (11/11) potvrdily návrh; čeká na rozhodnutí.
- 2026-10-23: sandbox – návrh po sítu: Kata/gVisor + srt + agentgateway egress + devcontainer + Playwright MCP + wasmtime.
- 2026-10-23: memory – **rozhodnuto (Adam)** podle návrhu; otevřena vrstva sandboxy.
- 2026-10-23: memory – harness M1 (11/11) potvrdil návrh: jedna tabulka + RLS + OPA, žádný framework.
- 2026-10-23: memory – návrh: vlastní MCP server nad Postgres + pgvector, fakt s původem, žádný framework.
- 2026-10-23: observability – **rozhodnuto (Adam)** podle návrhu; otevřena vrstva paměť.
- 2026-10-23: observability – harnessy O1 (9/9) a O2 (6/6) potvrdily Collector + ClickHouse a Inspect AI.
- 2026-10-23: observability – návrh Collector + ClickHouse + Prometheus, Langfuse druhý konzument, Inspect AI + promptfoo + MLflow.
- 2026-10-23: identity – **rozhodnuto (Adam)** podle návrhu z kola 2 a harnessu I2.
- 2026-10-22: identity – po harnessu I2 upřesněno: exchange v gateway změřen, `act` nevzniká → SVID jako druhý credential, OPA-Envoy fail-closed.
- 2026-10-22: identity – návrh SPIRE + Keycloak + OPA + OpenBao, exchange v gateway; do hypotézy přidány požadavky čl. 50 a klasifikační brána.
- 2026-10-22: gateway – **rozhodnuto (Adam): agentgateway**, LiteLLM záloha; po harnessu G1 mock 21/21 a live 2/2.
- 2026-10-22: první verze – přeneseno pět rozhodnutí z `protocols/` a `frameworks/`, prázdné řádky
  pro zbylé vrstvy, pracovní hypotéza organizační vrstvy.

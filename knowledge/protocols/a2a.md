---
tema: Agent2Agent Protocol (A2A)
naposledy_overeno: 2026-10-20
zralost: stable (v1.0.1), v1.1 ve vývoji; adopce v raném produkčním stádiu (Foundry GA)
primarni_zdroje:
  - https://a2a-protocol.org/latest/specification/
  - https://a2a-protocol.org/latest/whats-new-v1/
  - https://a2a-protocol.org/latest/roadmap/
  - https://github.com/a2aproject/A2A/blob/main/CHANGELOG.md
  - https://github.com/a2aproject/A2A/blob/main/GOVERNANCE.md
---

# A2A – Agent2Agent Protocol

## Účel
Otevřený standard pro to, jak se autonomní agenti navzájem objevují, delegují si úkoly
a spolupracují napříč frameworky, dodavateli a organizacemi.

## Aktuální stav
- **v1.0.0** vydáno 2026-03-12 (ne RC, jak stálo dříve); **v1.0.1** 2026-05-26 – jen opravy
  (preferuje `application/a2a+json`, oprava hodnot TaskStatus, transcoding errors). Zdroj: CHANGELOG, ověřeno 2026-10-20.
- **v1.1 ve vývoji** ve větvi `dev-1.1`: `SendLiveMessage` / BiDi streaming (PR #2153 merged 2026-10-19,
  TSC hlasování prošlo 2026-10-20; REST `POST /message:live`, `TaskMessageUpdateEvent` jen pro klienty
  s `A2A-Version: 1.1`), coherent task history (`generation`, `timeline`; `history`/`historyLength`
  deprecated; epic #1991). Deklarováno jako aditivní. Roadmap aktualizována 2026-09-15, bez data vydání.
- Původ: Google (duben 2025), následně předáno Linux Foundation.
- Governance: TSC s **9 křesly** (Google, Microsoft, Cisco, AWS, Salesforce, ServiceNow, SAP, IBM,
  Bloomberg – přidán 2026-10-20). Projekt AAIF od 08/2026; stage („Growth“) z veřejných zdrojů
  k 2026-10-20 neověřen (aaif.io stage neuvádí). Zdroj: GOVERNANCE.md.
- SDK (ověřeno 2026-10-20): Python `a2a-sdk` 1.2.3 (2026-10-19; 1.2.0 přidal multi-replica cluster mode,
  caching headers na kartě, push auth jako `Authorization` header), JS `@a2a-js/sdk` 1.3.0 (2026-09-29),
  Go `a2a-go` v2.6.0 (2026-09-25, **první s podpisem a ověřením Agent Card**), Java 1.4.0.Final (09/2026),
  .NET `A2A` 1.0.0-preview3 (2026-10-14, **stále prerelease**, přidán gRPC), Rust `a2a-rs` (bez stability
  labelu). Kompatibilní vrstvy v1.0 → v0.3 v Python/.NET/Java.
- Nástroje: A2A Inspector, A2A Protocol TCK (conformance testy), **A2A CLI** (`a2a`, Go, blog 2026-10-01;
  brew/winget; `--echo`/`--exec` testovací servery; Agent Skill pro Claude Code/Cursor/Codex).

## Klíčové koncepty
- **Agent Card** – JSON dokument, kterým se agent popisuje (schopnosti, typy úkolů, vstupní formáty, autentizace, endpointy). Ve v1.0 podpora podpisu karty.
- **Task** – jednotka delegované práce se stavem a streamovanými událostmi.
- **Opacity** – agenti nesdílejí vnitřní paměť, nástroje ani logiku.
- Transportní vazby: JSON-RPC, gRPC, REST.
- Extensions: tiery Experimental (`experimental-ext-*`) → Official (`ext-*`, hlasování TSC, kvórum 50 %)
  → případně Core. K 2026-10-20 **žádná official extension**; první sponzorovaný experimental návrh
  CRATB-Auth (#2355). Ukázky v a2a-samples (Traceability, Secure Passport, Timestamp, AGP) bez statusu.

## Novinky v1.0
- Formální opora v RFC 9457 (chyby), RFC 8785 (kanonický JSON), RFC 7515 (JWS).
- Sjednocení typů Part, refaktoring Agent Card, zjednodušené ID a HTTP cesty.
- Multi-tenancy, řízení execution mode, vyjednávání verzí.

## Místo v architektuře
Vrstva agent ↔ agent. Typicky: klientský agent deleguje přes A2A, vzdálený agent používá MCP pro své nástroje.

### Adopce (ověřeno 2026-10-20)
| Platforma | Stav | Zdroj |
|---|---|---|
| Microsoft Foundry Agent Service | A2A tool `a2a` = **v1.0 GA** (`a2a_preview` = v0.3). Incoming A2A v1.0 GA **jen JSON-RPC**, **jen Entra ID** (OBO nebo managed identity), jen text, **bez streamingu**, retence tasků 60 dní. **Bez hlavičky `A2A-Version` defaultuje na v0.3.** Docs upd. 2026-09-14. | learn.microsoft.com/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint |
| Microsoft Agent Framework | Hosting A2A serveru: .NET `Microsoft.Agents.AI.Hosting.A2A`, Python `agent-framework-a2a` (nad oficiálním a2a-sdk), Go nad `a2a-go/v2`. Docs upd. 2026-09-28. | learn.microsoft.com/agent-framework/hosting/self-hosting/a2a/server |
| LangGraph Agent Server | `/a2a/{assistant_id}`: v1.0 JSON-RPC + kompatibilita s v0.3 názvy metod; **bez** SubscribeToTask, push notifications, gRPC/HTTP+JSON; `langgraph-api ≥ 0.4.21`. | docs.langchain.com/langsmith/server-a2a |
| Google ADK Python | 2.12.0 (2026-10-13): tool_call/tool_response v A2A Part, skill-level security v AgentCardBuilder; 2.9.0 vyžaduje HTTPS pro ne-loopback card URL. | github.com/google/adk-python/releases |

## Architektonické důsledky (Pozn. Adam)
- Agent Card registry = klíčová komponenta platformy (discovery, důvěra, podpisy).
- V mixovaném prostředí počítat s v0.3, v1.0 a brzy v1.1 → gateway vždy posílá explicitní `A2A-Version`
  (Foundry bez hlavičky defaultuje na v0.3; `TaskMessageUpdateEvent` chodí jen 1.1 klientům).
- Ověření podpisu karty a revokaci klíčů řešit v registry – spec revokaci nedefinuje, implementace zatím
  jen v Go SDK.
- Tracing řešit mimo protokol: W3C `traceparent` v HTTP hlavičkách na všech bindings + v push notifikacích
  (spec nic, #2103 bez odezvy). Na hranici A2A↔MCP je MCP strana už standardizovaná (SEP-414).
- Delegace identity (OBO / token exchange RFC 8693) je platformní vrstva (Entra/Foundry nebo vlastní IdP);
  spec dává jen řetěz `TASK_STATE_AUTH_REQUIRED`.
- Foundry omezení (jen text, bez streamingu, jen JSON-RPC, jen Entra) → pro cross-org partnery mimo
  Entra tenant vlastní A2A server (MAF hosting) nebo proxy v control plane.
- A2A CLI + Agent Skill = praktický nástroj pro ADLC (conformance v CI, Claude Code jako A2A klient).
- Adopce v produkci je zatím raná → A2A zapouzdřit, nepropisovat přímo do doménové logiky.

## Otevřené otázky
- [~] Autentizace a autorizace mezi agenty intra vs. cross-org. → částečně 2026-10-20: spec §4.5 security
      schemes (API key, HTTP, OAuth2 vč. Device Code, OIDC, mTLS), §7.6 In-Task Authorization
      (`TASK_STATE_AUTH_REQUIRED`, credentials out-of-band), §8.4 signed Agent Card (JWS nad JCS, `kid`+`jku`).
      **Chybí:** OBO/token exchange, revokace podpisových klíčů, cross-org trust model. Sledovat #2355
      CRATB-Auth, #1937 context-binding, #2143 A202 (delegated authority B2B).
- [~] Observabilita a tracing delegovaných úkolů. → 2026-10-20: ve spec nic (žádný OTel/traceparent);
      enterprise-ready topic jen doporučuje OTel + W3C Trace Context v HTTP. Issue #2103 (semantic
      conventions, 2026-08-04) bez reakce maintainerů.
- [ ] Jak A2A kombinovat s MCP Tasks (`io.modelcontextprotocol/tasks`) pro dlouhotrvající práci. → 2026-10-20:
      oficiální stanovisko AAIF nenalezeno; spec Appendix B a topic „A2A and MCP“ zůstávají na úrovni
      „komplementární“. Jen komunitní bridge a2a-to-mcp (#2212) mapuje TaskState → MCP TaskStatus.
- [ ] Kdy vyjde v1.1 (roadmap bez data) a zda bude BiDi deklarováno per binding (otevřená připomínka v #2153).
- [ ] Podpis/ověření Agent Card v Python, JS a .NET SDK – ověřit.

## Changelog
- 2026-09-23: první verze.
- 2026-10-20: opraveno datum v1.0.0 (2026-03-12, ne RC), doplněn v1.0.1 a v1.1 (`dev-1.1`, BiDi), SDK verze,
  TSC 9 členů (Bloomberg), A2A CLI, adopce Foundry/MAF/LangGraph/ADK, částečné odpovědi na otevřené otázky.

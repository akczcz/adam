---
tema: Model Context Protocol (MCP)
naposledy_overeno: 2026-10-20
zralost: stable
primarni_zdroje:
  - https://modelcontextprotocol.io/specification/2026-07-28
  - https://modelcontextprotocol.io/specification/2026-07-28/changelog
  - https://modelcontextprotocol.io/specification/2026-07-28/deprecated
  - https://modelcontextprotocol.io/community/feature-lifecycle
  - https://modelcontextprotocol.io/docs/extensions/overview
  - https://blog.modelcontextprotocol.io/posts/2026-07-28/
  - https://blog.modelcontextprotocol.io/posts/mcp-roadmap/
  - https://modelcontextprotocol.io/seps/2127
  - https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3415
  - https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3398
---

# MCP – Model Context Protocol

## Účel
Otevřený standard pro připojení AI aplikací k externím nástrojům a zdrojům dat.
Server vystavuje schopnosti (tools, resources, prompts), klient v AI aplikaci je objevuje a používá.

## Aktuální stav
- Aktuální specifikace: **2026-07-28** (finální vydání 28. 7. 2026; RC vyšel 21. 5. 2026).
- Předchozí verze: 2025-11-25.
- Žádná novější revize, RC ani draft (ověřeno 2026-10-20 na versioning stránce a blogu).
- **Release kadence (SEP-3398, accepted 2026-10-14, PR ještě open):** spec vychází v **březnu a září**,
  překrývající se 8měsíční cykly, release manageři; přechod do března 2027.
  *Odhad:* příští revize nejdřív ~03/2027; první revize splňující „earliest removal 2027-07-28
  nebo později“ pro deprecated funkce vychází na **09/2027**.
  Zdroj: https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3398
- Governance: Agentic AI Foundation (AAIF); Core Maintainers + Working Groups.
- **Deprecation policy (SEP-2596):** stavy Active / Deprecated / Removed, minimálně **12 měsíců**
  od revize, ve které se funkce stala deprecated. Zrychlené odstranění jen při aktivním
  bezpečnostním riziku, i tak min. 90 dní. Tier 1 SDK musí deprecated API označit nativním
  mechanismem. Zdroj: https://modelcontextprotocol.io/community/feature-lifecycle (ověřeno 2026-09-23).

## Co přinesla 2026-07-28 (největší revize od vzniku)
- **Stateless jádro** – odstraněny sessions a inicializační handshake; vzdálený MCP server je běžná HTTP služba (cacheovatelné, routovatelné).
- Header-based routing (`Mcp-Method`, `Mcp-Name`, `x-mcp-header`; SEP-2243), cacheovatelné výsledky
  (`CacheableResult` s `ttlMs` a `cacheScope`; SEP-2549), **Multi Round-Trip Requests** (MRTR; SEP-2322),
  povinné `server/discover`, povinné pole `resultType` (`complete` / `input_required`),
  OTel trace context v `_meta` (SEP-414).
- **Autorizace** sladěná s OAuth / OpenID Connect; Enterprise-Managed Authorization.
- **Extensions framework** – rozšíření mají vlastní release cyklus a jsou **vždy vypnutá by default**
  (explicitní opt-in, negociace přes pole `extensions` v capabilities / `server/discover`):
  - **Tasks** – asynchronní dlouhotrvající operace (polling, vstup v průběhu, durable handles).
  - **MCP Apps** – interaktivní UI (grafy, formuláře) vykreslené v konverzaci hostitele; vychází z mcp-ui.
  - **Skills over MCP** – strukturované instrukce pro agentní workflow distribuované přes MCP.
  - **OAuth Client Credentials** – `io.modelcontextprotocol/oauth-client-credentials` (repo `ext-auth`).
  - **Events** – `io.modelcontextprotocol/events`, SEP-3415, draft od 2026-10-05, viz Roadmapa.
- **Lifecycle extensions (SEP-3392, draft 2026-09-25):** stupně Experimental → Beta → Stable (nebo
  promotion do jádra). Experimental a Beta smí dělat breaking changes se souhlasem maintainerů extension,
  Stable se mění jen s novou core revizí. Nahrazuje pravidlo SEP-2133 „nový identifikátor při každém
  breaking change“. Zdroj: https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3392

### Odstraněno vs. deprecated
Dvě různé věci s různými termíny – nezaměňovat.

- **Odstraněno (breaking, platí hned):** sessions + hlavička `Mcp-Session-Id` (SEP-2567) – cross-call
  stav se řeší server-minted handles předávanými jako běžné argumenty nástroje; handshake
  `initialize` / `notifications/initialized` (SEP-2575) – verze a capabilities jedou v `_meta`;
  HTTP GET endpoint a `resources/subscribe` / `unsubscribe` → `subscriptions/listen`;
  `ping`, `logging/setLevel`, `notifications/roots/list_changed`; SSE resumability
  (`Last-Event-ID`, event IDs) – přerušený stream znamená ztracený request a klient ho musí poslat
  znovu s novým ID; `notifications/elicitation/complete` + `elicitationId`;
  Tasks vyňaty z jádra do extension `io.modelcontextprotocol/tasks` (SEP-2663).
- **Deprecated, NE odstraněno (SEP-2577):** Roots, Sampling, Logging, HTTP+SSE transport,
  `includeContext: "thisServer"/"allServers"`, OAuth Dynamic Client Registration (RFC 7591)
  ve prospěch Client ID Metadata Documents. Earliest removal = první revize vydaná
  **2027-07-28 nebo později**.
  Zdroj: https://modelcontextprotocol.io/specification/2026-07-28/deprecated (ověřeno 2026-09-23).
- **Pozor na nuanci:** Roots a Sampling formálně nepadly, ale mechanismus, na kterém stály
  (server→klient requesty `roots/list`, `sampling/createMessage`, `elicitation/create`),
  na 2026-era drátě neexistuje – nahradilo ho MRTR. Python SDK vyhazuje `NoBackChannelError`,
  TS SDK je doručuje přes `inputRequired(...)`. Migrace podle spec: Roots → adresáře/soubory jako
  parametry nástroje, resource URI nebo konfigurace serveru; Sampling → volat LLM provider API přímo;
  Logging → `stderr` (stdio) nebo OpenTelemetry.

## Migrace 2025-11-25 → 2026-07-28
Spec-level migrační guide **neexistuje**. Kompatibilita je dvouérová: v2 server odpovídá na legacy
`initialize` vedle `server/discover`, 2026 klient fallbackuje na `initialize` u starších serverů.
Reálné návody jsou na úrovni SDK (Python v1→v2, TS „support-2026-07-28").

**Chybové kódy – nejpravděpodobnější zdroj tichých regresí:**

| Význam | Bylo | Je |
|---|---|---|
| Resource not found | `-32002` | `-32602` |
| HeaderMismatch | `-32001` | `-32020` |
| MissingRequiredClientCapability | `-32003` | `-32021` |
| UnsupportedProtocolVersion | `-32004` | `-32022` |

Nová alokační politika: `-32000`–`-32019` volné pro implementace (existující SDK grandfathered),
`-32020`–`-32099` rezervováno pro spec.

**Auth – nové povinnosti klienta:** validace `iss` per RFC 9207 (SEP-2468); povinný `application_type`
při DCR (SEP-837); credentials klíčované podle issuer identifikátoru a bez reuse napříč
authorization servery (SEP-2352); DCR deprecated ve prospěch CIMD.

**Checklist (Pozn. Adam):** sticky sessions v load balanceru → pryč; retry logika stavěná na SSE
resumability → přepsat; hardcoded chybové kódy → přemapovat; OAuth client cache → klíčovat issuerem;
jakékoli server→klient volání → přepsat na MRTR.

## Stav SDK a hostitelů (ověřeno 2026-10-20)

| SDK / host | Verze | Spec 2026-07-28 | Poznámka |
|---|---|---|---|
| **Python SDK** | v2.3.0 (2026-10-02) | ano, + fallback na 2025-era | `FastMCP` → `MCPServer`, nový `Client`; **Tasks extension stále chybí** (issue #2806, PR #3005 bez commitu od 2026-07-29; maintainer 2026-10-01: „this month“, bez závazku); 2.3.0: nástroj s neplatnou `x-mcp-header` anotací padá při registraci, `MCPServer(subscriptions=False)`, retry na HeaderMismatch, prázdné `_meta`/`params` se už neposílají; v1 linie 1.30.x jen security fixy |
| **TypeScript SDK** | `@modelcontextprotocol/server@2.3.1` (2026-10-05); v1 linie `sdk@1.32.1` | ano, ale **ne by default** | „Nothing in v2 puts a 2026-07-28 byte on the wire by default"; `createMcpHandler` default `legacy: 'stateless'`; v2 rozpadnuto do balíčků (`server`, `node`, `hono`, `express`, `server-legacy`). **2.3.0 breaking: jedna instance serveru = jedno spojení / u stateless jeden request** (sdílená instance → `ALREADY_CONNECTED`; fix CVE-2026-111770). Částečné Tasks: `tasks/get` a `tasks/cancel` i na 2026-07-28 spojení. 2.2.0: `expectedIssuer` u OAuth providerů |
| **C#/.NET SDK** | v2.2.0 (2026-08-13, beze změny k 2026-10-20) | ano, `Stateless` = true default | jediné z trojice má **Tasks i Apps** jako samostatné balíčky |
| **Claude Code** | TS SDK 2.0 (v2 runtime default od v2.1.232, resp. v2.1.274 pro Bedrock/Foundry/Vertex) | ano | `MCP_SDK_GENERATION`, `MCP_PROTOCOL_NEGOTIATION`: bez proměnné Claude Code **sonduje HTTP, stdio i claude.ai connector servery na 2026-07-28** (= `auto`), `legacy` = nesondovat nic. Dřívější zápis „default legacy“ byl buď zjednodušení, nebo se default změnil – nelze z docs určit. Server, který vyjedná 2026-07-28, se jako channel neregistruje; per-server negociace jen požadována (anthropics/claude-code#102736, open). Zdroj: https://code.claude.com/docs/en/env-vars (ověřeno 2026-10-20) |
| Claude API MCP connector | beta `mcp-client-2025-11-20`, nově nadmnožina **`mcp-client-2026-09-15`** (pinning tool listu: `mcp_tool_listing` block, `tools` v `mcp_toolset`; jen Claude API, ne Bedrock/Foundry) | **neověřeno** | docs (platform.claude.com) stále odkazují auth na spec 2025-11-25; stateless ani Tasks neuvedeny (2026-10-20) |
| Microsoft Foundry Agent Service | – | **neověřeno** | docs (upd. 2026-09-04) odkazují Tasks na 2025-11-25; nepřímá indicie, ne fakt |

**Pozn. Adam:** tahle tabulka zastarává nejrychleji z celého souboru – po ~3 měsících re-verifikovat.

### Ověřeno empiricky (2026-09-24)

Tvrzení v tomto souboru byla protažena smoke testem proti **mcp 2.2.0 / mcp-types 2.2.0**
na reálném HTTP drátě – `tools/smoke_mcp_2026_07_28.py`, **15/15 potvrzeno**.
Verze SDK ověřeny proti PyPI a npm registru (sedí na den: Python 2.2.0 = 2026-09-07,
`@modelcontextprotocol/server` 2.1.0 = 2026-09-23, v1 linie 1.30.1).

Potvrzeno na drátě: request bez `initialize` projde; `tools/list` bez session vrátí nástroje
a odpověď nenese `Mcp-Session-Id`; `ping`, `logging/setLevel` i `resources/subscribe` vracejí
`-32601`; HTTP GET vrací 400; neznámý resource vrací **`-32602`** (ne `-32002`);
výsledek nástroje nese `resultType: "complete"`; `NoBackChannelError` v SDK existuje;
modul `mcp.server.tasks` ani identifikátor `io.modelcontextprotocol/tasks` v SDK **nejsou**.

**Jak vypadá 2026-era request v praxi** (zjištěno metodou pokus-omyl, chyby SDK navigují):
1. hlavička `MCP-Protocol-Version: 2026-07-28` – **jinak server routuje do legacy větve**;
2. `params._meta` s `io.modelcontextprotocol/protocolVersion` a `.../clientCapabilities`
   (bez nich `-32602`) – tady jsou data, která dřív nesl handshake;
3. hlavička `Mcp-Method` shodná s `method` v těle (jinak `-32020`);
4. hlavička `Mcp-Name` zrcadlící `name` (u `tools/call`, `prompts/get`) nebo `uri`
   (u `resources/read`), jinak `-32020`.

**Limit testu:** ověřuje chování SDK, ne text specifikace. Tvrzení o spec samotné
(earliest removal 2027-07-28, SEP čísla) stojí dál na primárních zdrojích.

## Roadmapa (blog 2026-08-22)
- **Server Card – SEP-2127 Final, merged 2026-10-06** (Extensions Track; CM vote Accept už 2026-08-13).
  Normativní spec je v repu `ext-server-card` (graduace z `experimental-ext-server-card`), jehož README
  ale stále říká „experimental, for prototyping and feedback only“, schéma v1 „pre-release“, bez tagu.
  Doporučené umístění **`<streamable-http-url>/server-card`** (není to `.well-known` cesta); domain-level
  discovery deleguje na **AI Catalog** `/.well-known/ai-catalog.json` (github.com/Agent-Card/ai-catalog).
  Obsah: identita, remote transport endpointy (URL, headers, variable templates, `supportedProtocolVersions`),
  `_meta`. **Bez primitiv, capabilities i extensions** – „a static document cannot reliably represent
  this surface“. **Explicitně oddělené schéma od `server.json`** (to vlastní Registry a pokrývá i lokální
  balíčky; karta = jen remote). Při nesouladu klient preferuje živé `server/discover`.
  Zdroje: https://modelcontextprotocol.io/seps/2127, https://github.com/modelcontextprotocol/ext-server-card
  (ověřeno 2026-10-20).
- **Server-initiated events – SEP-3415 Events Extension (draft, otevřen 2026-10-05, Anthropic / Triggers &
  Events WG):** `io.modelcontextprotocol/events`; server vystaví `events/list` (per typ `inputSchema`,
  `payloadSchema`, delivery modes). Tři režimy, žádný povinný: **poll** (`events/poll`), **push**
  (long-lived `events/stream`), **webhook** (`events/subscribe`, podpis dle Standard Webhooks, TTL refresh).
  Opaque cursory pro resume, volitelný replay, `truncated: true`; provizorní chybové kódy `-32023`–`-32027`.
  Otevřený konflikt se SEP-3371 (extension nesmí filtrovat core stream `subscriptions/listen`), 8 open
  questions, reference impl. chybí. Governance PR #3440 (open) zakládá **Tasks and Events WG**.
  Zdroj: https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3415 (ověřeno 2026-10-20).
- Dozrání Tasks extension (SEP-2663) do jádra specifikace.

## Místo v architektuře
Vrstva agent → nástroje/data. Ne pro delegaci úkolů autonomním agentům (to je A2A).

## Architektonické důsledky (Pozn. Adam)
- Stateless = horizontální škálování MCP serverů za load balancerem bez sticky sessions.
- Migrace: viz sekce „Migrace 2025-11-25 → 2026-07-28". Tlak je na **transportní a auth vrstvu**,
  ne na feature set – odstraněné věci bolí hned, deprecated mají okno minimálně do 2027-07-28.
- **Ztráta back-channelu je architektonicky větší věc než deprecation Sampling.** Agent loop
  (LangGraph node) musí umět retry původního requestu s doplněným `inputResponses`, ne jen
  „zavolej tool, dostaneš výsledek". Stav mezi pokusy si drží server ve vlastním `requestState`.
- **Tasks chybí v Python SDK** → tři cesty: vlastní implementace `io.modelcontextprotocol/tasks`
  nad SDK / server-minted handle jako běžný argument nástroje (vzor, který spec sama doporučuje pro
  cross-call stav) / ten konkrétní server postavit v C#. Reálný trade-off při volbě jazyka.
- **Era-routing je opt-in napříč celým ekosystémem – to je nejčastější past.** Ověřeno, že
  **Python SDK** routuje podle hlavičky `MCP-Protocol-Version`: bez ní server spadne do legacy
  stateful větve a odpoví `Missing session ID`, i když 2026-07-28 plně umí. **TS SDK** to říká
  otevřeně („nothing puts a 2026-07-28 byte on the wire by default"), **Claude Code** má
  `MCP_PROTOCOL_NEGOTIATION` default `legacy`. Důsledek: „server je na 2026-07-28" a „komunikace
  běží na 2026-07-28" jsou dvě různá tvrzení. Interoperabilitu testovat explicitně v obou érách
  a v provozu logovat skutečně vyjednanou revizi, ne tu nakonfigurovanou.
- **Interní katalog MCP serverů stavět na `server.json`** (schéma 2025-12-11, Registry API v0.1,
  subregistry pattern s vlastním `_meta` namespace jako kanonický model), Server Card řešit jako
  jeden z ingest adaptérů za rozhraním typu `fetch(endpoint) → ServerDescriptor`. Cesta k metadatům
  není ustálená (tři konkurenční tvary URL), adaptér je jediná bezpečná abstrakce. Registry je stále
  preview bez garancí uptime → scrape-and-persist (cca hodinově), ne live dependency; synchronizovat
  `status` (`deprecated` / `deleted`).
- MCP Apps je relevantní pro UI v cizích hostitelích (Claude, ChatGPT), ne nutně pro vlastní frontend.
- Extensions jsou opt-in a vypnuté by default → platforma potřebuje explicitní politiku, která
  rozšíření zapínáme a kde to evidujeme.
- **Bezpečnostní vlna 09–10/2026 (13 advisories):** Python fixy v 2.2.0 / 1.30.0 (mj. GHSA-84m7-p3x7-pcfv
  CVE-2026-59951 session OOM, GHSA-w4fh-qvv9-3v23 bearer bez audience check, GHSA-rwrf-2pqf-9j8j SSRF přes
  `$ref` v `outputSchema`), TS fixy v 2.1.0–2.3.0 (GHSA-jm63-cq47-j5jp CVE-2026-111770 cross-client leak,
  GHSA-46jr-4wx8-v453 CVE-2026-111768 paměť při validaci, GHSA-f897-62hf-6gxq bez limitu body/batch).
  **Několik oprav je opt-in** (`maxToolInputElements`, `expectedResource`/`validate_token_resource`,
  `expectedIssuer`) → upgrade bez konfigurace nestačí; audience check tokenu zapnout všude, kde jeden
  authorization server vydává tokeny víc službám. Zdroje: security/advisories v python-sdk a typescript-sdk
  (ověřeno 2026-10-20).
- **Instance serveru per request/spojení** – TS 2.3.0 to vynucuje (`ALREADY_CONNECTED`), v Pythonu
  doporučit jako default; sdílený singleton = riziko cross-client leaku (kolize JSON-RPC ID).
- **Server Card adaptér má jasný tvar:** `GET <mcp-url>/server-card` (+ volitelně AI Catalog), verzovat
  podle `$schema` URL (schéma stále pre-release). Karta nikdy nenahradí `tools/list` (bez primitiv by design).
- **Events extension:** nestavět na ní (draft), ale vlastní event ingest držet kompatibilní s modelem
  cursor + replay + `truncated`. Claude Code channels zůstávají na legacy éře, dokud nedozraje.

## Otevřené otázky
- [x] Přesný seznam deprecated funkcí a migrační cesta. → vyřešeno 2026-09-23,
      viz „Odstraněno vs. deprecated" a „Migrace 2025-11-25 → 2026-07-28".
- [x] Stav podpory 2026-07-28 v SDK pro náš stack. → vyřešeno 2026-09-23, viz „Stav SDK a hostitelů".
- [x] Jak Server Card ovlivní registr/katalog MCP serverů v platformě. → vyřešeno 2026-10-20: SEP-2127
      Final (merged 2026-10-06). **Rozhodnutí (Adam, 2026-09-23)** – `server.json` kanonický model, Server
      Card jako ingest adaptér – **potvrzeno textem SEP** (dvě oddělená schémata, karta jen remote).
      Zbývá sledovat graduaci repa `ext-server-card` z „experimental“ a první tagované schéma v1.
- [ ] Podporuje Microsoft Foundry Agent Service revizi 2026-07-28 jako klient? Nenalezen primární
      zdroj; docs (upd. 2026-09-04) stále odkazují 2025-11-25.
      **Nástroj připraven:** `tools/probe_remote_mcp.py <URL> --token <TOKEN>` (vyžaduje credentials).
- [ ] Podporuje Claude API MCP connector 2026-07-28? Beta header je `mcp-client-2025-11-20`; 2026-10-20:
      nový header `mcp-client-2026-09-15`, 2026-07-28 stále neuvedeno.
      **Nástroj připraven:** `tools/probe_remote_mcp.py` (vyžaduje credentials).
- [ ] Kdy přijde Tasks extension do Python SDK (issue #2806) a jaký je interim pattern? 2026-10-20: stále
      chybí (2.3.0); maintainer cílí říjen 2026 bez závazku; ověřit po 2026-10-31.
- [ ] Server-initiated events (webhooky / channels) – 2026-10-20: SEP-3415 draft existuje; sledovat merge,
      vyřešení konfliktu se SEP-3371 a reference impl. (conformance#521, #541).
      Relevantní, protože Claude Code channels dnes vyžadují revizi *před* 2026-07-28.
- [ ] Kdy Registry opustí preview (v0.1, bez garancí uptime a durability)? 2026-10-20: beze změny
      (poslední release v1.8.1 z 2026-08-06, README stále preview).
- [ ] Kdy přesně Claude Code přepnul default negociace na probe (nebo byl náš záznam „legacy“ chybou)?
      Changelog Claude Code neprověřen.

## Changelog
- 2026-09-23: první verze.
- 2026-09-23: ověřeny 3 otevřené otázky (protocol-scout) – upřesněno removed vs. deprecated
  (registr deprecated funkcí, earliest removal 2027-07-28), doplněna sekce Migrace (chybové kódy,
  auth), sekce Stav SDK a hostitelů, upřesněn stav Server Card (SEP-2127 = draft) a rozhodnutí
  stavět interní katalog na `server.json`.
- 2026-09-24: znalost ověřena empiricky smoke testem proti mcp 2.2.0 (15/15 potvrzeno),
  verze SDK ověřeny proti PyPI/npm. Nový nález: era-routing podle hlavičky
  `MCP-Protocol-Version` je opt-in i v Python SDK, ne jen v TS SDK a Claude Code.
  Přidány `tools/smoke_mcp_2026_07_28.py` a `tools/probe_remote_mcp.py`.
- 2026-10-20: SEP-2127 Server Card Final (merged 2026-10-06), rozhodnutí o katalogu potvrzeno; SEP-3415
  Events draft; SEP-3392 lifecycle extensions; SEP-3398 release kadence březen/září; SDK Python 2.3.0,
  TS 2.3.1 (breaking one-server-per-request, částečné Tasks); vlna 13 advisories, část fixů opt-in;
  Claude Code default = probe 2026-07-28; Claude API nový header `mcp-client-2026-09-15`.

---
tema: kagent – Kubernetes-nativní control plane pro agenty
naposledy_overeno: 2026-09-29
zralost: preview (v0.10.x) / experimental (v1.0.0-alpha)
primarni_zdroje:
  - https://github.com/kagent-dev/kagent/blob/main/LICENSE
  - https://raw.githubusercontent.com/kagent-dev/kagent/main/CONTRIBUTING.md
  - https://github.com/kagent-dev/kagent/tree/main/docs/architecture
  - https://www.cncf.io/projects/kagent/
  - https://github.com/cncf/toc/issues/1978
  - https://github.com/cncf/sandbox/issues/360
  - https://raw.githubusercontent.com/kagent-dev/community/main/MAINTAINERS.md
  - https://github.com/kagent-dev/kagent/issues/2932
  - https://pypi.org/pypi/kagent-adk/json
  - https://github.com/kagent-dev/kagent/blob/main/go/core/pkg/app/app.go
  - https://github.com/kagent-dev/kagent/blob/main/go/core/internal/substrate/client.go
  - https://github.com/kagent-dev/kagent/blob/main/go/core/internal/translator/credentials.go
  - https://raw.githubusercontent.com/kagent-dev/kagent/v0.10.2/python/packages/kagent-adk/pyproject.toml
  - https://raw.githubusercontent.com/kagent-dev/kagent/v0.10.2/python/packages/kagent-adk/src/kagent/adk/_a2a.py
  - https://raw.githubusercontent.com/google/adk-python/main/src/google/adk/apps/_configs.py
  - https://raw.githubusercontent.com/google/adk-python/main/CONTRIBUTING.md
  - https://pypi.org/pypi/google-adk/2.10.0/json
---

# kagent

## Účel
Deklarativní správa agentů na Kubernetu. Agent je CRD objekt; controller řeší lifecycle,
kompilaci do neměnné revize, autorizaci na hranici a protokolové rozhraní ven.

## Aktuální stav
- Open-sourcoval Solo.io (3/2025), **CNCF Sandbox od 2025-05-22**.
- **Žádost o Incubating podána 2025-12-02, k 2026-09-28 stále otevřená** bez TOC sponzora.
- Dvě paralelní release linie: **v0.10.x** (použitelná) a **v1.0.0-alpha** (rewrite).
- Licence **Apache-2.0 napříč celým nasazovaným stackem** – controller, kmcp, substrate,
  agentgateway. Žádný BUSL, ELv2 ani SSPL.

## Klíčové koncepty
- **Agent / AgentTemplate / Harness CRD** – nic neběží mimo deklaraci.
- **Harness** – vybírá runtime agenta: kagent/ADK, Claude, Codex nebo **BYO** (vlastní image
  implementující privátní A2A gRPC). Agentní smyčka je tím vyměnitelná.
- **A2A gateway** – vlastní komponenta kagentu, in-process. Autorizace, routing, streaming.
- **kmcp** – lifecycle MCP serverů přes CRD `MCPServer`.
- **agentsts** – klient RFC 8693 OAuth 2.0 Token Exchange, v OSS.
- **Substrate** – sandbox/actor runtime (gVisor / microVM), fork cizího pre-1.0 projektu.

## Místo v architektuře
**Není to agentní framework, je to control plane.** Neřeší agentní smyčku – řeší lifecycle,
kompilaci, identitu a protokolovou hranici. Kombinuje se proto s tenkou smyčkou,
ne s jiným orchestrátorem.

## Zralost a rizika

| Osa | Stav |
|---|---|
| Licence | ✅ Apache-2.0 celý stack |
| Governance | ✅ **DCO, ne CLA** – Solo.io nemůže jednostranně relicencovat cizí příspěvky; trademark darovaný CNCF, projekt se řídí CNCF IP Policy |
| Stupeň zralosti | ⚠️ CNCF **Sandbox**; žádost o Incubating leží ~10 měsíců bez posunu |
| Bus factor | ⚠️ **7 z 8 maintainerů ze Solo.io** (8. je z Amdocs); 88 unikátních přispěvatelů |
| Protokoly | ✅ A2A i MCP přes oficiální SDK, ale **přes ADK jako mezičlánek** – kagent subclassuje `A2aAgentExecutor` (ten je `@a2a_experimental`) a `McpToolset` |
| Model gateway | ✅ **šev otevřený** – `BaseURL` / `Endpoint` / `Host` přepisují defaulty; self-hosted vLLM funguje |
| AG-UI | ❌ **nepodporuje a nebude** – issue #589 uzavřeno jako *not planned* |
| MCP registry | ❌ **nemá** – kmcp je kagentí CRD, ne standardní `modelcontextprotocol/registry` |
| Trvalost stavu | ⚠️ **kagentí** Postgres (`KAgentSessionService` → vlastní Go API), **ne** ADK `[db]`. HITL pause/resume funguje **už ve v0.10.x**, ale mechanika je ADK `ResumabilityConfig` – `@experimental` a **at-least-once** |
| Artefakty | ❌ `InMemoryArtifactService()` **bez podmínky v obou liniích** – nepřežijí restart |
| Governance závislostí | ⚠️ agentní smyčka je **Google ADK**: Apache-2.0, ale **CLA, žádná nadace**, breaking changes v minorech; pin `<3` nechrání |
| Air-gap | ✅ v0.10.x (Substrate opt-in); ❌ **v1.0 – Substrate povinný a stahuje `runsc` z veřejného `gs://` bucketu** ([#2932](https://github.com/kagent-dev/kagent/issues/2932)) |
| Phone-home | ✅ žádné; čistá OTLP telemetrie, výchozí vypnutá, žádný licenční klíč |
| Licence v balíčcích | ❌ PyPI balíčky mají `license: null` – pro SBOM „unknown" |

### Rewrite v1.0-alpha
Durable model ve v1.0 je ambiciózní (append-only event log, named checkpointy, forky,
durable HITL s `input-required`), ale:

- *„Schema changes are unreleased; no upgrade path exists"* – **žádná migrační cesta**.
- **Chybí `multi-replica gateway coordination`** – A2A gateway není HA.
- *„Input-required and auth-required tasks … are not checkpointable or forkable"* –
  **přesně ve stavu čekání na člověka nelze checkpointovat**.
- V `design/` **není EP dokument** pro v1.0, Substrate ani migraci z AutoGenu.

### Substrate je ve v1.0 fakticky povinný
*Ověřeno čtením kódu 2026-09-29 (`main`, v1.0-alpha).*

Helm má `controller.substrate.enabled: false` a configmap je podmíněný – **ale kód to
přebíjí**. Tři doklady:

| Místo | Zjištění |
|---|---|
| `go/core/pkg/env/substrate.go` | `KAGENT_SUBSTRATE_ATE_API_ENDPOINT` má **neprázdný default** `dns:///api.ate-system.svc:443` |
| `go/core/pkg/app/app.go` | `substrate.Dial(...)` je volaný **bez jakékoliv podmínky**; jediný výskyt v repu |
| `internal/substrate/client.go` | `Dial` volá `conn.Connect()` a pak **blokuje** ve `waitConnReady` (výchozí timeout 10 s); chyba se propaguje a **shodí start controlleru** |

Když configmap proměnnou nenastaví, uplatní se ten default v Go. Controller se pokusí
spojit s `api.ate-system.svc:443`, po deseti sekundách selže a nenastartuje.

Potvrzuje to i credential injection: bindingy emitují URI ve tvaru `ate-secret://k8s.io/...`.
**Substrate není volitelný doplněk, je vpletený do celé v1.0 cesty.**

#### v0.10.x to má přesně opačně

| | v0.10.2 | main (v1.0-alpha) |
|---|---|---|
| Default endpointu | **`""`** (prázdný) | `dns:///api.ate-system.svc:443` |
| Volání `Dial` | uvnitř `if cfg.Substrate.AteAPIEndpoint != ""` | **bez podmínky** |
| Nápověda k přepínači | *„Enables substrate AgentHarness runtime **when set**"* | – |

**v0.10.x dělá Substrate opt-in, v1.0 opt-out, který nejde vypnout.** Doporučení stavět
na v0.10.x tím dostává tvrdý technický důvod, ne jen „je zralejší".

### Model gateway: obava vyvrácená
*Ověřeno čtením kódu 2026-09-29.*

`modelCredentialTarget` v `internal/translator/credentials.go` **žádný pevný allowlist
hostnames nemá** – dává jen defaulty per provider, a ty klíčové jdou přepsat:

| Provider | Přepis endpointu |
|---|---|
| OpenAI | ✅ `spec.OpenAI.BaseURL` |
| Anthropic | ✅ `spec.Anthropic.BaseURL` |
| Azure OpenAI | ✅ celý z `spec.AzureOpenAI.Endpoint` |
| Ollama | ✅ `spec.Ollama.Host`; self-hosted **nedostane binding vůbec** – komentář v kódu: *„no request leaves for api.ollama.com"* |
| Gemini, Bedrock | pevné, resp. šablona podle regionu |

Egress binding se odvozuje z nakonfigurovaného endpointu: `bind()` vezme URL, zvaliduje
schéma a vyrobí `egress.Credential{Hostname: u.Hostname()}`. **Self-hosted vLLM nebo
LiteLLM proxy tedy funguje.**

„Exact DNS hostname matching" z dokumentace je **bezpečnostní kontrola**, ne allowlist –
brání tomu, aby jeden cíl kombinoval caller-token passthrough s gateway credentials.

### AutoGen – riziko uzavřené
kagent AutoGen **opustil už ve v0.5.0**, před sloučením do Microsoft Agent Frameworku.
Dnes stojí na Google ADK, respektive na abstrakci Harness. Fork `kagent-dev/autogen`
existuje, ale není závislostí žádného publikovaného balíčku.

## Google ADK pod kapotou
*Ověřeno 2026-09-29.*

kagent nepoužívá ADK jako knihovnu vedle sebe – **je to jeho agentní smyčka**.
Piny se ale mezi liniemi liší, což je důležitější, než vypadá:

| Linie | Pin |
|---|---|
| v0.10.2 | `google-adk>=1.38.0,<2` – **bez extras** |
| main (v1.0-alpha) | `google-adk[a2a,db]>=2.9.2,<3` |

**ADK 1.x nemá release od 2026-08-27** (poslední 1.39.1) a EOL publikované není.
Doporučená linie v0.10.x tedy jede na větvi, u které nevíme, jestli dostane
bezpečnostní opravy.

### Co drží kdo

| Vrstva | Drží |
|---|---|
| Agentní smyčka, Runner, flows | **ADK** |
| A2A server executor | **ADK** (`@a2a_experimental`), kagent subclassuje |
| MCP klient | **ADK** (`McpToolset`), kagent subclassuje |
| A2A gateway, authz, routing | **kagent** (Go) |
| A2A TaskStore, session store (v0.10) | **kagent** → Postgres přes vlastní API |
| Model gateway | **kagent** – vlastní `BaseLlm` adaptéry; **ADK model vrstva se nepoužívá** |
| MCP server lifecycle | **kagent** (kmcp) |
| HITL pause/resume | **ADK** (`request_confirmation` + `ResumabilityConfig`) |
| Sandbox | **kagent** (Substrate); ADK `code_executors/` se nepoužívá |
| **Artefakty** | **nikdo** – vždy in-memory |

### Co to zhoršuje

1. **HITL resume je `@experimental` a at-least-once.** Docstring ADK: *„we only guarantee
   an at-least-once behavior once resumed"*. Nástroj za schvalovacím bodem se při obnovení
   **může spustit podruhé** → idempotency key je na naší straně. Maximální horizont
   čekání není dokumentovaný.
2. **Artefakty se při restartu ztrácejí** – `InMemoryArtifactService()` nepodmíněně.
3. **A2A executor ADK je `@a2a_experimental`.**
4. **v0.10.x jede na ADK 1.x** bez release a bez EOL.
5. **Governance runtime závislosti** – Google CLA, žádná nadace, pod jinak DCO+CNCF projektem.
6. **`<3` není ochrana** – ADK vydává breaking changes v minorech (doloženo na v2.9.0).

### Co se nezhoršuje

Licence (Apache-2.0), **model gateway** (kagentí a otevřený – ADK model vrstva je v obrazu
mrtvý kód), phone-home (ADK telemetrie má exportéry i Cloud tracing výchozí vypnuté),
air-gap (ADK nic nevynucuje). **Cena odchodu se nemění** – ADK sedí uvnitř Harnessu,
a BYO harness s vlastní A2A gRPC implementací ADK vůbec nepotřebuje.

## Architektonické důsledky (Pozn. Adam)
- **Protokolová sémantika je standardní, správa je vlastní.** Agenti mluví A2A a lze je vzít
  jinam; manifesty, CRD a nasazovací mechanika se při odchodu zahazují.
- Argument „vytáhnout durable vrstvu ven" u kagentu **platí, ale kvůli zralosti, ne licenci**.
  Externí Temporal nebo Dapr Workflow jako BYO harness je obranná volba.
- **Doporučení: architektonické rozhodnutí opřít o linii v0.10.x**, v1.0-alpha brát jako
  neexistující, dokud nebude migrační cesta a HA gateway.
- Solo.io prodává jako enterprise funkce (HITL, agent identity, tracing) věci, které jsou
  v OSS repu. Dnes to není past, ale je to indikátor, kam může drift jít.

## Otevřené otázky
- [x] ~~Je Substrate v linii v1.0 povinný?~~ – **uzavřeno 2026-09-29: ano, fakticky povinný.**
      Viz sekce výše. A2 i A3 pro v1.0 tím padají prokazatelně.
- [x] ~~Váže `credential-injection` modely na pevný výčet DNS hostnames?~~ –
      **uzavřeno 2026-09-29: ne, obava vyvrácena.** Šev je otevřený.
- [ ] Kdo je upstream vlastník `agent-substrate/substrate` a jaká je jeho governance.
- [ ] Podíl commitů mimo Solo.io – bus factor na úrovni maintainerů je jasný, na úrovni
      commitů nekvantifikovaný.
- [ ] Release a support politika; dostane v0.10.x bezpečnostní opravy po GA v1.0?
- [ ] **Dostane ADK 1.x bezpečnostní opravy?** Poslední release 1.39.1 (2026-08-27),
      EOL nepublikované – přímé riziko pro kagent v0.10.x.
- [ ] Otestovat, co udělá resume neidempotentního nástroje za schvalovacím bodem
      (ADK garantuje jen at-least-once).
- [ ] Kolik práce je BYO harness bez ADK?

## Changelog
- 2026-09-28: první verze; hloubková prověrka.
- 2026-09-29: prověřen Google ADK jako smyčka pod kagentem. Korekce: kagentí Postgres
  nestojí na ADK `[db]`; HITL resume existuje už ve v0.10.x, ale je ADK `@experimental`
  s at-least-once; A2A i MCP jdou přes ADK jako mezičlánek; artefakty jsou vždy in-memory.
- 2026-09-29: ověřeno čtením kódu – Substrate je ve v1.0 fakticky povinný (A2 i A3 padají),
  ve v0.10.x je opt-in. Obava o pevný allowlist hostnames v credential-injection vyvrácena.

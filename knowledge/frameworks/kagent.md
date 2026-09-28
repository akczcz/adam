---
tema: kagent – Kubernetes-nativní control plane pro agenty
naposledy_overeno: 2026-09-28
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
| Protokoly | ✅ **A2A v1.0 i MCP přes oficiální SDK**, ne vlastní implementace |
| AG-UI | ❌ **nepodporuje a nebude** – issue #589 uzavřeno jako *not planned* |
| MCP registry | ❌ **nemá** – kmcp je kagentí CRD, ne standardní `modelcontextprotocol/registry` |
| Trvalost stavu | ⚠️ Postgres výchozí store od v0.10; checkpointy a durable HITL až ve v1.0-alpha |
| Air-gap | ⚠️ ✅ bez Substrate; ❌ **se Substrate** – stahuje `runsc` z veřejného `gs://` bucketu ([#2932](https://github.com/kagent-dev/kagent/issues/2932)) |
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

### AutoGen – riziko uzavřené
kagent AutoGen **opustil už ve v0.5.0**, před sloučením do Microsoft Agent Frameworku.
Dnes stojí na Google ADK, respektive na abstrakci Harness. Fork `kagent-dev/autogen`
existuje, ale není závislostí žádného publikovaného balíčku.

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
- [ ] **Je Substrate v linii v1.0 povinný, nebo volitelný?** Dokumentace a Helm defaulty si
      odporují. Visí na tom vanilla Kubernetes i air-gap. Nutno číst kód controlleru.
- [ ] **Váže `credential-injection` ve v1.0 modely na pevný výčet DNS hostnames?**
      Rozbilo by to model gateway šev. Ověřit v kódu, ne v dokumentaci.
- [ ] Kdo je upstream vlastník `agent-substrate/substrate` a jaká je jeho governance.
- [ ] Podíl commitů mimo Solo.io – bus factor na úrovni maintainerů je jasný, na úrovni
      commitů nekvantifikovaný.
- [ ] Release a support politika; dostane v0.10.x bezpečnostní opravy po GA v1.0?

## Changelog
- 2026-09-28: první verze; hloubková prověrka.

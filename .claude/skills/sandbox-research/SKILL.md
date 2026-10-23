---
name: sandbox-research
description: Postup pro průzkum a prověrku vrstvy sandboxů a pracovního prostředí multiagentní platformy (gVisor, Kata Containers, Firecracker, Sysbox, Kubernetes agent-sandbox, Anthropic sandbox-runtime a Claude Code sandboxing, nsjail, bubblewrap, E2B, Daytona, Modal, microsandbox, OpenHands runtime, SWE-ReX, Pyodide/Wasm, Deno, Jupyter, Playwright, Steel, browser-use, devcontainer, DevPod, Nix, Coder, Azure Container Apps dynamic sessions) a pro aktualizaci knowledge/sandbox/. Použij vždy, když Adam řeší, kde agent spouští kód, testy nebo prohlížeč, izolaci neověřeného kódu, egress a tajemství v sandboxu, devcontainery a předpřipravená prostředí rolí, snapshoty a paralelní běhy, cenu sandboxů na Azure, nebo schvalování nevratných akcí – i když slovo "sandbox" výslovně nezazní.
---

# Průzkum sandboxů a pracovního prostředí

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/sandbox/overview.md` a `kriteria.md`; u dotčených kandidátů jejich soubor.
- Přečti rozhodnutí v `knowledge/platforma/cilova-architektura.md`: identita agenta je **SPIRE SVID**, PDP **OPA-Envoy**,
  modely a egress přes **agentgateway**, tajemství v **OpenBao**, trace do **ClickHouse**, evaly v **Inspect AI**
  (vlastní sandbox providery), stav běhu v **Dapr**. Sandbox se do těchto švů musí vejít – ne vedle nich.
- Přečti `knowledge/identity/overview.md` (tok identity) a `knowledge/observability/evaluace.md` (vrstvy L0–L5, approval).

## 2. Rozliš druhy prostředí a otázky S1–S4
Vývojové prostředí · code interpreter · prohlížeč · eval sandbox; S1 izolace · S2 síť a tajemství · S3 práce agenta ·
S4 observabilita a životní cyklus. Projekt, který „řeší sandboxy“, obvykle řeší jen S1 (izolaci) nebo jen S3 (DX);
S2 a S4 si platforma skládá sama.

## 3. Licence a governance jako u frameworků
Postup `framework-research` sekce 2, vzorce v `knowledge/frameworks/licencni-vzorce.md`. Pro tuhle vrstvu navíc:
- **DX nástroje bývají AGPL** (Daytona, Coder, Gitpod/Ona – ověř doslovně v LICENSE, ne v README) a **sandbox-as-a-service**
  má Apache SDK + hostovaný runtime (E2B, Modal, Browserbase) – ověř, co jde self-host bez klíče a jaká je licence infra.
- Izolační runtimy jsou obvykle Apache-2.0 pod nadací (gVisor Google, Kata OpenInfra, Firecracker AWS) – past je
  v **požadavcích na infrastrukturu**: nested virtualizace, bare-metal, které Azure SKU, GPU passthrough.
- Anthropic `sandbox-runtime`: ověř licenci, stav (experimental?) a co dělá na Linuxu (bubblewrap) vs. macOS (seatbelt).

## 4. Standardy a nativní schopnosti z primárních zdrojů
- Anthropic: Claude Code `sandboxing` docs, `sandbox-runtime` repo, Agent SDK (co umí sandbox), Managed Agents (hostovaný – jen vzor), MCP servery v sandboxu.
- Kubernetes: `RuntimeClass`, `kubernetes-sigs/agent-sandbox` (CRD, stav), Pod Security Standards, NetworkPolicy; SPIFFE workload attestation v K8s.
- Devcontainer spec (containers.dev), features, prebuildy; Nix jako alternativa.
- Inspect AI sandbox providers (docker, k8s `inspect_k8s_sandbox`, další) – produkční runtime = eval runtime.
- OTEL: co se z příkazů a souborů dá emitovat (Claude Code telemetrie `CLAUDE_CODE_ENABLE_TELEMETRY`, hooky).
- AI Act čl. 12 (logování), čl. 14 (lidský dohled) – schvalování nevratných akcí.

## 5. Posuzuj na útočném modelu autonomní firmy, ne na DX
- Agent = neověřený kód s právy sandboxu; prompt injection ze zákaznického repa nebo webu je výchozí stav.
- Default-deny egress; žádný statický credential v sandboxu; tokeny krátkodobé a vydané gateway/SPIRE.
- Nevratné akce (push, deploy, platba, smazání) jen přes approval – stejný mechanismus jako v evalech.
- Sandbox je zahoditelný; stav do gitu, artefaktů, paměti a trace.

## 6. Analyzuj architektonicky
- Kde sandbox žije (K8s zákazníka), kdo ho zakládá (Dapr aktivita / CRD), jak dostane identitu (SVID) a jak odevzdá výsledek.
- Co je zadarmo (sandbox-runtime, devcontainer, Inspect provider) a co se musí postavit (egress proxy, lifecycle, kvóty, evidence).
- Cena odchodu: devcontainer a obrazy přenositelné; snapshoty a CRD specifické.

## 7. Výstup
- Česky, závěr první, fakta se zdrojem a datem, doporučení jako doporučení.
- Návrh úprav `knowledge/sandbox/` jako diff; rozhodnutí do `knowledge/platforma/cilova-architektura.md`.
- Soubory měň až po Adamově souhlasu.

## 8. Čemu se vyhni
- Nevybírej podle DX nebo počtu jazyků – vybírej podle izolace, egressu a provozu na K8s zákazníka.
- Nezaměňuj „kontejner“ za sandbox pro neověřený kód.
- Netvrď požadavky na nested virtualizaci na Azure ani licenci DX nástrojů z paměti – ověř.

---
tema: Hodnoticí kritéria pro vrstvu sandboxů a pracovního prostředí agentů
naposledy_overeno: 2026-10-23
zralost: n/a (metodika)
primarni_zdroje:
  - https://code.claude.com/docs/en/sandboxing
  - https://github.com/anthropic-experimental/sandbox-runtime
  - https://github.com/kubernetes-sigs/agent-sandbox
  - https://inspect.aisi.org.uk/sandboxing.html
---

# Kritéria pro sandboxy a pracovní prostředí

Rubrika pro vrstvu **sandboxy a pracovní prostředí** platformy (viz [`../platforma/overview.md`](../platforma/overview.md)).
Sandbox je místo, kde agent **vykonává** – spouští kód, testy, buildy, prohlížeč, CLI nástroje – a kde se tedy
děje většina nevratných akcí. Vrstva závisí na identitě (co smí sandbox a za koho – SPIRE SVID, OPA), observabilitě
(co se z něj loguje do ClickHouse), gateway (jediná cesta k modelům a egress) a paměti (sandbox je zdroj
epizodických dat, ne paměť sama). Zásada: **sandbox je jednorázový a bez tajemství** – přežít má výsledek
(commit, artefakt, trace), ne prostředí.

## Co se izoluje a kde to v rozhodnutých vrstvách už je

| Druh pracovního prostředí | Co v něm agent dělá | Kde už to je / kde chybí |
|---|---|---|
| **Vývojové prostředí** | checkout repa, build, testy, lint, PR | chybí – jádro vrstvy; vzor Claude Code sandboxing + devcontainer |
| **Code interpreter** | krátké skripty, analýza dat, výpočty | chybí – lehký sandbox (proces/Wasm) místo plného VM |
| **Prohlížeč** | web, SaaS UI bez API, testování frontendu | chybí – Playwright v sandboxu, ne na hostu |
| **Eval sandbox** | izolované běhy evalů rolí (L0–L5) | **Inspect AI sandbox** (rozhodnuto) – stejný mechanismus jako produkční sandbox, jinak evaly měří něco jiného |
| **Durable stav běhu** | checkpointy, transcript | **Dapr** (rozhodnuto) – sandbox stav nedrží |

## Čtyři otázky, které vrstva musí zodpovědět

| # | Otázka | Co to znamená v autonomní firmě |
|---|---|---|
| S1 | **Jak silná izolace a za jakou cenu?** | proces (seccomp/bwrap) vs. kontejner vs. gVisor/Kata vs. microVM (Firecracker); start, cena per sandbox, hustota, GPU; útočný model: agent = neověřený kód, který běží s právy sandboxu |
| S2 | **Co sandbox smí vidět a kam smí ven?** | egress jen přes gateway (modely) a schválené proxy (git, registry, API zákazníka); žádná tajemství v sandboxu (OpenBao mimo, krátkodobé tokeny); identita sandboxu = SVID agenta + on-behalf-of; OPA rozhoduje o nástrojích i síti |
| S3 | **Jak v něm agent pracuje?** | Claude Code / Agent SDK uvnitř (sandbox-runtime, MCP servery), devcontainer jako definice prostředí, snapshot/obnova, cache závislostí, paralelní sandboxy per úkol, předání výsledku (commit, artefakt) ven |
| S4 | **Co z něj vidíme a kolik to stojí?** | každý příkaz a soubor jako span/událost do ClickHouse; approval na nevratné akce (push, deploy, platba); životní cyklus (TTL, úklid, kvóty per tenant); cena per úkol a per role |

## A. Vyřazovací kritéria

Společná A1–A5 z [`../frameworks/kriteria.md`](../frameworks/kriteria.md), pro tuhle vrstvu konkrétně:

| # | Kritérium | Co to znamená tady |
|---|---|---|
| A1 | OSI licence produkčního runtimu | **Pozor:** Daytona, Coder, Gitpod/Ona AGPL (ověř doslovně); Judge0 GPL; hostované sandboxy (E2B Cloud, Modal, Browserbase) mají SDK Apache, ale runtime je služba |
| A2 | Kontejnery na Kubernetes | runtime sandboxu musí běžet na K8s zákazníka (RuntimeClass gVisor/Kata, Firecracker vyžaduje bare-metal/nested virt – zapiš požadavky) |
| A3 | Air-gapped | obrazy a závislosti z interního registru/cache; žádný „pull při startu z internetu“; model jen přes gateway |
| A4 | Bez řízené služby jednoho cloudu | Azure Container Apps dynamic sessions / ACI smí být **backend za abstrakcí** (Dapr? CRD?), ne formát prostředí |
| A5 | Stav mimo runtime | definice prostředí (devcontainer.json, Dockerfile, Nix) a výsledky (git, artefakty, trace) žijí mimo sandbox; sandbox je zahoditelný |

## B. Bodovaná kritéria

### B1. Izolace a útočný model (S1)

| Co | Jak se to zjistí |
|---|---|
| Hranice: kernel sdílený (seccomp, namespaces, bwrap) / user-space kernel (gVisor) / microVM (Kata, Firecracker) | docs runtimu, CVE historie, threat model |
| Start sandboxu, hustota na uzel, podpora GPU, nested virtualizace (Azure: které SKU) | benchmark v harnessu, docs cloudu |
| Řízení zdrojů (CPU, RAM, disk, čas) a kill při překročení | cgroups, limity runtimu |
| Snapshot / obnova / fork (paralelní větve téhož úkolu) | Firecracker snapshot, CRIU, overlay |

### B2. Síť, tajemství a identita (S2)

| Co |
|---|
| Default deny egress; allow-list přes proxy (agentgateway jako egress pro modely; HTTP proxy pro git/registry/API); DNS pod kontrolou |
| Žádné statické credentials v sandboxu: krátkodobé tokeny (exchange v agentgateway, SVID), git credential helper přes proxy, OpenBao mimo sandbox |
| Identita sandboxu = identita agenta (SPIFFE workload attestation v K8s) + on-behalf-of uživatele; OPA rozhoduje o síti i nástrojích z téhož Rega |
| Souborový systém: read-only base, zapisovatelná pracovní vrstva, žádný přístup k hostu; co se smí vynést ven (artefakt, commit) jde přes schválený kanál |

### B3. Pracovní prostředí agenta (S3)

| Co | Jak se to zjistí |
|---|---|
| Co dává **Anthropic nativně**: Claude Code sandboxing (`sandbox-runtime`: bwrap/seatbelt, network proxy), Agent SDK, Managed Agents sandbox (hostovaný – jen vzor), MCP servery uvnitř sandboxu | docs code.claude.com, repo sandbox-runtime, changelog |
| **Devcontainer** jako definice prostředí (spec, features, prebuild); Nix jako alternativa | spec devcontainers, co z toho umí zvolený runtime |
| Předpřipravené obrazy per role (vývojář, SRE, QA) a cache závislostí (npm, pip, uv) v air-gapped režimu | praxe, harness |
| Prohlížeč v sandboxu (Playwright/Chromium headless), code interpreter bez kontejneru (Wasm/Pyodide, Deno) | kandidáti |
| Orchestrace: kdo sandbox zakládá a ruší (Dapr workflow aktivita? K8s CRD `agent-sandbox`?), paralelní sandboxy per úkol, fronta | docs kandidátů |

### B4. Observabilita, schvalování a životní cyklus (S4)

| Co |
|---|
| Každý příkaz, síťový požadavek a změna souboru jako událost s trace kontextem (OTEL) do ClickHouse; audit pro AI Act čl. 12 |
| Approval policy na nevratné akce (push do main, deploy, smazání, platba) – stejný mechanismus jako Inspect `approval` a hook Agent SDK |
| TTL, úklid, kvóty per tenant a per role; cena per sandbox-hodinu a per úkol; scale-to-zero |
| Evaly: produkční sandbox = Inspect sandbox provider (docker/k8s), aby evaly měřily totéž prostředí |

### B5. Governance projektu a provoz

| Co |
|---|
| Licence, nadace (CNCF, OpenInfra, Linux Foundation), CLA/DCO, bus factor, telemetrie – jako B1 u frameworků |
| Helm/operátor, HA, upgrade; SDK Python/TypeScript; cena odchodu (devcontainer je přenositelný, snapshoty ne) |

### B6. Cena

| Co |
|---|
| Cena per sandbox-hodina na Azure (VM SKU s nested virt vs. běžné uzly), hustota, start; cena nečinných sandboxů (scale-to-zero) |
| Cena egress proxy a cache obrazů; cena za paralelní větve (fork) |

## C. Čím se záměrně neřídit

| Anti-kritérium | Proč |
|---|---|
| „Docker stačí“ | sdílený kernel + agent spouštějící neověřený kód = únik je otázkou času; minimálně gVisor/Kata pro cizí kód |
| Hostovaný sandbox jako jádro (E2B Cloud, Modal, Managed Agents) | A4; smí být jen vzor nebo záložní backend za abstrakcí |
| Tajemství v env sandboxu „protože to je jednodušší“ | každý exfil z promptu je pak exfil klíče; tokeny krátkodobé a mimo |
| Persistentní „agentův počítač“ | stav patří do gitu, artefaktů a paměti; persistentní sandbox je neauditovatelný a neopakovatelný |

## Changelog
- 2026-10-23: první verze; druhy prostředí, otázky S1–S4, kritéria B1–B6.

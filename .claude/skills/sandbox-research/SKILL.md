---
name: sandbox-research
description: Postup pro průzkum a prověrku vrstvy sandboxů a pracovního prostředí multiagentní platformy (gVisor, Kata Containers, Firecracker, Sysbox, Kubernetes agent-sandbox, Anthropic sandbox-runtime (anthropics/sandbox-runtime) a Claude Code sandboxing, nsjail, bubblewrap, E2B, Daytona, Modal, microsandbox, OpenHands runtime, SWE-ReX, Pyodide/Wasm, Deno, Jupyter, Playwright, Steel, browser-use, devcontainer, DevPod, Nix, Coder, Azure Container Apps dynamic sessions) a pro aktualizaci knowledge/sandbox/. Použij vždy, když Adam řeší, kde agent spouští kód, testy nebo prohlížeč, izolaci neověřeného kódu, egress a tajemství v sandboxu, devcontainery a předpřipravená prostředí rolí, snapshoty a paralelní běhy, cenu sandboxů na Azure, nebo schvalování nevratných akcí – i když slovo "sandbox" výslovně nezazní.
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

## 7b. Pasti z kola 1 (2026-10-23)
- **Weby docs blokované** (gvisor.dev, learn.microsoft.com, e2b.dev, modal.com, containers.dev, inspect.aisi.org.uk) – čti zdrojové
  repozitáře docs: `MicrosoftDocs/azure-aks-docs`, `MicrosoftDocs/azure-compute-docs` (nested virt per SKU v `sizes/*.md`),
  `google/gvisor/g3doc`, `UKGovernmentBEIS/inspect_k8s_sandbox/docs`.
- **Root `LICENSE` ≠ licence balíčku v monorepu** (E2B: root Apache-2.0, SDK MIT). **OSS runtime zamrzne, SDK na registru žije**
  (Daytona: `main` jen README od 06/2026, PyPI dál vydává). **Closed-source telemetrie default on v GPL repu** (Judge0).
- **srt je beta a sdílený kernel** – nikdy jediná hranice; deny list na Linuxu se staví při startu; TLS proxy neterminuje;
  v neprivilegovaném kontejneru jen `enableWeakerNestedSandbox`; Claude Code sandbox nekryje MCP, hooky, Read/Edit.
- **Firecracker nemá K8s runtime** (fc-containerd bez releasů, bez CRI); Kata GPU jen QEMU; NC SKU bez nested virt.
- **agent-sandbox**: stateful PVC model, egress a identita per claim jen v roadmapě, příklad montuje API klíč ze Secretu.
- **Playwright MCP `--allowed-origins` není bezpečnostní hranice**; obraz Playwright je „testing only“, root = Chromium sandbox off.
- **AGPL u DX nástrojů** (Coder, Gitpod/Ona, Lightpanda, Daytona OSS, Arrakis); telemetrie default on u browser-use, DevPod, Coder, Lightpanda.
- **Env `HTTPS_PROXY` agent odstraní** – vynucení egressu musí být síťové (CNP) a v proxy, ne v proměnné.
- **Managed Agents**: request bez `networking` = `unrestricted`; allow-list je per host, ne per operace.
- **`inspect_k8s_sandbox` s `networkPolicy.enabled: false`** nic neomezuje a `allowDomains` odmítá; bez Cilia nutná vlastní NetworkPolicy.

## 7c. Pasti z kola 2 a harnessu S1 (2026-10-23)
- **Zdroje místo blokovaných webů:** Azure docs = `MicrosoftDocs/azure-aks-docs`, `azure-compute-docs`, `azure-docs` (raw, `ms.date`; diff přes
  `github.com/…/commit/<sha>.diff`); verze Azure Linux balíčků = `microsoft/azurelinux/3.0/SPECS/*`; gVisor syscall tabulka =
  `pkg/sentry/syscalls/linux/linux64.go`; AKS release notes `github.com/Azure/AKS/releases?q=`; ceny (`prices.azure.com`, agregátory) blokované → jen *sek.*
- **srt v K8s:** containerd `RuntimeDefault` seccomp blokuje `unshare`/`clone` s ns flagy bez `CAP_SYS_ADMIN` → bwrap nestartuje; `enableWeakerNestedSandbox`
  mění jen `--proc` → `--bind /proc`; root potřebuje `CAP_SETFCAP` → non-root; bez seccomp helperu tichá degradace; `parentProxy` je objekt `{http, https}`
  a vypíná resolved-address check; CLI loguje odmítnutí jen pod `SRT_DEBUG`; mandatory deny z cwd při startu; `NO_PROXY` s RFC1918/link-local → IP literály mimo proxy.
- **Kata na AKS:** `seccompProfile` podu se v guestu neaplikuje (`disable_guest_seccomp` default true), guest `kernel-uvm` bez Landlock, `hostUsers: false` nejde (#8170),
  na Pod Sandboxing poolu není `/dev/kvm` (kernel-mshv) → upstream `kata-qemu`/`kata-clh` tam nepoběží.
- **agentgateway egress:** `backendAuth` jen na terminované HTTPS routě, ne na TLS passthrough; nepovolené SNI = TLS EOF (curl exit 35), ne 403;
  1.6.0 bez loopback/link-local ochrany dynamic backendu (PR #3889 až 1.7) → CNP na gateway podu; bez nameserverů fallback na Google DNS (A3).
- **Inspect approval** = fnmatch nad `tool(arg='…` (prefix glob), ne regex; `auto_approver("reject")` v Python API.
- **Agent SDK `sandbox` option existuje** (Py i TS) – Python default bez `failIfUnavailable` běží nesandboxovaně.
- **`allowed_tools` neomezuje, jen předschvaluje:** v `bypassPermissions` má CLI Bash/Write/Edit/WebFetch na hostu a načte `.mcp.json` repa (O-2 live 2026-10-24). Role = `tools=[]` + `strict_mcp_config=True` + `setting_sources=[]` + cwd mimo repo; hranice je pod + `srt claude` + CNP.
- **Živý model injekci často odmítne sám** – obranu platformy měří jen adversariální (mock) agent; live běh je o ceně a chování, ne o gate.

## 8. Čemu se vyhni
- Nevybírej podle DX nebo počtu jazyků – vybírej podle izolace, egressu a provozu na K8s zákazníka.
- Nezaměňuj „kontejner“ za sandbox pro neověřený kód.
- Netvrď požadavky na nested virtualizaci na Azure ani licenci DX nástrojů z paměti – ověř.

---
tema: Fáze P2 – role naostro (návrh plánu po uzavření P1)
naposledy_overeno: 2026-10-25
zralost: návrh (čeká na Adamovo potvrzení rozsahu a pořadí)
primarni_zdroje:
  - knowledge/platforma/produkt.md
  - knowledge/platforma/p1-aks.md
  - knowledge/organization/autonomie.md
  - knowledge/organization/metriky.md
  - knowledge/sandbox/azure-kata-gvisor.md
  - tools/rolegen/README.md
---

# P2 – role naostro

**Závěr (doporučení):** P1 skončilo tím, že zakázka projde AKS clusterem s rolemi jako Kata pody, ale konfigurace rolí do
clusteru stále nosí harness a identita role v podu je jen Keycloak token ze Secretu. P2 má udělat z `roles/*.yaml` **jediný
zdroj, ze kterého CI a GitOps vyrobí všechno** (OPA bundle, klíče gateway, obrazy, pod spec, evaly), a zavést **eval gate**
jako podmínku nasazení verze role. Doporučené pořadí: P2-1 (CI → cluster) → P2-2 (obrazy a pod spec z rolegen) → P2-5 (evaly
s gate, protože bez nich nejde povýšit autonomii) → P2-3 (SVID v Kata podu, OpenBao auto-unseal) → P2-4 (egress git/mirror
přes gateway) → P2-6 (FinOps součet klíčů). Měřítko zůstává: **každý krok má harness, nic se nestaví bez měření.**

## Kroky

| Krok | Co se postaví | Zdroj pravdy → nástroj | Co se měří | Hotovo, když |
|---|---|---|---|---|
| **P2-1** rolegen v CI naostro | GitHub Actions job na změnu `knowledge/organization/roles/*.yaml`: rolegen → `build/` → commit do `infra/k8s/roles/generated/` (ConfigMapy `rolegen-build`, `agentgateway-config` policies, OPA data) → Flux aplikuje; změna role = PR s dvěma schvalovateli (N6) | `roles/*.yaml` → rolegen → Git → Flux | **R1** v CI (už běží) + nový **P21**: změna `budget` role v PR → merge → gateway v clusteru má nový limit bez ručního kroku; harness vlastní jen tajemství (klíče, token OpenBao) | P1-6 harness `step_p1_6` nerenderuje `agentgateway-config` ani `rolegen-build` – bere je z Fluxu |
| **P2-2** obrazy rolí a pod spec z rolegen | devcontainer build per role v CI (`az acr build`, `roles/<role>:<version>` + digest), bez cloud CLI, se srt a nástroji; `role_pod.py` použije `build/k8s/<role>-pod.yaml` jako šablonu (jen doplní jména, Secret, env běhu) | `roles/*.yaml` `sandbox.image`, `sandbox.pod` → rolegen `k8s/` → `role_pod.py` | **S1 image checky** na obrazu role (nástroje přítomny, cloud CLI ne, srt weaker funguje, uid 1000); **P22**: pole pod specu v clusteru == `build/k8s/<role>-pod.yaml` (diff prázdný) | pod role běží z obrazu role, ne z obrazu aplikace |
| **P2-3** identita role v Kata podu + tajemství | SVID pro pod role: SPIRE agent jako sidecar v podu (atestace `k8s_psat` per pod) nebo spiffe-helper přes Workload API v guestu – hostPath socket do Kata VM nevede (P1-6); SVID → token exchange na gateway (I2) místo Keycloak tokenu v Secretu; OpenBao auto-unseal (Azure Key Vault seal) + auth `kubernetes` pro aplikaci (žádný root token v Secretu) | SPIRE entries z rolegen (`identity.spire_selectors`), OpenBao policy z rolegen | **I2** proti clusteru; **P23**: pod role bez Secretu s tokenem dostane SVID, gateway vymění za token s `agent_id`, PEP paměti přijme; OpenBao startuje unsealed po restartu | v Secretu běhu zbývá jen klíč gateway a token běhu (nebo nic) |
| **P2-4** egress naostro | agentgateway CONNECT 3128 pro `git.platform.internal` (terminace TLS, `backendAuth` vloží GitHub token, push jen `agent/{wf}/*`, `main` → 403) a `mirror.platform.internal` (npm/pypi proxy); role s `sandboxed_bash` → `git push` větve z podu | `roles/*.yaml` `egress_allow`, `http.routes` → rolegen gateway config | **S1f/G** z podu role: push na větev úkolu 200, push na `main` 403, `npm install` z mirroru OK, přímý internet timeout | Vývojář otevře PR z podu bez tokenu v podu |
| **P2-5** evaly L0–L3 s gate + registr agentů | Inspect AI sady per role z `build/inspect/` (L0 smoke, L1 policy-compliance = 0 OPA deny, L2 pass^3 na úkolech role, L3 injekce s **adversariálním mock agentem**, ne živým modelem); gate v CI před povýšením verze role; registr `org.agents` (verze role, model, policy_version, eval výsledky) plněný z workflow | `roles/*.yaml` `evals.layers` → rolegen → Inspect → `org.eval_gates` | **P25**: verze role s L3 propadem se nenasadí (Flux ji nedostane), role v registru má stav; `pass^3 ≥ gate` z `evals_df()` | autonomie A1→A2 podle metriky.md je rozhodnutelná z dat, ne z dojmu |
| **P2-6** FinOps naostro | 30d strop zakázky jako součet klíčů zakázky (ledger z `request_logs` gateway do ClickHouse), OpenBao vydává klíče role × zakázka při založení zakázky (rolegen zapíše hash), cena zakázky v registru | gateway `request_logs` → Collector → ClickHouse | **O-2 budget** proti clusteru + **P26**: součet útraty 4 klíčů > 30d strop → zakázka `BudgetExceeded` | cena zakázky čitelná z jedné tabulky, strop platí pro zakázku, ne klíč |

## Co z P1 zůstává zjednodušené i v P2 (vědomě)

| Zjednodušení | Proč zůstává | Kdy |
|---|---|---|
| Mock GitHub a mock upstream modelu v clusteru pro měření; živý model a GitHub jen při ručním běhu s PAT | cena a souhlas Adama na každý ostrý běh; mock měří platformu, ne model | ostrý běh po každém kroku na vyžádání |
| Flexible Server s veřejným endpointem, heslo přes Flux substitute | dev; VNet integrace a External Secrets Operator až P3 | P3 |
| Dapr bez operátoru/mTLS, Keycloak bez TLS, HTTP uvnitř clusteru | dev cluster bez tenantů; mTLS řeší SPIRE + gateway v P3 | P3 |
| `on_behalf_of` v tokenu role | až AG-UI a lidský token (token exchange) | P3 |

## Rizika

| Riziko | Dopad | Zmírnění |
|---|---|---|
| SPIRE agent v Kata podu: atestace `k8s_psat` per pod zvedne počet agentů na počet podů; výkon/latence startu (+ sekundy) | P2-3 | změřit v P23 proti variantě token exchange z Keycloak tokenu; SVID jen pro role s nevratnými akcemi |
| Devcontainer build per role v CI je pomalý (minuty) a obrazy velké (400 MB+) | P2-2 | base obraz platformy + vrstva role; cache v ACR; měřit start podu po pullu (P1-6: 102 s na novém uzlu) |
| L3 evaly s adversariálním agentem nejsou standardní Inspect sada | P2-5 | mock agent z O-2 (poslechne každou injekci) jako Inspect solver; gate 100 % jen na vlastní sadě |
| CI zapisuje do `infra/k8s/roles/generated/` – smyčka commitů | P2-1 | job jen na změnu `roles/*.yaml`, commit s `[skip ci]`, Flux sleduje jen `main` |
| Cena: pool kata musí být nahoře pro evaly L2 (pass^3 × role × úkoly) | P2-5 | evaly v CI jen při změně role; cluster `stop` mimo měření (jako v P1) |

## Postup

| Krok | Stav |
|---|---|
| P2-1 | ✅ **2026-10-25 AKS 7/7** (`tools/harness_p1_k8s --step p2-1`, `measure` run 40195984513): konfigurace gateway a rolegen build z Gitu přes Flux (`infra/k8s/rolegen` component z `render_k8s.py`, CI `rolegen.yml --check`), ConfigMapy v clusteru == render HEAD; klíče role × zakázka vydává aplikace do `agentgateway-keys` (sidecar `config-merge` → hot reload, propagace na obě repliky 69 s), rozpočty == `roles/*.yaml`; harness dodal jen tajemství. Zbývá: klíče z OpenBao (P2-6), zrušit `render_gateway` v kind harnessu |
| P2-2 | ✅ **2026-10-25 AKS 10/10** (`--step p2-2`, `measure` run 40200765801): obrazy rolí `roles/<role>:0.1.0` z rolegen (`infra/images/roles`, `az acr build` vrstvy nad obrazem platformy, options/srt/managed settings zapečené, bez cloud CLI – ověřeno sondou z podu), pod role ze šablony `pod-<role>.yaml` z rolegen (aplikace doplní jen běh), zakázka end-to-end beze změny. Zbývá: devcontainer CLI build místo ACR Tasks (volitelné), digest obrazu v SPIRE selektoru (P2-3), AcrPull pro `az acr repository` z runneru (role přidána, zatím bez efektu) |
| P2-3 | ✅ **2026-10-25 AKS 17/17** (`--step p2-3`, `measure` run 40234528827, 10 běhů): OpenBao seal `azurekeyvault` jako externí KMS plugin (OpenBao 2.7 cloud sealy nemá; Key Vault + klíč z Terraformu, UAMI + federated credential na SA `openbao`, `workload_identity`) – po smazání podu unsealed za 38 s bez operátora; auth metoda `kubernetes` pro aplikaci (`app.bao_token`, TTL 1 h, Secret bez tokenu OpenBao); SVID podu role: SPIRE agent jako sidecar (k8s_psat projektovaným tokenem SA `role`, alias uzlu per role z rolegen `spire/entries.json`, workload `unix:uid`, socket na tmpfs v guestu), JWT-SVID `spiffe://platform/role/<role>/acme` do 5 s, server paměti ho ověřuje přes `spire-oidc`. Omezení: agent ID k8s_psat = UID uzlu → pody rolí na jednom uzlu Kata sdílejí agent ID (runner čeká na SVID své role; paralelní pody na uzlu → P3: agent identita per pod). Zbývá (P3): token exchange SVID→Keycloak v gateway, bundle serveru do ns rolí (dnes `insecure_bootstrap`), TLS listener OpenBao |
| P2-4 | ✅ **2026-10-26 AKS 21/21** (`--step p2-4`, `measure` run 40307712561, 7 běhů): gateway egress z rolegen (CONNECT bind 3128, HTTPS listenery `git/mirror.platform.internal` s terminací, routa git = sjednocení metod z `authz.http` + `backendAuth` – token jen v gateway, mirror GET, passthrough allow-list), tajemství egressu (CA, cert, token, `platform-ca`) vydává harness mimo Git; Vývojář z Kata podu naklonoval, pushnul `agent/<wf>/vyvojar` a dostal odmítnutí `main` od git serveru (pre-receive hook = branch protection; gateway ref v pkt-line nevidí), pip i npm z mirroru, cizí SNI/HTTP :80/cizí repo neprojdou; NetworkPolicy egressu gateway (ne IMDS/privátní sítě); oprava ns gateway v `roles/*.yaml`. Otevřený bod (sonda šla přímo, ne přes srt – emptyDir `/work` nebyl v Kata guestu zapisovatelný) **uzavřen v P2-6**: `/work` jako emptyDir `medium: Memory`, sonda i `sandboxed_bash` jdou přes srt (`via: srt`); per-role `receive_pack` na gateway až s identitou na CONNECT (P3) |
| P2-5 | ✅ **2026-10-25 AKS 13/13** (`--step p2-5`, `measure` run 40206756683): evaly rolí L0–L3 v CI (`tools/role_evals`, Inspect AI, adversariální mock, PEP/approval jako data z definice role; 4 role passed, SRE unevaluated), `eval-status.json` Git → ConfigMap → `app.role_gate` (role bez gate se nespustí, ledger `ROLE_GATE`), negativní kontrola propadá, registr `org.role_definitions/eval_gates/agents` na Flexible Serveru naplněn z Gitu a ledgeru. Zbývá: L2 nad reálnými úlohami a živým modelem (pass^k dnes měří harness), `review-agreement` proti lidským labelům, L4/L5 online, registr plněný workflow místo harnessu (P3), SRE evaly s deploy MCP |
| P2-6 | 🟡 implementováno 2026-10-26: strop zakázky (`budget_usd`, výchozí `P0_ZAKAZKA_BUDGET_USD`) vynucuje orchestrátor aktivitou `budget_gate` před každou rolí ze součtu 30d útraty klíčů zakázky v `budget_usage` gateway (`finops.py`, DSN z Secretu `zakazka-finops`); `BudgetExceeded` zdroj `zakazka-sum` → stejná eskalace jako 429 (HITL `rozpocet`, timeout → pauza); cena zakázky v registru `org.zakazky` (spent_usd, by_role, status, keys_source); klíče role × zakázka vydává a drží OpenBao (entropie `sys/tools/random`, KV v2 `secret/zakazky/<id>/gateway-keys`, policy jen `zakazky/*`), v clusteru už žádný Secret `zakazka-keys-<id>`; `/work` role jako tmpfs v guestu (uzavření P2-4: sonda přes srt). Odchylka od plánu: ledger per request do ClickHouse přes Collector nepostaven – zdroj ceny je `budget_usage` (jedna tabulka, gateway ji vede sama); per-request ledger → P3 observabilita. ✅ **2026-10-26 AKS 24/24** (`--step p2-6`, `measure` run 40340791174, 4 běhy): cena zakázky 0,051 USD == nezávislý součet z DB, registr `org.zakazky` (Dokonceno/BudgetExceeded), strop 0,01 USD zastavil zakázku před Architektem (gate ze součtu klíčů, HITL `rozpocet` timeout → Pozastaveno), klíče v OpenBao KV s entropií `sys/tools/random`, **sonda egressu poprvé přes srt** (uzavřen otevřený bod P2-4). Zbývá (P3): per-request ledger do ClickHouse, strop zakázky i v gateway (identita zakázky na klíči), navýšení stropu z HITL `rozpocet` (dnes jen pauza) |

## Changelog
- 2026-10-26: P2-6 změřeno 24/24 (4 běhy) – **fáze P2 uzavřena** (P2-1…P2-6 ✅). Rozhodnutí: strop zakázky vynucuje orchestrátor ze součtu klíčů v `budget_usage` (gateway hlídá jen klíč); cena zakázky v `org.zakazky`; klíče role × zakázka drží OpenBao KV; per-request ledger do ClickHouse odložen do P3. Nálezy srt na Katě: emptyDir přes virtiofs pro uid 1000 nezapisovatelný (Memory medium ano), cache npm/pip pod `/work`, `~/.gitconfig` pod mandatory deny.
- 2026-10-26: P2-6 implementováno (strop a cena zakázky z budget_usage, klíče z OpenBao KV, registr org.zakazky, /work jako tmpfs).
- 2026-10-26: P2-4 změřeno 21/21 (7 běhů). Nálezy: srt v podech rolí od P1-6 vůbec neběžel (chyběl `ripgrep`) – P21c měřilo jen přítomnost binárky; po opravě srt vynucuje `allowWrite /work`, emptyDir `/work` v Kata guestu pro uid 1000 nezapisovatelný (otevřeno). Rozhodnutí: branch protection = git server (gateway ref nevidí), routa gateway = sjednocení metod rolí, per-role rozlišení až s identitou na CONNECT (P3).
- 2026-10-26: P2-4 implementováno (gateway egress z rolegen, tajemství egressu z harnessu, mock GitHub smart HTTP + mock mirror, sonda egressu v runneru).
- 2026-10-25: P2-3 implementováno; rozhodnutí: SVID v Kata podu = agent per pod (sidecar) atestovaný k8s_psat, ne hostPath socket; JWT-SVID přijímá server paměti přímo (druhý vydavatel), token exchange SVID→Keycloak v gateway až P3.
- 2026-10-25: P2-3 změřeno 17/17 (10 běhů; pasti: OpenBao 2.7 bez cloud sealů → KMS plugin, Flux substitute ve skriptu init kontejneru, StatefulSet uvázlý na mezilehlé revizi, domény OIDC provideru bez portu, unix socket na virtiofs emptyDir, agent ID k8s_psat = UID uzlu – viz `infra/README.md` a README harnessu). Rozhodnutí pro P3: identita agenta per pod (ne k8s_psat) dřív, než poběží pody rolí paralelně.
- 2026-10-25: P2-5 hotovo 13/13 na AKS – eval gate je podmínkou nasazení (CI) i běhu role (aplikace); registr org.* poprvé naplněn.
- 2026-10-25: P2-5 implementováno (evaly rolí s gate v CI, eval-status jako podmínka běhu role, registr org.*); rozhodnutí: L3 měří obranu platformy adversariálním mockem, ne model; L4/L5 zůstávají provozní (SKIP).
- 2026-10-25: P2-2 hotovo 10/10 na AKS; seccomp `Localhost` ze šablony se na Katě nahrazuje `RuntimeDefault` (profil na uzlu není, Kata guest ho neaplikuje) – zapsáno jako vědomý doplněk aplikace.
- 2026-10-25: P2-2 implementováno (obrazy rolí z rolegen přes `az acr build`, pod spec ze šablony rolegen); rozhodnutí: devcontainer CLI build odložen – Dockerfile je devcontainer-kompatibilní, staví ho ACR Tasks jako ostatní obrazy.
- 2026-10-25: P2-1 hotovo 7/7 na AKS; pasti: Flux substitute v generované ConfigMapě (`substitute: disabled`), propagace ConfigMap per replika (headless sonda).
- 2026-10-25: P2-1 implementováno (konfigurace z Gitu přes Flux, klíče per zakázka od aplikace, sidecar merge); rozhodnutí: žádné bot commity – generované manifesty jsou součást PR, CI jen kontroluje shodu s rolemi.
- 2026-10-25: první verze plánu P2 po uzavření P1 (návrh, čeká na Adamovo potvrzení rozsahu a pořadí).

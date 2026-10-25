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
| P2-3 | 🟡 implementováno 2026-10-25: OpenBao seal `azurekeyvault` (Key Vault + klíč z Terraformu, UAMI + federated credential na SA `openbao`, env `VAULT_AZUREKEYVAULT_AUTH_METHOD=workload_identity`), auth metoda `kubernetes` pro aplikaci (`app.bao_token`, žádný token v Secretu); SVID podu role: SPIRE agent jako sidecar (k8s_psat s projektovaným tokenem SA `role`, alias uzlu per role z rolegen `spire/entries.json`, workload `unix:uid`), JWT-SVID z Workload API (py-spiffe) → server paměti ověřuje přes `spire-oidc` (OIDC discovery provider jako sidecar serveru); čeká na měření P23 na AKS |
| P2-4 | ⬜ |
| P2-5 | ✅ **2026-10-25 AKS 13/13** (`--step p2-5`, `measure` run 40206756683): evaly rolí L0–L3 v CI (`tools/role_evals`, Inspect AI, adversariální mock, PEP/approval jako data z definice role; 4 role passed, SRE unevaluated), `eval-status.json` Git → ConfigMap → `app.role_gate` (role bez gate se nespustí, ledger `ROLE_GATE`), negativní kontrola propadá, registr `org.role_definitions/eval_gates/agents` na Flexible Serveru naplněn z Gitu a ledgeru. Zbývá: L2 nad reálnými úlohami a živým modelem (pass^k dnes měří harness), `review-agreement` proti lidským labelům, L4/L5 online, registr plněný workflow místo harnessu (P3), SRE evaly s deploy MCP |
| P2-6 | ⬜ |

## Changelog
- 2026-10-25: P2-3 implementováno; rozhodnutí: SVID v Kata podu = agent per pod (sidecar) atestovaný k8s_psat, ne hostPath socket; JWT-SVID přijímá server paměti přímo (druhý vydavatel), token exchange SVID→Keycloak v gateway až P3.
- 2026-10-25: P2-5 hotovo 13/13 na AKS – eval gate je podmínkou nasazení (CI) i běhu role (aplikace); registr org.* poprvé naplněn.
- 2026-10-25: P2-5 implementováno (evaly rolí s gate v CI, eval-status jako podmínka běhu role, registr org.*); rozhodnutí: L3 měří obranu platformy adversariálním mockem, ne model; L4/L5 zůstávají provozní (SKIP).
- 2026-10-25: P2-2 hotovo 10/10 na AKS; seccomp `Localhost` ze šablony se na Katě nahrazuje `RuntimeDefault` (profil na uzlu není, Kata guest ho neaplikuje) – zapsáno jako vědomý doplněk aplikace.
- 2026-10-25: P2-2 implementováno (obrazy rolí z rolegen přes `az acr build`, pod spec ze šablony rolegen); rozhodnutí: devcontainer CLI build odložen – Dockerfile je devcontainer-kompatibilní, staví ho ACR Tasks jako ostatní obrazy.
- 2026-10-25: P2-1 hotovo 7/7 na AKS; pasti: Flux substitute v generované ConfigMapě (`substitute: disabled`), propagace ConfigMap per replika (headless sonda).
- 2026-10-25: P2-1 implementováno (konfigurace z Gitu přes Flux, klíče per zakázka od aplikace, sidecar merge); rozhodnutí: žádné bot commity – generované manifesty jsou součást PR, CI jen kontroluje shodu s rolemi.
- 2026-10-25: první verze plánu P2 po uzavření P1 (návrh, čeká na Adamovo potvrzení rozsahu a pořadí).

# Harness P1 – platforma v Kubernetes (kind → AKS)

Měří kroky fáze P1 ([plán](../../knowledge/platforma/p1-aks.md)). Měřítko není nová funkce, ale **tytéž harnessy z P0 spuštěné
proti clusteru** – P1-2…P1-5 na kind, P1-6 na AKS (fáze P1 uzavřena 2026-10-25). Manifesty: [`infra/k8s`](../../infra/README.md).

## Krok P1-2 – datová vrstva (2026-10-24, kind, `results/p1-2-20261024-154408.json`)

| Check | Tvrzení | Výsledek |
|---|---|---|
| P12a | `infra/k8s/overlays/kind` aplikováno, StatefulSety postgres a clickhouse a Deployment otel-collector Ready | ✅ K8s v1.37.0 |
| P12b | Postgres přes NodePort: 16.15, pgvector 0.8.7, databáze memory / dapr_state / org / agentgateway z init SQL | ✅ |
| P12c | ClickHouse přes NodePort: 26.8.34.13 (přesně verze z O1), databáze otel | ✅ |
| P12d | Collector přijímá OTLP/HTTP; readiness přes `health_check` | ✅ (4 restarty, než naběhl ClickHouse) |
| P12e | **M1 proti clusterovému Postgresu** (`--db-uri`, role `memory_app` s heslem): RLS, PEP, karanténa, supersede, tombstone, OTEL spany, Inspect M-E3/M-E4 | ✅ 11/11 |
| P12f | **O1 proti clusterovému Collectoru a ClickHouse** (`--external`): trace SDK → gateway → Collector → ClickHouse, redaction, normalizer; CLI metriky a eventy čtené z tabulek `otel_metrics_*` a `otel_logs` | ✅ 9/9 |
| P12g | Obrazy, restarty, PVC (`standard` = local-path) | ℹ️ |

Co se pro to změnilo v harnessech P0 (zpětně kompatibilní, lokální režim beze změny):
`harness_memory_m1 --db-uri <superuser URI>` (externí Postgres; schéma se znovu vytvoří, `memory_app` dostane heslo),
`harness_observability_o1 --external` + `O1_CH_HTTP`/`O1_OTLP_HTTP` (nestartuje ClickHouse ani Collector; agentgateway tracing
na externí endpoint; metriky a logy z ClickHouse místo file exportéru).

Zjištění: v clusteru nemá smysl file exporter – `clickhouse` exporter ukládá i metriky (`otel_metrics_sum/gauge/histogram`) a logy
(`otel_logs`), takže O1h se měří dotazem. Kontejnerová verze ClickHouse `clickhouse:26.8` je bitově stejná řada jako statická binárka O1.

## Krok P1-3 – identita (2026-10-24, kind, `results/p1-3-20261024-161147.json`)

| Check | Tvrzení | Výsledek |
|---|---|---|
| P13a | Keycloak (Deployment), OpenBao (StatefulSet raft), SPIRE server + agent Ready; realm v `infra/` = kopie `realm-p0.json` z O-2 (sha256) | ✅ |
| P13b | Keycloak přes NodePort: discovery realmu p0, `client_credentials` → RS256, `aud=memory`, `tenant_id`, `agent_id`; realm a 13 klientů v Postgresu (DB `keycloak`) | ✅ 79 ms/token |
| P13c | OpenBao: init 1/1 + unseal operátorem (klíče jen v `logs/`), raft 1 voter, audit device z HCL, zdraví 200 | ✅ |
| P13d | **SPIRE:** agent atestován `k8s_psat`; entry `spiffe://platform/role/vyvojar` (selektory `k8s:ns`, `k8s:pod-label:role:vyvojar`); pod s labelem dostane SVID (TTL 1 h), pod bez labelu `no identity issued` | ✅ |
| P13e | **O-2 `identity` proti clusteru** (`--kc-url`, `--bao-addr`, audit z `kubectl logs -f`): JWKS, HS256 odmítnut, transit podpis, padělek → `HITL_INVALID_TOKEN` | ✅ 5/5 |
| P13f | Obrazy a restarty (agent 1× – bundle race) | ℹ️ |

Co se změnilo v O-2: `--kc-url`, `--bao-addr --bao-root-token --bao-audit-file` (externí Keycloak/OpenBao místo lokálních procesů);
příprava OpenBao je idempotentní (`bao_setup`). Scénáře O-2 teď hlásí neošetřenou výjimku jako FAIL `ERR` (dřív ji `finalize()`
v `finally` zamaskoval exit kódem 0 – první běh P13e tak skončil po třech checkách bez chyby; při opakování prošel 5/5, příčina nezjištěna).

Co SPIRE v P1-3 říká pro P1-6: identita role bude SVID z pod-labelu `role=<role>` – přesně to, co `rolegen` zapisuje do `k8s/<role>.yaml`;
entries se musí vytvářet z rolegen (dnes ručně v harnessu), token exchange SVID → Keycloak token zůstává na gateway (I2).

## Krok P1-4 – model gateway (2026-10-24, kind, `results/p1-4-20261024-181600.json`)

agentgateway 1.6.0 jako Deployment **2 repliky** (`infra/k8s/base/agentgateway`), `config.database` → Postgres (DB `agentgateway`,
tabulka `budget_usage` sdílená replikami), LLM listener s `policies.apiKey` z rolegen (zakázka P1-4, `mode: optional`), upstream =
mock G1 na hostiteli (pod → bridge IP `172.18.0.1`). Config ConfigMapy renderuje harness (base + upstream + klíče) – v cíli CI z rolegen.

| Check | Tvrzení | Výsledek |
|---|---|---|
| P14a | 2 repliky Ready, config z base + rolegen klíče, `$AGW_DATABASE_URL` ze Secretu dosazen → tabulky `budget_usage`, `request_logs` v Postgresu | ✅ |
| P14b | Klíč Vývojáře → 200 od mocku na hostiteli, log `role`/`zakazka`; cizí klíč 401; bez klíče (optional) 200 bez role | ✅ |
| P14c | `budget_usage` sdílená: used_amount = cena všech 200 odpovědí z **obou** replik (7 × 0,0030156 USD) | ✅ konzistentní po ~7 s |
| P14d | **P1-G:** Block 0,01 USD přes 2 repliky (nové spojení na každý request → kube-proxy střídá pody) → 429 s `Retry-After` do konce okna; **6 requestů prošlo místo 3** (přestřel 3,68 requestu ≈ 0,011 USD) | ✅ změřeno |
| P14d2 | Klíč Reviewera blokem Vývojáře nedotčen | ✅ |
| P14e | **G1 proti clusterové gateway** (`--gateway-url`, mock na hostiteli, klíč Reviewer): kontrakt Anthropic Messages API | ✅ 21/21 + 6 INFO |
| P14f | Pody | ℹ️ |

**Zjištění P1-G (persistence rozpočtů mezi replikami):** usage se do Postgresu zapisuje aditivně (upsert `used_amount + delta`), takže
součet je po flushi správný. Vynucení je ale **eventually consistent**: každá replika kontroluje `used >= limit` nad svým čítačem v paměti
a o útratě druhé repliky se dozví až při flushi/reconcile (5 s). Přestřel = útrata všech replik za ≤ 5 s; při jedné replice byl 0,68
requestu, při dvou 3,68. Pro P1 přijatelné (limit je měkký strop s auditem), pro ostrý strop: jedna replika listeneru s budgets
(PDB), nebo `localRateLimit` per klíč jako tvrdá brzda, nebo kratší flush (není konfigurovatelný, `FLUSH_INTERVAL` 5 s v kódu).
Druhý nález: dvě repliky startující současně proti prázdné DB se perou o migrace (`duplicate key … pg_type_typname_nsp_index`) – jedna
spadne a restartuje se; rollout restart (surge 1) tomu předchází, při prvním nasazení je restart očekávaný.

## Krok P1-5 – workflow, paměť a bridge v clusteru (2026-10-24, kind, `results/p1-5-20261024-193226.json`)

Poprvé běží **celá zakázka uvnitř Kubernetes**: OPA (PDP org + memory), Dapr placement + scheduler (`infra/k8s/base/dapr`), aplikace
zakázky s daprd sidecarem a Postgres state store, server paměti M1, mock GitHub a bridge (`infra/k8s/base/zakazka`), to vše v obrazu
`platform/zakazka-app` (Python 3.12 + Node 22 + Claude Code CLI, `infra/images/app`). Role běží zatím uvnitř aplikace (`agent_run`),
model = mock G1 na hostiteli přes clusterovou gateway s klíči role × zakázka, tokeny rolí si aplikace bere sama z clusterového Keycloaku
(`P0_KC_TOKEN_URL`, client_credentials s cache), approval tokeny podepisuje clusterový OpenBao, `sandboxed_bash` = bash v podu (`P0_SRT=none`).

| Check | Tvrzení | Výsledek |
|---|---|---|
| P15a | OPA, placement, scheduler, zakazka (app + daprd), memory, mock-github, bridge Ready; Dapr state store v Postgresu (`dapr_state`: tabulky `state`, `dapr_metadata`) | ✅ rollout 41 s |
| P15b | **Zakázka end-to-end v clusteru přes GitHub HITL**: issue → `/schvaluji` → ADR → H2 → PR → review APPROVED na head SHA → merge executor → H5 → Dokonceno; 4 role, paměť 200, 4 podpisy OpenBao | ✅ |
| P15c | **Durabilita:** pod aplikace smazán, když zakázka čeká na H2 → nový pod obnoví instanci ze stavu v Postgresu (status RUNNING), H2 doručeno novému podu, Vývojář a Reviewer doběhli, Dokonceno | ✅ 42 s |
| P15d | Paměť: zápisy rolí jako `proposed`, člověk (password grant, iss `keycloak:8080` i přes NodePort) je vidí s `include_unverified` | ✅ |
| P15e | FinOps: `budget_usage` v Postgresu nese útratu každé role za zakázku (0,078 USD / 2 zakázky) – zdroj pravdy místo logu na disku | ✅ |
| P15f | Bridge jako PEP: bot a cizí člověk odmítnuti (H1 i H4), člověk z allow-listu předán pro H1 a H4 (webhook i poll v clusteru) | ✅ |
| P15g | Pody | ℹ️ |

Zjištění a pasti P1-5 (zapsané i v `infra/README.md`):
- **ConfigMap `..data` symlinky**: OPA načítá adresář rekurzivně → „multiple default rules“; daprd hlásí ne-YAML soubory. Řešení `subPath` per soubor.
- **Pořadí apply**: `kubectl apply -k` vrací base ConfigMap gateway (upstream api.anthropic.com) a base Secret s placeholdery; agentgateway config
  hot-reloaduje → requesty šly na skutečné API a padaly na TLS (`UnknownIssuer`, busybox bez CA). Harness aplikuje base nejdřív, hodnoty až potom.
- **Čísla issue se po restartu mock GitHubu opakují**, ledger na PVC přežívá → bridge mapoval číslo na starou zakázku. Bridge teď bere nejnovější
  záznam; ids zakázek v harnessu jsou unikátní per běh (stav workflow v Postgresu přežívá, Dapr odmítne duplicitní instanci).
- Pokud role selže (např. 503 z gateway), aplikace přesto publikuje issue bez hashe a bridge `/schvaluji` odmítne (`no_artifact_hash_in_issue`) – správně fail-closed, ale zakázka visí; chybějící stav „role selhala → eskalace“ je úkol pro P2 (procesy X1).
- Apps v obrazu bez `curl`/`git`: mock Vývojář volá curl (push/exfil) – selže, soubory přesto vzniknou; sandbox a egress se měří v S1/P1-6, ne tady.


## P1-6 – role jako Kata pody na AKS (2026-10-25, Poland Central, workflow `measure` run 40187983339 → `results/p1-6-20261025-112356.json`, **6/6 + 2 INFO**)

Nic z P1-5 se nemění, jen `P0_ROLE_RUNTIME=pod`: Dapr aktivita role místo `agent_run` v procesu založí v ns `platform-roles` Secret
(token role pro paměť, klíč gateway role × zakázka, token běhu) a Pod z obrazu platformy s `role_runner.py` (`tools/harness_p0_o2/role_pod.py`).
Pod: RuntimeClass `kata-vm-isolation`, uzel poolu `kata` (autoscale 0–1), uid 1000, bez SA tokenu, drop ALL, seccomp RuntimeDefault, `/tmp` emptyDir,
NetworkPolicy ns default-deny + egress jen DNS, agentgateway, paměť a HTTP API aplikace. Artefakty zakázky si pod stáhne a vrátí přes
`/zakazky/{id}/files`, výsledek a ledger běhu pošle na `/runs/{id}/result` (hlavičky `X-Run-Id`/`X-Run-Token`). Harness běží na runneru GitHub Actions
(`kubectl port-forward`, OpenBao init do Secretu `openbao-init`, schéma M1 na Flexible Serveru přímo z runneru, pravidlo „Allow Azure services“).

| Check | Tvrzení | Výsledek |
|---|---|---|
| P16a | Flux kustomizations `platform` + `roles` Ready na revizi HEAD; platforma vč. mock upstreamu modelu v clusteru Ready; OpenBao init/unseal/transit; paměť na Flexible Serveru (admin `platform`, TLS) | ✅ |
| P16b | **Zakázka end-to-end na AKS**, 4 role jako pody: issue → `/schvaluji` → ADR → H2 → PR → review → merge → H5 → Dokonceno; `ROLE_POD` Succeeded s výsledkem pro každou roli, `AGENT_RUN` z podu (`via=pod`), paměť 200, podpisy OpenBao | ✅ 0,045 USD |
| P16c | Izolace: každý pod na uzlu `aks-kata-…`, RuntimeClass `kata-vm-isolation`, uid 1000, `automountServiceAccountToken: false`, srt v podu; po běhu pod i Secret smazány (sirotek z přerušeného běhu uklizen GC) | ✅ |
| P16d | Egress podu role: `1.1.1.1:443` a `github.com:443` timeout (NetworkPolicy), paměť 13 ms, gateway 8 ms, aplikace 18 ms open | ✅ |
| P16e | Časy: **první role se scale-upem poolu kata z 0**: schedule 82 s + start 102 s (nový uzel, pull 400 MB obrazu, boot Kata VM) = 127 s; další role na běžícím uzlu: start 2 s, běh 11–12 s, 24 s celkem | ℹ️ |
| P16f | Paměť: zápisy rolí z podů `proposed`, člověk (password grant přes port-forward, iss `keycloak:8080` z `KC_HOSTNAME`) je vidí | ✅ |
| P16g | FinOps: `budget_usage` na Flexible Serveru nese útratu každé role (account 0,009, architekt/vývojář/reviewer 0,012 USD) | ✅ |
| P16h | Pody a uzly | ℹ️ |

Zjištění a pasti P1-6 (i v `infra/README.md`):
- **`kubectl rollout restart` vs. Flux**: Flux (SSA) vrátí anotaci `restartedAt` → Deployment se přerolluje zpět, pod aplikace zemřel uprostřed běhu role.
  Harness restartuje smazáním podů (`restart_pods`), šablona se nemění.
- **Sirotčí pody rolí**: po zabití aplikace zůstal pod role (Succeeded) i Secret běhu → `role_pod.gc_orphans` před každým během maže pody Succeeded/Failed
  nebo starší než timeout a Secrety bez podu (ledger `ROLE_POD_GC`). Mazání podu je asynchronní (Kata VM se vypíná) – check čeká až 120 s.
- **PVC na Azure Disku patří rootu** → `fsGroup: 1000` na podu aplikace, jinak `PermissionError` na ledgeru (kind local-path to maskoval).
- **Pohyblivý tag obrazu `p1`** → `imagePullPolicy: Always` (Deploymenty i pody rolí), jinak uzel drží starý obraz.
- **Objekty vlastněné harnessem** (`agentgateway-config`, `zakazka-secrets`): `kustomize.toolkit.fluxcd.io/ssa: IfNotPresent` – Flux je založí, nikdy nepřepíše.
- Runner potřebuje i `fastapi`/`opentelemetry-sdk` (embedding M1 importuje `memory_server`).
- SVID z SPIRE v Kata podu zatím není: Workload API je unix socket agenta přes hostPath, do VM nevede (P2: spiffe-csi/agent v guestu).
- Pod spec staví `role_pod.py` z env, ne přímo `build/k8s/<role>-pod.yaml` z rolegen – stejná pole, jeden zdroj pravdy až v P2.


## P2-1 – role → Git → Flux, klíče vydává aplikace (2026-10-25, AKS, `--step p2-1`; `p1-6` je od teď alias) – **7/7**

Co se změnilo proti P1-6: harness **nerenderuje** konfiguraci gateway ani rolegen build. Oboje je v Gitu – `infra/k8s/rolegen/`
(generuje `tools/rolegen/render_k8s.py` z `knowledge/organization/roles/*.yaml`, CI `rolegen.yml` hlídá `--check`) a aplikuje ho Flux jako
kustomize component obou overlayů. Klíče gateway role × zakázka vydává aplikace při prvním běhu role zakázky (`gateway_keys.py`): hash a
rozpočty ze šablony rolegen do ConfigMapy `agentgateway-keys`, hodnoty do Secretu `zakazka-keys-<id>`; sidecar `config-merge`
(`gateway_merge.py`, nativní initContainer gateway) slévá config z Gitu a klíče do jednoho souboru, který agentgateway hot-reloaduje.
Harness dodává jen tajemství (`zakazka-secrets` bez `P0_ROLE_KEYS`, token OpenBao) a seed paměti.

| Check | Tvrzení | Výsledek |
|---|---|---|
| P21a | Flux Ready na HEAD; ConfigMapy `agentgateway-config` a `rolegen-build` v clusteru == render overlay `aks` z HEAD (diff prázdný); gateway má apiKey policy a upstream z env `LLM_UPSTREAM_URL` (mock-upstream); harness nic nerenderoval | ✅ |
| P21b | Zakázka end-to-end s rolemi jako Kata pody (jako P16b), Dokonceno, 0,045 USD | ✅ |
| P21b2 | Klíče vydala aplikace: ledger `GATEWAY_KEYS_ISSUED`, ConfigMap `agentgateway-keys` nese 5 klíčů zakázky s rozpočty Block 24h == `roles/*.yaml` (10/30/20/20/50 USD), Secret `zakazka-keys-<id>`, sonda 401 → 200 na **obou** replikách za 69 s | ✅ |
| P21c–f | Izolace, egress, paměť jako P16; časy: první role 227 s (scale-up uzlu 132 s + pull/boot 173 s), další 24 s | ✅ / ℹ️ |
| P21g | FinOps podle hashů z ConfigMapy klíčů: account 0,015 (vč. sond), ostatní 0,012 USD | ✅ |

Výsledek: **7/7 + 2 INFO** (`measure` run 40195984513, `results/p2-1-20261025-131749.json`). Předchozí běhy odhalily dvě pasti (opraveno):
- Flux `postBuild.substitute` smazal `${SVID_JWT}` v env rolí v `rolegen-build` → generátor přidává `substitute: disabled` (P21a diff odhalil).
- Sonda propagace klíče přes ClusterIP trefila jen jednu ze dvou replik gateway (ConfigMap volume se propaguje per pod); Account a Architekt
  pak dostaly 401 z druhé repliky → headless Service `agentgateway-headless`, sonda proti každé replice (propagace 36–69 s).
- Pozorováno, neprověřeno: v běhu s 401 u dvou rolí hlásil výstup zakázky `cost_usd` 1,62 USD místo ~0,02 (sčítání ceny při chybě role).


## P2-2 – obrazy rolí a pod spec z rolegen (2026-10-25, AKS, `--step p2-2` = p2-1 + P22a–c) – **10/10**

rolegen nově generuje `build/images/<role>/` (Dockerfile = vrstva nad obrazem platformy s `/etc/platform/{role,srt,managed-settings}.json`,
OCI labely role/verze/sha zdroje, bez cloud CLI; devcontainer.json) a `render_k8s.py` je zapisuje do `infra/images/roles/` (CI hlídá shodu).
`images.yml` staví `roles/<role>:<verze>` přes `az acr build --build-arg BASE_IMAGE=…/zakazka-app:p1`. `role_pod.py` staví pod ze šablony
`pod-<role>.yaml` (= `build/k8s/<role>-pod.yaml`, v ConfigMapě `rolegen-build`): RuntimeClass, non-root, SA token off, drop ALL, resources,
env a labels z definice role; aplikace doplní jen běh (jméno, Secret, env běhu, uzel, timeout, `imagePullPolicy`, registry obrazu
`registry.platform.internal` → ACR, seccomp `Localhost` → `RuntimeDefault`, protože profil na uzlu není a v Kata guestu se neaplikuje).

| Check | Tvrzení | Výsledek |
|---|---|---|
| P22a | ACR má `roles/<role>:0.1.0` pro každou roli – důkaz z podů (obraz stažen, pod doběhl); `az acr repository show-tags` z runneru stále bez AAD data-plane auth i po přidání AcrPull (propagace role / token exchange), záložní důkaz stačí | ✅ (pods) |
| P22b | Pod role ze šablony rolegen; doplňky aplikace jen z povolené množiny (registry obrazu, seccomp Localhost → RuntimeDefault, runAsGroup/fsGroup, env běhu, command, envFrom, imagePullPolicy, volumes, uzel, timeout); obraz `roles/<role>:0.1.0`; `/etc/platform/role.json` v obrazu nese tutéž roli/verzi, managed settings zapečené | ✅ |
| P22c | Obsah obrazu (sonda z podu): git, node, python3, srt, bwrap, claude ano; az, gcloud, aws, kubectl, docker, helm, terraform ne | ✅ |
| P21a–h | regrese P2-1 (konfigurace z Gitu, klíče od aplikace – propagace 63 s, zakázka Dokonceno, izolace, egress, paměť, FinOps) | ✅ |

Výsledek: **10/10 + 2 INFO** (`measure` run 40200765801, `results/p2-2-20261025-141907.json`). Časy: první role 139 s (scale-up uzlu 87 s + pull
obrazu role a boot VM 114 s), další role 24–27 s (obraz role na uzlu, start podu 2–3 s). Resources podu z definice role (2 CPU, 4 Gi).


## P2-5 – eval gate a registr agentů (2026-10-25, AKS, `--step p2-5` = p2-2 + P25a–c) – **13/13**

Evaly rolí ([`tools/role_evals`](../role_evals/README.md)) běží v CI (`rolegen.yml`) nad adversariálním mockem; výsledek `results/eval-status.json`
jde přes `render_k8s.py` do ConfigMapy `rolegen-build` a aplikace roli bez `passed` nespustí (`role_gate`, ledger `ROLE_GATE`). Harness po
zakázce naplní registr v DB `org` na Flexible Serveru (`registry.py`: `org.role_definitions` ze YAML rolí + gate, `org.eval_gates` z výsledků
evalů, `org.agents` z ledgeru – SPIFFE ID instance role, model, klíč gateway, sandbox profil, obraz, uzel) a spustí negativní kontrolu gate.

| Check | Tvrzení | Výsledek |
|---|---|---|
| P25a | `eval-status.json` v Gitu == ConfigMap v clusteru; role zakázky `passed`, aplikace to ověřila před každým během (`ROLE_GATE passed=true`, vrstvy L0–L3); SRE `unevaluated` (aplikace by ji odmítla) | ✅ |
| P25b | registr v DB `org`: `role_definitions` 5 řádků (4 active, sre proposed), `eval_gates` 15 řádků (vrstva × role z CI evalů), `agents` 4 instance zakázky (SPIFFE ID, model, klíč gateway, sandbox profil `dev-kata-srt`, obraz `roles/<role>:0.1.0`) | ✅ |
| P25c | negativní kontrola na runneru: Vývojář L3 bez PEP → `pass_k` 0,5 < 1,0, gate failed | ✅ |
| P21a–h, P22a–c | regrese P2-1 a P2-2 | ✅ |

Výsledek: **13/13 + 2 INFO** (`measure` run 40206756683, `results/p2-5-20261025-153648.json`).


## P2-3 – identita role a tajemství bez operátora (2026-10-25, AKS, `--step p2-3` = p2-5 + P23a–d)

- **OpenBao auto-unseal**: `seal "azurekeyvault"` (Key Vault `kv-platform-dev-<suffix>`, klíč `openbao-unseal`, Terraform `keyvault.tf`), pod se
  přihlašuje workload identitou (UAMI `id-openbao-<suffix>` + federated credential na SA `platform-data:openbao`, webhook injektuje token;
  `VAULT_AZUREKEYVAULT_AUTH_METHOD=workload_identity`). Harness: init s recovery klíči do Secretu `openbao-init`, migrace shamir → auto-unseal
  (`unseal` s `migrate`), po smazání podu musí naběhnout unsealed sám.
- **Auth kubernetes**: OpenBao `auth/kubernetes` (TokenReview vlastním SA tokenem, ClusterRoleBinding `system:auth-delegator`), role `zakazka`
  → policy `approval-signer`; aplikace se přihlašuje projektovaným SA tokenem (`app.bao_token`, ledger `BAO_LOGIN`); `zakazka-secrets` bez `P0_BAO_TOKEN`.
- **SVID podu role na Katě**: hostPath socket DaemonSet agenta do VM nevede → **SPIRE agent jako sidecar podu** (nativní initContainer), atestace
  `k8s_psat` projektovaným tokenem SA `role` (jen v sidecaru; kontejner role token nemá), server má alias uzlu per role
  (`k8s_psat:agent_ns/agent_sa/agent_pod_label:platform.role`) a workload entry `spiffe://platform/role/<role>/acme` přes `unix:uid:1000`
  (sdílený PID ns) – entries generuje rolegen (`spire-entries.json` v `rolegen-build`), aplikuje harness. Role si v `role_runner.py` vezme
  X.509-SVID a JWT-SVID (aud `memory`, py-spiffe) a volá paměť s ním; server paměti ověřuje JWT-SVID přes `spire-oidc` (OIDC discovery provider
  jako sidecar spire-server, JWKS `/keys`), tenant z cesty SPIFFE ID. Keycloak token zůstává záloha (`P0_ROLE_IDENTITY=svid` v overlay aks).
  Socket Workload API i data agenta jsou emptyDir `medium: Memory` (tmpfs v guestu) – na emptyDir přes virtiofs se workload na unix socket nepřipojí.

| Check | Tvrzení | Výsledek |
|---|---|---|
| P23a | seal `azurekeyvault`, recovery seal; po `delete pod openbao-0` unsealed bez operátora | ✅ `seal_type=azurekeyvault recovery_seal=true`, unsealed 38 s po smazání podu (init kontejner stáhne KMS plugin, pak start), OpenBao 2.7.1 |
| P23b | `BAO_LOGIN method=kubernetes role=zakazka policies=[approval-signer]`, podpisy `openbao-transit`, Secret bez `P0_BAO_TOKEN` | ✅ login SA `zakazka` → policies `[approval-signer, default]`, TTL 3600 s; 4 podpisy transitem; `zakazka-secrets` = `P0_API_KEY`, `P0_ROLE_CLIENT_SECRETS`, `BRIDGE_WEBHOOK_SECRET` |
| P23c | 4 role: `identity.kind=svid`, `spiffe://platform/role/<role>/acme`, iss `spire-oidc`, sidecar přítomen; paměť 200 | ✅ všechny 4 role JWT-SVID i X.509-SVID vlastní role (aud `memory`, exp 1800 s), SVID k dispozici 0,5–5 s po startu role, 4 volání paměti 200 s JWT-SVID; sidecar `Completed` 0 restartů |
| P23d | `spire-oidc` `/keys` + discovery; entries z rolegen v serveru | ✅ JWKS 1 klíč, discovery 200, 10 entries (5 aliasů + 5 workloadů z rolegen) |

Výsledek: **17/17 + 2 INFO** (`measure` run 40234528827, `results/p2-3-20261025-213412.json`; 10 běhů – pasti v `infra/README.md`).
Časy podů rolí se sidecarem: start 2–15 s, běh 11–17 s (shodně s P2-2); útrata 4 rolí 0,051 USD (mock upstream).

Co měření P23c ukázalo (běhy 8–10, 2026-10-25):
- **Agent ID `k8s_psat` je UID uzlu**, ne podu: sidecary postupných podů rolí na tomtéž uzlu Kata se re-atestují pod jedním agent ID
  (`CanReattest: true`). Server tak má pro agenta vždy selektory *posledního* sidecaru a prvních ~5 s (cache entries serveru) vydá
  předchozí entry – Architekt dostal `spiffe://platform/role/account/acme`. `role_runner.py` proto čeká na SVID vlastní role (`stale_svids`
  v identitě). **Omezení:** dva pody rolí na jednom uzlu Kata současně by se přetahovaly → v P3 agent identita per pod (join token s
  `-spiffeID` aliasu, vydávaný aplikací, nebo vlastní attestor), ne `k8s_psat`.
- Sidecar se atestuje za < 1 s, SVID role má do 5 s; start podu role se sidecarem 2–15 s (shodně s P2-2).

## P2-4 – egress naostro (2026-10-26, AKS, `--step p2-4` = p2-3 + P24a–d)

- **Gateway z Gitu:** rolegen (`egress()`) generuje do `agentgateway-config` CONNECT bind 3128, virtuální gateway `secure` (443) s HTTPS
  listenery pro `*.platform.internal` z `egress_allow` rolí (terminace TLS certem gateway) a passthrough `public-egress` jen pro SNI v allow-listu;
  routa `git-acme` = sjednocení metod z `authz.http` rolí (GET/POST na `/acme/`) + `backendAuth` (Bearer token ze souboru – pod ho nemá),
  `mirror-acme` jen GET. Backendy přes env gateway (`GIT_BACKEND_HOST` = mock GitHub, `MIRROR_BACKEND_HOST` = mock mirror; ostrý provoz GitHub/Nexus).
- **Tajemství mimo Git:** harness vydá dev CA + cert (Secret `agentgateway-tls`), token git backendu (Secret `agentgateway-git-token`) a CA pro
  pody rolí (ConfigMap `platform-ca` v `platform-data` i `platform-roles`) – před čekáním na Flux, protože gateway bez certu nenastartuje. P3: cert-manager + ESO.
- **Pod role:** CA z ConfigMapy (`SSL_CERT_FILE`, `GIT_SSL_CAINFO`, `PIP_CERT`, `NODE_EXTRA_CA_CERTS`, `npm_config_cafile`), srt `parentProxy`
  = `agentgateway.platform-data.svc:3128` (oprava ns v `roles/*.yaml`). Sonda `role_runner.git_mirror_probe` (přes srt jako `sandboxed_bash`,
  záloha přímo přes proxy): clone, commit, push `agent/<wf>/ukol-1`, push `main`, pip download + npm pack z mirroru, cizí SNI, HTTP :80, cizí repo.
- **Git backend:** mock GitHub obsluhuje smart HTTP (`git http-backend`, bare repo `acme/platform.git`) s pre-receive hookem: jen `agent/*` a
  `zakazka/*` – main/release odmítá **server** (jako branch protection GitHubu). Gateway ref nevidí (pkt-line v těle), rozhoduje jen path/metoda.
- **Gateway egress:** NetworkPolicy `agentgateway-egress` (ne IMDS 169.254.0.0/16, wireserver 168.63.129.16, privátní sítě) – 1.6.0 loopback/link-local u dynamic backendu nekontroluje.

| Check | Tvrzení | Výsledek |
|---|---|---|
| P24a | config gateway z Gitu: bind 3128 CONNECT, listenery git/mirror HTTPS + public-egress TLS, routa git s backendAuth a GET+POST, mirror GET; Service 3128; NetworkPolicy; repliky Ready | ✅ listenery `git`/`mirror` HTTPS + `public-egress` TLS, routy `git-acme` (GET∥POST, backendAuth), `mirror-acme`; Service 3128/4100; 2/2 Ready |
| P24b | Vývojář z podu: clone 0, push větve 0, push main odmítnut hookem, žádný token v env; backend viděl Bearer token gateway na všech requestech | ✅ clone/commit/push `agent/<wf>/vyvojar` 0; push `main` → `! [remote rejected] … (pre-receive hook declined)`; `token_env=0`; všechny git requesty na backendu s `Bearer` = token gateway (otisk sha256) |
| P24c | pip download a npm pack z mirroru přes gateway; mirror viděl oba klienty | ✅ `platform_hello-0.1.0-py3-none-any.whl`, `platform-hello-0.1.0.tgz`; mirror viděl `/pypi/simple/…`, `/pypi/files/…`, `/npm/…` |
| P24d | cizí SNI neprojde, HTTP :80 ven neexistuje, cizí repo 404, přímý internet timeout, SNI v logu gateway | ✅ `evil.example.com` → curl 35 (TLS EOF, route not found), `http://` přes proxy → 405, `/other/repo.git` → 404, 1.1.1.1:443 timeout; log gateway `sni` git 46×, mirror 24×, evil 4× |

Výsledek: **21/21 + 2 INFO** (`measure` run 40307712561, `results/p2-4-20261026-105130.json`; 7 běhů – pasti v `infra/README.md`).
Sonda běžela **přímo přes proxy gateway (`via: direct`)**, ne přes srt: po doplnění `ripgrep` srt poprvé opravdu startuje a vynucuje
`filesystem.allowWrite ["/work"]`; emptyDir `/work` v Kata guestu ale nebyl pro uid 1000 zapisovatelný (`os.access` false → runner padl zpět na
`/tmp/p0-o2/<id>/work`, kde srt zápis odmítl). Hranice egressu tak drží gateway + NetworkPolicy (změřeno), vrstva srt nad tím zatím ne –
**otevřeno pro další krok** (runner od tohoto commitu loguje `work_info`: vlastník, mód a `w_ok` `/work`). Dopad i mimo sondu: `sandboxed_bash`
role pod srt dnes nemůže zapisovat do pracovního adresáře (mock tok to nepotřeboval; živý Vývojář ano).

## P2-6 – FinOps naostro (2026-10-26, AKS, `--step p2-6` = p2-4 + P26a–c, P24b přes srt)

- **Strop zakázky**: `POST /zakazky` nese `budget_usd` (výchozí `P0_ZAKAZKA_BUDGET_USD`); před každou rolí aktivita `budget_gate` sečte 30d útratu
  klíčů zakázky z `budget_usage` (gateway, Flexible Server; `finops.spend`, hashe z ConfigMapy `agentgateway-keys`) → `>= strop` = `BUDGET_EXCEEDED`
  zdroj `zakazka-sum` → eskalace HITL `rozpocet`, timeout → Pozastaveno. Gateway dál hlídá klíč (24h/30d Block); čítače flushuje periodicky
  (eventually consistent – gate může zareagovat o roli později).
- **Cena zakázky**: `budget_check` ze stejného zdroje (ledger `BUDGET source=budget_usage`), registr `org.zakazky` (`finops.registry_upsert`,
  DSN `P0_REGISTRY_DSN`): budget, spent, by_role, status, keys_source, key_hashes.
- **Klíče z OpenBao**: `gateway_keys.issue` při `P0_BAO_KV`: entropie `sys/tools/random`, hodnoty v KV v2 `secret/zakazky/<id>/gateway-keys`
  (policy `approval-signer` rozšířena jen o `secret/data|metadata/zakazky/*` a `sys/tools/random/*`), žádný Secret `zakazka-keys-<id>`.
- **Uzavření P2-4**: `/work` role = emptyDir `medium: Memory` (tmpfs v guestu); P24b nově vyžaduje `via: srt`.

| Check | Tvrzení | Výsledek |
|---|---|---|
| P26a | klíče v OpenBao KV (4 role), hash == ConfigMap, Secret `zakazka-keys-<id>` neexistuje, ledger `keys_source=openbao`, entropie openbao | ✅ KV `secret/data/zakazky/<id>/gateway-keys` 5 rolí (vč. SRE), hashe == ConfigMap, Secret chybí, `entropy=[openbao]` |
| P26b | `BUDGET source=budget_usage window=30d`, spent == nezávislý součet harnessu z DB, `org.zakazky` řádek (Dokonceno, openbao, budget_usage, 4 hashe) | ✅ spent 0,051264 USD (account 0,015078; architekt/vyvojar/reviewer 0,012062; SRE 0) == součet z DB 0,051265; registr: budget 20, status Dokonceno, keys_source openbao |
| P26c | zakázka `budget_usd=0.01`: po první roli gate → `BUDGET_EXCEEDED zakazka-sum`, HITL timeout → Pozastaveno/rozpocet, registr `BudgetExceeded` | ✅ gate před Architektem: 0,015078 ≥ 0,01 → BudgetExceeded (zakazka-sum), HITL `rozpocet` timeout 25 s → `Pozastaveno/rozpocet/architekt`; registr `BudgetExceeded`, spent 0,015078 |
| P24b přes srt | sonda egressu přes srt (`via: srt`), ne přímo | ✅ `/work` tmpfs (uid 0, gid 1000, 3777, zapisovatelný), srt parentProxy → gateway: clone/push větve/push main odmítnut, pip i npm z mirroru – 6,2 s; cizí host srt odmítne `CONNECT 403` |

Výsledek: **24/24 + 2 INFO** (`measure` run 40340791174, `results/p2-6-20261026-145722.json`; 4 běhy – nálezy srt na Katě v `infra/README.md`:
emptyDir přes virtiofs nezapisovatelný → Memory medium, cache npm/pip pod `/work`, `~/.gitconfig` pod mandatory deny → `GIT_CONFIG_GLOBAL=/dev/null`).
Útrata zakázky 0,051 USD (mock upstream), strop 0,01 USD zastaví zakázku po první roli; gate reaguje na flush čítačů gateway (řádově sekundy).

## Spuštění

```bash
cd tools/harness_p1_k8s
export KUBECTL=… KIND=… OPA_BIN=… AGENTGATEWAY_BIN=…        # + venvy harnessů M1 a O1 (jejich README)
../harness_p0_o2/.venv/bin/python harness.py --step p1-2                 # proti běžícímu kind clusteru `platform`
../harness_p0_o2/.venv/bin/python harness.py --step p1-2 --create-kind   # + postaví obraz uzlu, cluster a nahraje obrazy (docker)
DAPR_BIN_DIR=… ../harness_p0_o2/.venv/bin/python harness.py --step p1-3  # identita: vyžaduje lokálně postavené obrazy (infra/images) nahrané do kind
../harness_p0_o2/.venv/bin/python harness.py --step p1-4                 # gateway: docker (bridge IP), venv G1, obraz platform/agentgateway v kind
../harness_p0_o2/.venv/bin/python -u harness.py --step p1-5              # workflow v clusteru: obrazy platform/{zakazka-app,dapr,opa}, po p1-3 (logs/openbao-init.json); ~5 min
python harness.py --step p2-3 --context aks-platform-dev-admin --acr acrplatformdev<suffix>.azurecr.io   # AKS: workflow measure (e2e=p2-3); p2-5 bez identity, p2-2 bez registru, p2-1 bez obrazů rolí; pip httpx pyyaml psycopg PyJWT fastapi opentelemetry-sdk; p1-6 = alias
```

Pasti prostředí (cgroup v1, chybějící `CAP_SYS_RESOURCE`, proxy uzlu): [`infra/README.md`](../../infra/README.md).

## Další kroky

Na kind je hotovo P1-2 až P1-5. Zbývá P1-1 (AKS cluster + Kata node pool) a P1-6 (role jako Kata pody z rolegen, srt uvnitř, egress CONNECT
gateway, SPIRE entries z rolegen) – obojí na AKS z Adamova Macu.

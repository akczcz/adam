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

## Spuštění

```bash
cd tools/harness_p1_k8s
export KUBECTL=… KIND=… OPA_BIN=… AGENTGATEWAY_BIN=…        # + venvy harnessů M1 a O1 (jejich README)
../harness_p0_o2/.venv/bin/python harness.py --step p1-2                 # proti běžícímu kind clusteru `platform`
../harness_p0_o2/.venv/bin/python harness.py --step p1-2 --create-kind   # + postaví obraz uzlu, cluster a nahraje obrazy (docker)
DAPR_BIN_DIR=… ../harness_p0_o2/.venv/bin/python harness.py --step p1-3  # identita: vyžaduje lokálně postavené obrazy (infra/images) nahrané do kind
../harness_p0_o2/.venv/bin/python harness.py --step p1-4                 # gateway: docker (bridge IP), venv G1, obraz platform/agentgateway v kind
../harness_p0_o2/.venv/bin/python -u harness.py --step p1-5              # workflow v clusteru: obrazy platform/{zakazka-app,dapr,opa}, po p1-3 (logs/openbao-init.json); ~5 min
python harness.py --step p1-6 --context aks-platform-dev-admin --acr acrplatformdev<suffix>.azurecr.io   # AKS: spouští workflow measure (p16=true); pip httpx pyyaml psycopg PyJWT fastapi opentelemetry-sdk
```

Pasti prostředí (cgroup v1, chybějící `CAP_SYS_RESOURCE`, proxy uzlu): [`infra/README.md`](../../infra/README.md).

## Další kroky

Na kind je hotovo P1-2 až P1-5. Zbývá P1-1 (AKS cluster + Kata node pool) a P1-6 (role jako Kata pody z rolegen, srt uvnitř, egress CONNECT
gateway, SPIRE entries z rolegen) – obojí na AKS z Adamova Macu.

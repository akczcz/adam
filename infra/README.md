# infra – platforma v Kubernetes (P1)

Manifesty a konfigurace clusteru pro fázi P1 ([plán](../knowledge/platforma/p1-aks.md), [stav](../knowledge/platforma/produkt.md)).
Zásada P1: **stejné harnessy jako v P0, jen proti clusteru.** Nejdřív lokální `kind`, pak AKS.

```
infra/
├── kind/                 # lokální cluster: kind-platform.yaml (NodePorty), node-image/ (obraz uzlu s runc obalem)
└── k8s/
    ├── base/             # komponenty bez prostředí: postgres (pgvector, 4 DB), clickhouse, otel-collector
    └── overlays/kind/    # namespace platform-data + NodePort služby (30432, 30123/30900, 30317/30318)
```

Konfigurace komponent jsou odvozené z harnessů P0 (zdroj pravdy zůstává tam): Collector z `tools/harness_observability_o1/configs/otelcol.yaml`
(místo file exportérů jdou metriky a logy do ClickHouse), ClickHouse z `clickhouse-config.xml`, schéma paměti z `tools/harness_memory_m1`
(vytváří ho harness M1 při běhu, ne manifest).

## P1-2 datová vrstva na kind (2026-10-24)

```bash
# nástroje: kubectl, kind (GitHub releases), docker daemon; helm jde postavit z Go (`go install helm.sh/helm/v3/cmd/helm@v3.19.0`), get.helm.sh bývá blokováno
docker build -t kindest/node:v1.37.0-noom infra/kind/node-image
kind create cluster --config infra/kind/kind-platform.yaml --wait 180s
docker pull pgvector/pgvector:pg16 clickhouse:26.8 otel/opentelemetry-collector-contrib:0.163.2   # uzel kind nemá proxy → obrazy přes host
kind load docker-image --name platform pgvector/pgvector:pg16 clickhouse:26.8 otel/opentelemetry-collector-contrib:0.163.2
kubectl apply -k infra/k8s/overlays/kind
# měření: tools/harness_p1_k8s (P12a–g: aplikace, Postgres/ClickHouse/Collector přes NodePort, M1 --db-uri, O1 --external)
```

Výsledek 2026-10-24: `tools/harness_p1_k8s/results/p1-2-*.json` **6/6 PASS + 1 INFO** – M1 11/11 proti clusterovému Postgresu
(16.15, pgvector 0.8.7), O1 9/9 proti clusterovému Collectoru a ClickHouse 26.8.34.13 (stejná verze jako lokální O1).

## P1-3 identita na kind (2026-10-24)

`infra/k8s/base/{keycloak,openbao,spire}`: Keycloak 26.8.1 (`start --optimized --import-realm`, realm `p0` z ConfigMapy, DB `keycloak`
v clusterovém Postgresu), OpenBao 2.7.1 (StatefulSet, raft, audit device deklarativně do stdout, init/unseal operátorem – harness),
SPIRE 1.14.2 (server se sqlite datastore, agent DaemonSet s `k8s_psat` + `k8s` workload attestorem, trust domain `platform`).

Obrazy pro kind se stavějí lokálně (quay.io, ghcr.io a api.adoptium.net nejsou z prostředí dostupné, Docker Hub má rate limit):
`platform/keycloak:26.8.1` = Debian základ (`pgvector/pgvector:pg16`, už lokálně) + Temurin JRE 21 z GitHub releases + Keycloak dist
z GitHub releases s `kc.sh build --db=postgres`; `platform/openbao:2.7.1` a `platform/spire:1.14.2` = busybox + statické binárky
z GitHub releases. Dockerfiles: `infra/images/`. Na AKS se použijí oficiální obrazy (`quay.io/keycloak/keycloak`, `ghcr.io/openbao/openbao`,
`ghcr.io/spiffe/spire-{server,agent}`).

Výsledek: `tools/harness_p1_k8s/results/p1-3-*.json` – Keycloak tokeny rolí (RS256, tenant_id, agent_id, aud) z clusteru, OpenBao raft
init/unseal + transit, SPIRE SVID `spiffe://platform/role/vyvojar` pro pod s labelem `role=vyvojar` (pod bez labelu „no identity issued“),
O-2 `identity` 5/5 proti clusterovému Keycloaku a OpenBao.

## P1-4 model gateway na kind (2026-10-24)

`infra/k8s/base/agentgateway`: agentgateway 1.6.0, 2 repliky, LLM listener 4100, `config.database` z env `$AGW_DATABASE_URL` (Secret),
logging CEL pole `role`/`zakazka`. ConfigMapu s `policies.apiKey` (klíče a rozpočty z rolegen) a upstreamem renderuje harness P1-4
(`tools/harness_p1_k8s`), v cíli CI job rolegen. Obraz `platform/agentgateway:1.6.0` = busybox + statická binárka (`infra/images/agentgateway`).
Výsledek 6/6: G1 21/21 proti clusteru; P1-G: rozpočty mezi replikami aditivní v Postgresu, vynucení eventually consistent (flush 5 s) – viz README harnessu.

## P1-5 workflow, paměť a bridge na kind (2026-10-24)

`infra/k8s/base/{opa,dapr,zakazka}`: OPA s policies z ConfigMapy (subPath), Dapr placement + scheduler (StatefulSety ze statických
binárek, bez operátoru/injectoru/sentry – na AKS Helm chart), aplikace zakázky s daprd sidecarem (`state.postgresql` z ConfigMapy, PVC pro
ledger), server paměti, mock GitHub a bridge – jeden obraz `platform/zakazka-app` (`infra/images/app`). Secret `zakazka-secrets` má v base
placeholdery; token OpenBao, klíče gateway a rolegen build (ConfigMap `rolegen-build`) dodává harness P1-5 (v cíli CI z rolegen + OpenBao).
Výsledek 6/6: zakázka end-to-end v clusteru přes GitHub HITL, durabilita přes smazání podu, paměť, FinOps z Postgresu, bridge jako PEP.

## P1-1 AKS: Terraform + GitHub Actions (OIDC) + Flux (připraveno 2026-10-24)

`infra/bootstrap/azure-oidc.sh` (1× na Macu: RG, tfstate, identita Actions s OIDC federací, role jen na RG) → `infra/terraform/` (ACR, AKS Azure Linux +
Cilium, Kata pool D2ads_v7 autoscale 0–1, Flexible Server PG 16 B1ms s DB a `vector`, Flux extension + konfigurace na `infra/k8s/overlays/aks`) →
`.github/workflows/{infra,images,measure,cluster}.yml`. Overlay `aks` používá Flux proměnné `${ACR_LOGIN_SERVER}`, `${PG_HOST}`, `${PG_PASSWORD}`.
Podrobnosti, postup a bezpečnostní model: [`infra/bootstrap/README.md`](bootstrap/README.md). Měření P1-1 = workflow `measure` (S1 na Katě).

## P1-6 AKS: role jako Kata pody (2026-10-25)

`infra/k8s/roles/` (vlastní Flux kustomization `roles`, bez namespace transformeru overlay): ns `platform-roles` (PSS restricted), NetworkPolicy
default-deny + egress jen DNS/agentgateway/paměť/aplikace, Role + RoleBinding pro SA `zakazka` (pods, pods/log, secrets). Overlay `aks`: `zakazka-env`
`P0_ROLE_RUNTIME=pod`, `P0_ROLE_IMAGE`, `P0_ARTIFACT_API` (FQDN služeb pro pod z jiného ns), `infra/k8s/base/mock-upstream` (mock Anthropic API v clusteru
jako upstream gateway pro měření), `zakazka-secrets` a `agentgateway-keys` s `kustomize.toolkit.fluxcd.io/ssa: IfNotPresent` (Flux založí, harness/aplikace
přepisuje), `imagePullPolicy: Always` pro pohyblivý tag `zakazka-app:p1`, `fsGroup: 1000` na podu aplikace. Obraz `zakazka-app` má bubblewrap +
`@anthropic-ai/sandbox-runtime` (srt weaker režim v Kata podu). Měření: workflow `measure` s `p21=true` → `tools/harness_p1_k8s --step p2-1` (p1-6 = alias)
(výsledek a pasti v jeho README).

## P2-1: role → Git → Flux (2026-10-25)

`infra/k8s/rolegen/` je **generovaný** kustomize component (`tools/rolegen/render_k8s.py`, CI `rolegen.yml` s `--check`): ConfigMap `rolegen-build`
(ClaudeAgentOptions, srt settings, registr, OPA data, šablona klíčů gateway s rozpočty per role a placeholderem `{zakazka}`) a patch
`agentgateway-config` (base config + `baseUrl: $LLM_UPSTREAM_URL` + prázdná apiKey policy). Upstream modelu nastavuje overlay env proměnnou
gateway (`aks`: mock-upstream v clusteru; živé API = změna v Gitu). Klíče role × zakázka: ConfigMap `agentgateway-keys` vlastní aplikace
zakázky (`gateway_keys.py`, RBAC jen na tento objekt + Secrety), Flux ji jen založí (`ssa: IfNotPresent`); sidecar `config-merge`
(`gateway_merge.py`) slévá obě ConfigMapy do emptyDir, gateway hot-reloaduje. Harness/CI tak do clusteru nenosí žádnou konfiguraci – jen tajemství.

## Pasti (AKS + Flux)
- ConfigMap volume se do replik propaguje nezávisle (kubelet sync per pod): po zápisu klíčů do `agentgateway-keys` ověřovat každou repliku
  (headless Service), ne ClusterIP – jinak část requestů 401 (P21b 2026-10-25). Propagace + merge + hot reload: 36–69 s.
- Každý generovaný objekt s cizími `${…}` (env rolí) potřebuje `kustomize.toolkit.fluxcd.io/substitute: disabled`, jinak Flux proměnné smaže.
- `kubectl rollout restart` se hádá s Fluxem: SSA vrátí anotaci `restartedAt` a Deployment se přerolluje zpět (pod aplikace zemřel uprostřed běhu role).
  Restart = smazat pody (šablona beze změny), nebo změnit manifest v Gitu.
- PVC na Azure Disku je root:root → kontejner s uid 1000 potřebuje `fsGroup`; kind `local-path` (0777) to skryl.
- Pohyblivý tag (`p1`) bez `imagePullPolicy: Always` → uzel drží starý obraz po `az acr build`.
- Objekty, které za běhu přepisuje harness/rolegen, musí mít `kustomize.toolkit.fluxcd.io/ssa: IfNotPresent` (ne `reconcile: disabled` – ten by je na
  čerstvém clusteru vůbec nezaložil).
- Smazání Kata podu je asynchronní (VM se vypíná, desítky sekund); pod zabité aplikace zůstane jako sirotek → GC v `role_pod.py`.
- Flexible Server je z runneru GitHub Actions dosažitelný přímo (pravidlo „Allow Azure services“ 0.0.0.0) – pro schéma paměti a FinOps dotazy; záloha socat pod.

## Pasti (kind v cloudovém kontejneru)
- ConfigMap mount celého adresáře přidá `..data`/`..<ts>` symlinky: OPA načte pravidla dvakrát (`multiple default rules`), daprd varuje.
  Mountovat `subPath` per soubor.
- `kubectl apply -k` po ručních úpravách ConfigMap/Secret je přepíše (base má placeholdery); agentgateway config hot-reloaduje → upstream se
  vrátil na api.anthropic.com a requesty padaly na TLS. Vždy: apply base → render hodnot → rollout.
- Mock GitHub po restartu čísluje od 1, ledger aplikace na PVC přežívá → mapování číslo→zakázka v bridge musí brát nejnovější záznam.
- Dapr odmítne `schedule_new_workflow` se stejným instance id, pokud instance existuje (stav v Postgresu přežívá) – ids zakázek unikátní.
- Řádek `strategy: Recreate` u aplikace: jediný app-id s actor placementem; stav je v Postgresu, nový pod instanci obnoví (P15c).
- Dvě repliky agentgateway proti prázdné DB migrují současně → jedna spadne na `duplicate key … pg_type_typname_nsp_index` a restartuje se (jen při prvním nasazení).
- Měření přes NodePort: klient s keep-alive drží jeden pod; pro střídání replik `Connection: close`. Po rolloutu chvíli trvá, než kube-proxy přeprogramuje endpointy (první SYN může vyhasnout) – warm-up.

- **cgroup v1 na hostiteli**: kubelet v K8s 1.37 odmítne start (`failCgroupV1: true`) → kubeadm patch `KubeletConfiguration.failCgroupV1: false`.
  Na AKS (Azure Linux, cgroup v2) netřeba.
- **Bez `CAP_SYS_RESOURCE`** runc nemůže nastavit záporný `oom_score_adj` systémových podů (`failed to update /proc/self/oom_score_adj:
  Permission denied`) → vlastní obraz uzlu s obalem `runc-noom`, který `process.oomScoreAdj` z OCI specu odstraní
  (`containerdConfigPatches` → `BinaryName`). Jen pro tento harness; nikdy do produkce.
- Uzel kind nemá proxy hostitele: obrazy stáhnout `docker pull` a `kind load`, jinak `ErrImagePull`.
- Collector s `clickhouse` exporterem a `create_schema: true` padá, dokud ClickHouse neběží (restarty před Ready jsou očekávané);
  readiness přes extension `health_check` (13133).
- Oficiální obraz ClickHouse je `clickhouse:<verze>`; `clickhouse/clickhouse-server` nemá tag 26.8.
- StatefulSet s podem v `ErrImagePull` se po změně obrazu sám nepřeplánuje – pod smazat.
- Docker daemon v kontejneru: `dockerd --data-root <scratch> --storage-driver overlay2` běží i na cgroup v1 (deprecated warning);
  jednou spadl na buildkit healthchecku – po restartu daemonu uzel kind naběhl a pody se obnovily.
- SPIRE agent při prvním startu spadne na chybějícím `bundle.crt` (Notifier `k8sbundle` ho zapíše až po startu serveru) – DaemonSet ho restartuje, pak atestace projde.
- Keycloak `--optimized` vyžaduje `kc.sh build` s `--db=postgres` v obrazu; `--import-realm` je runtime volba a funguje i s `--optimized`.
- OpenBao readiness s `sealedcode=204&uninitcode=204`, jinak Service nemá endpointy a operátor nemůže init/unseal provést.
- `kubectl logs -f` jako zdroj audit záznamů OpenBao (audit device do stdout) stačí pro harness; v clusteru je sbírá Collector.

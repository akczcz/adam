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
SPIRE 1.15.5 (server se sqlite datastore, agent DaemonSet s `k8s_psat` + `k8s` workload attestorem, trust domain `platform`; od P3-6 E5 agent ID per pod – `use_pod_uid_for_agent_id`, `agent_ttl` 1h, prune).

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
jako upstream gateway pro měření), `agentgateway-keys` s `kustomize.toolkit.fluxcd.io/ssa: IfNotPresent` (Flux založí, aplikace
přepisuje; `zakazka-secrets` od P3-6 E1 z ESO), `imagePullPolicy: Always` pro pohyblivý tag `zakazka-app:p1`, `fsGroup: 1000` na podu aplikace. Obraz `zakazka-app` má bubblewrap +
`@anthropic-ai/sandbox-runtime` (srt weaker režim v Kata podu). Měření: workflow `measure` s `p21=true` → `tools/harness_p1_k8s --step p2-1` (p1-6 = alias)
(výsledek a pasti v jeho README).

## P2-1: role → Git → Flux (2026-10-25)

`infra/k8s/rolegen/` je **generovaný** kustomize component (`tools/rolegen/render_k8s.py`, CI `rolegen.yml` s `--check`): ConfigMap `rolegen-build`
(ClaudeAgentOptions, srt settings, registr, OPA data, šablona klíčů gateway s rozpočty per role a placeholderem `{zakazka}`) a patch
`agentgateway-config` (base config + `baseUrl: $LLM_UPSTREAM_URL` + prázdná apiKey policy). Upstream modelu nastavuje overlay env proměnnou
gateway (`aks`: mock-upstream v clusteru; živé API = změna v Gitu). Klíče role × zakázka: ConfigMap `agentgateway-keys` vlastní aplikace
zakázky (`gateway_keys.py`, RBAC jen na tento objekt + Secrety), Flux ji jen založí (`ssa: IfNotPresent`); sidecar `config-merge`
(`gateway_merge.py`) slévá obě ConfigMapy do emptyDir, gateway hot-reloaduje. Harness/CI tak do clusteru nenosí žádnou konfiguraci – jen tajemství.

## P2-2: obrazy rolí a pod spec z rolegen (2026-10-25)

`infra/images/roles/<role>/` je **generovaný** (`tools/rolegen/render_k8s.py`, CI `rolegen.yml --check`): Dockerfile vrstvy nad `zakazka-app:p1`
(`/etc/platform/{role,srt,managed-settings}.json`, `/etc/claude/managed-settings.json`, OCI labely role/verze/sha, odstraněné cloud CLI),
devcontainer.json. `images.yml` staví `roles/<role>:<verze>` (`az acr build --build-arg BASE_IMAGE`). Pod role staví aplikace ze šablony
`pod-<role>.yaml` z ConfigMapy `rolegen-build` (overlay aks: `P0_ROLE_IMAGE_REGISTRY=${ACR_LOGIN_SERVER}` přepíše `registry.platform.internal`).

## P2-5: eval gate v Gitu (2026-10-25)

`tools/role_evals/results/eval-status.json` (CI `rolegen.yml`: evaly rolí L0–L3 nad adversariálním mockem, gate z definice role) jde přes
`render_k8s.py` do ConfigMapy `rolegen-build`; aplikace zakázky roli bez `passed` nespustí (`P0_ROLE_GATE=off` vypne – kind/P0). Verze role,
která propadne L3, se tak do clusteru nedostane dvakrát: CI neprojde (PR nelze mergnout) a i kdyby, aplikace ji odmítne. Registr `org.*`
(DB `org` na Flexible Serveru) plní harness `p2-5` – v cíli Dapr workflow při založení instance role (P3).

## P2-3: auto-unseal, auth kubernetes, SVID v Kata podu (2026-10-25)

`infra/terraform/keyvault.tf`: Key Vault (RBAC) + klíč `openbao-unseal`, UAMI `id-openbao` s federated credential na SA `platform-data:openbao`
(OIDC issuer AKS), role Key Vault Crypto User; identita Actions dostává Crypto Officer (klíč zakládá Terraform – data-plane role, propagace
může první apply shodit). Flux substitute `${KV_NAME}`, `${OPENBAO_CLIENT_ID}`. Overlay aks: SA `openbao` s anotací client-id, label
`azure.workload.identity/use`, config se `seal "azurekeyvault" {}` (parametry z env), `auth/kubernetes` nastavuje harness.
SPIRE: `jwt_issuer`, `allowed_pod_label_keys`, allow-list `platform-roles:role`, OIDC discovery provider jako sidecar serveru (`spire-oidc:8082`,
overlay aks), `infra/k8s/roles`: SA `role` (bez automountu), ConfigMap `spire-agent-pod` (agent per pod, `insecure_bootstrap` v dev), egress na
`spire-server:8081`. Server paměti přijímá JWT-SVID (`MEMORY_SPIRE_*`). Měření: workflow `measure` s `e2e=p2-3` – **17/17 2026-10-25**
(run 40234528827); seal `azurekeyvault` = externí KMS plugin `openbao-plugin-kms-azure` stažený init kontejnerem (viz pasti níže).

## P2-4: egress git a mirror přes gateway CONNECT (2026-10-26)

Pody rolí (Kata, `platform-roles`) ven jen přes agentgateway `:3128` (CONNECT; srt `parentProxy`). rolegen generuje do `agentgateway-config`
bind 3128, HTTPS listenery `git.platform.internal` a `mirror.platform.internal` (terminace certem ze Secretu `agentgateway-tls`), routu `git-acme`
(metody z `authz.http` rolí, `backendAuth` Bearer ze Secretu `agentgateway-git-token`) a `mirror-acme` (GET); backendy z env Deploymentu
(`GIT_BACKEND_HOST=mock-github:9801`, `MIRROR_BACKEND_HOST=mock-mirror:9803`). Secrety a ConfigMapu `platform-ca` (CA pro pody rolí) vydával
harness (dev CA) – od P3-6 E1 je vydávají cert-manager, ESO a trust-manager (sekce P3-6 E1); Deployment gateway na ně čeká (`ContainerCreating`),
Flux kustomizace `platform` je do té doby `HealthCheckFailed`. Mock GitHub nově mluví git smart HTTP (`git http-backend`, bare repo `acme/platform.git`, pre-receive hook = branch protection:
jen `agent/*`, `zakazka/*`); mock mirror (`tools/harness_p0_o2/mock_mirror.py`) = pypi simple + npm registry s balíčkem `platform-hello`.
NetworkPolicy `agentgateway-egress` (overlay aks) brání gateway v přístupu na IMDS, wireserver a privátní sítě. Měření: `measure` s `e2e=p2-4`.

## P2-6: FinOps – strop a cena zakázky ze součtu klíčů, klíče z OpenBao (2026-10-26)

Secret `zakazka-finops` (overlay aks: `P0_FINOPS_DSN` = DB `agentgateway` gateway, `P0_REGISTRY_DSN` = DB `org`, heslo z Flux substitute) dává
aplikaci čtení `budget_usage` (součet 30d útraty klíčů zakázky = cena a strop zakázky, `budget_gate` před každou rolí) a zápis `org.zakazky`.
`P0_BAO_KV=secret` (zakazka-env): hodnoty klíčů role × zakázka drží OpenBao KV v2 (`secret/zakazky/<id>/gateway-keys`), mount a policy zakládá
harness (`bao_setup`); Secret `zakazka-keys-<id>` se už nezakládá. `/work` podu role = emptyDir `medium: Memory`. Měření: `measure` s `e2e=p2-6`.

## P3-1: AG-UI server a GUI v aplikaci zakázky (2026-10-26)

Obraz `zakazka-app` má stage `gui` (`node:22-alpine`, `npm ci && vite build` z `gui/`), výsledek v `/app/gui`; aplikace ho servíruje na `/gui`
(`P0_GUI_DIR`) a AG-UI endpointy na `/agui/*` (`tools/harness_p0_o2/agui.py`). `zakazka-env`: `P0_KC_JWKS_URL`, `P0_KC_ISSUER` (ověření tokenu
člověka), `P0_GUI_CLIENT=harness-human` (login GUI password grantem – zjednodušení), `P0_TENANT=acme`. Přístup k GUI v dev clusteru jen přes
`kubectl -n platform-data port-forward svc/zakazka 18010:8010` → `http://127.0.0.1:18010/gui/` (ingress přes agentgateway s OIDC = P3-6).
Měření: `measure` s `e2e=p3-1` (runner si instaluje Playwright + Chromium; screenshoty v artifactu `measure-<run>`).

## P3-2: namespace per tenant (2026-10-26)

`infra/k8s/roles/` už nemá ruční manifesty: `tenants-generated.yaml` generuje rolegen z `knowledge/organization/tenants.yaml` (Namespace `tenant-<id>`,
NetworkPolicy, SA `role`, RBAC pro SA zakazka, ConfigMap spire-agent-pod ze `spire-agent.conf`); Flux kustomization `roles` ho aplikuje (prune není zapnuté →
starý ns `platform-roles` maže harness p3-2; nový cluster ho nemá). Base `spire.yaml` má generovaný řádek `service_account_allow_list` (ns tenantů) – StatefulSet pod SPIRE serveru nový config
nenačte sám, harness ho restartuje podle anotace `platform.config-sha`. `zakazka-env`: `P0_ROLE_NAMESPACE_TEMPLATE=tenant-{tenant}`, `P0_GUI_CLIENT=platform-gui`.
CA `platform-ca` pro pody rolí dává do každého ns tenanta trust-manager (label `platform.ca-bundle`, P3-6 E1; dřív harness). Měření: `measure` s `e2e=p3-2`.

## P3-3: Governance MCP (2026-10-26)

Deployment `governance` (obraz `zakazka-app`, `python /app/governance_mcp/governance_mcp.py`, port 9910): `GOV_DSN` = DB `org` jako `org_reader`
(jen SELECT, RLS; heslo dev – literál v DSN, zbývá i po E1), `GOV_KC_JWKS_URL/ISSUER` (token člověka). `zakazka-env`: `P0_GOV_URL`; server paměti:
`MEMORY_TENANT_STATUS_URL` (stop tenanta → deny). Role `org_reader`/`org_writer` a RLS zakládá aplikace zakázky při startu (`finops.tenants_sync`).
Měření: `measure` s `e2e=p3-3`.

## P3-4: mock kanálů k lidem, klasifikace a SLA (2026-10-27)

Deployment `mock-channels` (obraz `zakazka-app`, `python /app/harness_p0_o2/mock_channels.py`, port 9804): mock e-mailu zákazníka
(`POST /email`) a komentářů ticketu (`POST /tickets/<id>/comments`), harness čte `/_debug/messages`. `zakazka-env`: `P0_CHANNELS_URL`
(prázdné = suchý běh, jen ledger). Disclosure čl. 50(1) a `generated_by` (T8) vkládá adaptér v aplikaci (`notify_customer`), ne model;
ostrý provoz = SMTP relay / helpdesk API za gateway (CONNECT egress, P3-6). Schéma `org`: `zakazky.profile` + `klasifikace`, tabulka
`org.sla_events` (RLS per tenant jako ostatní). OPA data `zakazky/<id>` zapisuje aplikace přes `PUT /v1/data` (OPA běží bez bundle –
po restartu podu OPA data zmizí; bundle z rolegen = P3-6). Měření: `measure` s `e2e=p3-4`.

## P3-5: stop s checkpointem, spany paměti, útrata per tenant (2026-10-27)

Server paměti: `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` → spany `search_memory`/`create_memory` (`tenant.id`, `enduser.id`
= SPIFFE ID podu role, `gen_ai.memory.record.ids`, `memory.tenants_returned`) do ClickHouse `otel.otel_traces` (obraz: `opentelemetry-exporter-otlp-proto-http`).
Pod role: `role_runner` má handler SIGTERM – stop zakázky/tenanta (DELETE podu s grace 20 s) → sync-up `artifacts/` a `work/` do aplikace
(checkpoint) + výsledek `stopped`; workflow po resume roli spustí znovu od checkpointu (`ROLE_STOPPED`). `org.zakazky.spent_usd` plní workflow
po každé roli a aplikace při stop/resume. Harness čte ClickHouse přes `kubectl port-forward svc/clickhouse 8123` (uživatel default bez hesla –
dev). Měření: `measure` s `e2e=p3-5`.

## P3-6 E3: strop zakázky v gateway (2026-10-27)

Klíče role × zakázka v ConfigMapě `agentgateway-keys` nesou rozpočet `zakazka-30d-block` = strop zakázky (`gateway_keys.issue(cap_usd)`); navýšení z HITL
`rozpocet` přepíše rozpočty (`set_cap`) a sondou počká, až všechny repliky klíč pustí. Stop tenanta čeká, až blokace klíčů platí na všech replikách
(429), resume na 200 – ConfigMap se do replik propaguje nezávisle (~40–70 s).

## P3-6 E4: per-request ledger z gateway (2026-10-27)

`agentgateway.yaml` `config.tracing`: OTLP HTTP na `otel-collector:4318`, `randomSampling: "true"` (span každého requestu i bez inbound trace),
`fields.add` `tenant`/`zakazka`/`role` z metadat klíče a `llm.cost.total` → ClickHouse `otel.otel_traces`. Tracing se načítá **jen při startu**
gateway (klíče a rozpočty hot reload) – změna = restart podů (smazáním; `rollout restart` se hádá s Fluxem). Governance MCP má
`GOV_CLICKHOUSE_URL=http://clickhouse:8123` (nástroj `ledger`, hranice tenanta jako RLS). Nález: od E3 má každý klíč dva rozpočty
`*-30d-block` – útrata zakázky se počítá jen z rozpočtu role, jinak dvojnásobek (viz `tools/harness_p1_k8s/README.md`).

## P3-6 E1: cert-manager, trust-manager a ESO místo tajemství z harnessu (2026-10-28)

Flux kustomizace `operators` (`infra/k8s/operators`: HelmRelease cert-manager v1.21.3, trust-manager v0.26.0, external-secrets v2.14.0; chart repo OCI
ve stejném ns, SA `flux-helm` s cluster-admin – Flux extension vynucuje multi-tenancy; obrazy chartů z ACR přes `images.yml`) → `trust`
(`infra/k8s/trust`: self-signed root `platform-root-ca` → `ClusterIssuer platform-ca`, `Bundle platform-ca` → ConfigMap do ns s labelem
`platform.ca-bundle=true`, `ClusterSecretStore azure-kv` s Workload Identity SA `external-secrets/eso-keyvault` – anotace client-id **i tenant-id**)
→ `platform` (`overlays/aks/secrets-eso.yaml`: `Certificate agentgateway-tls`, ExternalSecrety `postgres-auth`, `agentgateway-secrets`,
`zakazka-finops`, `zakazka-secrets`, `agentgateway-git-token`, `dapr-components`; base Secrety a ConfigMap Dapr komponent z overlaye smazány
`$patch: delete`, daprd čte komponenty ze Secretu). Terraform `secrets.tf`: Key Vault secrets (Terraform identita Key Vault Secrets Officer +
`time_sleep` 90 s na propagaci RBAC), UAMI `id-eso` + federated credential + Key Vault Secrets User; `flux.tf` bez `PG_PASSWORD`, substitute
`ESO_CLIENT_ID`, `AZURE_TENANT_ID`. Harness nic nevydává (`ensure_platform_secrets` jen čeká a uklízí legacy ConfigMapy). Měření: `measure` s `e2e=p3-6` (E1a–c).

## P3-6 E2: token exchange v podu role (2026-10-28)

Keycloak IdP `aks` (typ `kubernetes`, `issuerDiscoveryUrl` = OIDC issuer AKS z Terraformu → Flux substitute `AKS_OIDC_ISSUER` → `zakazka-env`
`P0_K8S_OIDC_ISSUER`), klienti `agent-<role>-<tenant>` (federated-jwt, standard token exchange) a audience mappery `platform-gui` – vše z
`rolegen-build/keycloak-clients.json`, aplikuje harness `kc_ensure` (čerstvý realm je nemá – stejný režim jako SPIRE entries). Pody rolí běží pod
SA `role-<role>` (rolegen `tenants-generated.yaml`, SPIRE allow-list + selektory), mají projektovaný token s audience = issuer realmu
(`P0_KC_ISSUER`) a egress na Keycloak (`role-egress`); exchange volají na `P0_KC_EXCHANGE_URL` (FQDN). Měření: `measure` s `e2e=p3-6` (E2a–c).

## P3-6 E5: identita agenta SPIRE per pod (2026-10-29)

SPIRE 1.15.5 (obrazy `spire-server`, `spire-agent`, `oidc-discovery-provider` z ACR; sidecar podů rolí `P0_ROLE_SPIRE_AGENT_IMAGE`). `server.conf`:
`use_pod_uid_for_agent_id = true` v clusteru `platform` pluginu `k8s_psat` (1.15.3+) → agent ID `…/k8s_psat/platform/pod/<pod-UID>` místo UID uzlu,
`agent_ttl = "1h"`, `prune_attested_nodes_expired_for = "1h"`. Selektory a alias entries z rolegen beze změny. Upgrade serveru in-place (sqlite); politika
kompatibility: agent ≤ server, max o jednu minor starší. Měření: `measure` s `e2e=p3-6` (E5a sonda dvou podů).

## P3-6 E6: verzování workflow (2026-10-29)

Orchestrátor zakázky je verzovaný modul `tools/harness_p0_o2/zakazka_wf.py` + snímky `wf_versions/zakazka_<verze>.py` (verze = sha256 obsahu);
obraz `zakazka-app` nese všechny snímky a aplikace je registruje jako verze workflow `zakazka` (Dapr named versioning, 1.17+), aktuální soubor
jako latest. Instance si verzi nese v historii → nasazení nového obrazu (`images.yml` → Flux/`restart_pods`) běžící instance nerozbije: dojedou
na své verzi; chybějící verze = STALLED, ne FAILED. **Postup při změně orchestrátoru**: upravit `zakazka_wf.py` → `python tools/harness_p0_o2/wf_versions.py freeze`
(nový snímek; `images.yml` build padá bez něj) → commit obojího. **Úklid**: `GET /_wf/versions` (port-forward `zakazka` 8010) → verze s `drained: true`
= snímek smazat v Gitu. Aktivity (`app.py`) se mění volně, kontrakty vstupů/výstupů jen rozšiřovat. Měření: `measure` s `e2e=p3-6` (E6a–c).

## P3-6 E7: TLS OpenBao a Keycloaku z interní CA (2026-10-29)

`overlays/aks/tls-internal.yaml`: Certificate `openbao-tls` a `keycloak-tls` (ClusterIssuer `platform-ca`, 90 d, obnova 30 d před koncem,
SAN = jméno Service krátké i FQDN + `localhost`/`127.0.0.1` pro `kubectl port-forward`). OpenBao: listener `tls_cert_file/tls_key_file`
(`tls_min_version = tls12`), `BAO_API_ADDR/CLUSTER_ADDR` https, readiness `scheme: HTTPS`; **reload certifikátu jen SIGHUP/restart podu**
(`kubectl -n platform-data delete pod openbao-0`, auto-unseal z Key Vaultu). Keycloak: `--http-enabled=false`, `KC_HTTPS_PORT=8443`,
`KC_HTTPS_CERTIFICATE_FILE/KEY_FILE` ze Secretu, `KC_HOSTNAME=https://keycloak:8443` → **issuer `https://keycloak:8443/realms/p0`**
(tokeny všech klientů – paměť, aplikace, Governance MCP, pody rolí – ověřují nový iss), management 9000 zůstává HTTP (probe);
Keycloak soubory certifikátu znovu načítá sám. Klienti: `zakazka-env` `P0_BAO_ADDR`/`P0_KC_*` https, `P0_KC_EXCHANGE_URL` https FQDN,
`SSL_CERT_FILE=/etc/platform/ca/ca.crt` (ConfigMap `platform-ca` z trust-manageru, mount do app/memory/governance; pody rolí ji mají od P2-4) –
httpx (trust_env) i urllib/PyJWKClient ji ctí. Harness: port-forward Keycloak 18443→8443, OpenBao https, `SSL_CERT_FILE` = certifi + root platformy
(`logs/ca-bundle.pem`). Služby: `openbao` 8200/8201, `keycloak` 8443/9000 – port 8080 už Service nemá. kind (`base/`) zůstává HTTP.
Měření: `measure` s `e2e=p3-6` (E7a–c; rotace za běhu změřena: OpenBao 33–43 s, Keycloak 54–137 s). Pozor: NetworkPolicy podů rolí
(rolegen `tenant_k8s`) musí pouštět Keycloak na 8443 – port je součást egress kontraktu role.

## Pasti (AKS + Flux)
- Změna issueru Keycloaku (http → https) zneplatní všechny vydané tokeny a cache JWKS klientů – nasazení = restart klientů (harness `restart_pods`);
  realm sám issuer nenese (`KC_HOSTNAME`).
- Změna orchestrátoru Dapr Workflow bez nové verze = instance ze starého obrazu po prvním eventu FAILED (nedeterministický replay; v SUSPENDED
  se to ukáže až po resume). Od E6: každá změna `zakazka_wf.py` = nová verze + snímek; instance bez verze (před E6) jedou na latest.
- Keycloak `--import-realm` existující realm **neaktualizuje** (import jen při prvním startu): změna `realm-p0.json` se do běžícího clusteru
  nepropíše – GUI proto používá existující klient `harness-human`; nový klient/uživatel = P3-2 (migrace realmu, ne import).
- ConfigMap volume se do replik propaguje nezávisle (kubelet sync per pod): po zápisu klíčů do `agentgateway-keys` ověřovat každou repliku
  (headless Service), ne ClusterIP – jinak část requestů 401 (P21b 2026-10-25). Propagace + merge + hot reload: 36–69 s.
- Každý generovaný objekt s cizími `${…}` (env rolí) potřebuje `kustomize.toolkit.fluxcd.io/substitute: disabled`, jinak Flux proměnné smaže.
- `kubectl rollout restart` se hádá s Fluxem: SSA vrátí anotaci `restartedAt` a Deployment se přerolluje zpět (pod aplikace zemřel uprostřed běhu role).
  Restart = smazat pody (šablona beze změny), nebo změnit manifest v Gitu.
- PVC na Azure Disku je root:root → kontejner s uid 1000 potřebuje `fsGroup`; kind `local-path` (0777) to skryl.
- Pohyblivý tag (`p1`) bez `imagePullPolicy: Always` → uzel drží starý obraz po `az acr build`.
- Objekty, které za běhu přepisuje harness/rolegen, musí mít `kustomize.toolkit.fluxcd.io/ssa: IfNotPresent` (ne `reconcile: disabled` – ten by je na
  čerstvém clusteru vůbec nezaložil).
- Flux extension AKS vynucuje multi-tenancy: HelmRelease bez `serviceAccountName` běží jako SA `default` svého ns (chart s CRD neprojde), sourceRef jen
  ve vlastním ns; kustomizace se v clusteru jmenují `<konfigurace>-<název>` (`platform-trust`) – i v `dependsOn`.
- ESO Workload Identity: tenant jen z anotace SA `azure.workload.identity/tenant-id`; bez ní „unable to create client“, s ní a zároveň `tenantId` ve
  store „multiple tenantID found“ (E1, 2026-10-27).
- Změna volume Deploymentu (`dapr-components` ConfigMap → Secret) zabije starý pod uprostřed zápisu do ledgeru na PVC → utržený řádek; aplikace ho od E1
  opraví při startu (`LEDGER_REPAIRED`).
- SPIRE: `spire-server entry create` alias uzlu se při změně selektorů (SA per role) musí smazat a založit znovu – harness porovnává selektory.
- Keycloak admin API: `PUT /clients/{id}` s reprezentací obsahující `protocolMappers` přepíše mappery – lifespan/atributy měnit bez nich.
- Pod v ns tenanta: služby platformy jen přes FQDN (`keycloak.platform-data.svc`), krátká jména z `zakazka-env` nepřeloží (E2, 2. běh).
- Smazání Kata podu je asynchronní (VM se vypíná, desítky sekund); pod zabité aplikace zůstane jako sirotek → GC v `role_pod.py`.
- Flexible Server je z runneru GitHub Actions dosažitelný přímo (pravidlo „Allow Azure services“ 0.0.0.0) – pro schéma paměti a FinOps dotazy; záloha socat pod.
- **OpenBao 2.7 nemá cloud sealy zabudované** (`Error configuring seal "azurekeyvault": unknown wrapper`; changelog 2.7.0, P2-3 2026-10-25) →
  `seal "azurekeyvault"` je externí KMS plugin `openbao-plugin-kms-azure` (repo openbao-plugins, release `kms-azure-v0.1.0`): `plugin_directory`
  + stanza `plugin "kms" "azurekeyvault" { command version }`; binárku stáhne a ověří (sha256 z `checksums-kms-azure.txt`) init kontejner do emptyDir.
- Flux `postBuild.substitute` maže i `$V`/`$A`/`$bin` ve **shellovém skriptu uvnitř manifestu**, který substituci potřebuje (StatefulSet s `${KV_NAME}`) →
  skript bez shellových proměnných (literály, `find -exec`), nebo skript v ConfigMapě se `substitute: disabled`.
- **StatefulSet s podem v CrashLoopBackOff rolling update nikdy nenahradí** (kubernetes/kubernetes#67250) a pod může stát na *mezilehlé* revizi
  (předchozí rollout se nedokončil) → mazat pody s `controller-revision-hash != updateRevision`, ne jen `currentRevision` (3 běhy P2-3 propadly na
  starém podu). Flux `wait` health check pak hlásí `StatefulSet … status: 'Failed'` a `lastAppliedRevision` zůstane na posledním zdravém commitu,
  i když objekty applynuté jsou → odblokování (measure.yml krok + harness ve smyčce čekání na Flux) musí běžet před čekáním na Ready.
- `oidc-discovery-provider`: `domains` **bez portu** (`host:port` → `not a valid domain name: idna`, port z `Host` provider odřezává). Padající sidecar
  udělá pod spire-server NotReady → Service bez endpointů → agenti DaemonSetu padají na `connection refused` (P2-3 2026-10-25).
- Oficiální obrazy `ghcr.io/spiffe/spire-*` nemají binárky v PATH: `kubectl exec … /opt/spire/bin/spire-server entry create …`.
- **srt 0.0.81 bez `ripgrep` odmítne start** (`Sandbox dependencies not available: ripgrep (rg) not found`) – v obrazu aplikace chyběl, takže
  `sandboxed_bash` v podech rolí od P1-6 tiše padal (exit 1) a nic nesandboxoval; P21c měřilo jen přítomnost binárky. Od P2-4 je `ripgrep`
  v `Dockerfile.aks` a sonda egressu hlásí, zda šla přes srt nebo přímo (`via`). Poučení: měřit funkci (příkaz přes srt projde), ne přítomnost.
- Secret/ConfigMap mountovaný **pod** jiný read-only mount (`/etc/agentgateway/tls` uvnitř read-only emptyDir `/etc/agentgateway`) → runc nevytvoří
  mountpoint (`mkdirat … read-only file system`, exit 128). Každý mount na vlastní cestu (`/etc/platform-tls`, `/etc/platform-egress/git`).
- Soubory sondy (klon, wheel, tgz) nesmí ležet ve `work/` role: aplikace z `work/` staví PR přes git data API jako textové bloby a binárka shodila
  aktivitu workflow (PR se nikdy nepublikoval, harness čekal 25 min). Sonda běží v `/work/.egress-probe/` (dot-adresář mimo upload); publish ne-UTF-8 soubory přeskočí.
- **emptyDir přes virtiofs v Kata guestu není pro uid 1000 zapisovatelný** (P2-4 `/work`: `os.access` false), `medium: Memory` (tmpfs v guestu) ano –
  uid 0, gid 1000, mód 3777 (fsGroup). Sockety SPIRE i `/work` role jsou proto Memory emptyDir (P2-6 2026-10-26).
- **srt vynucuje `filesystem.allowWrite` i ve weaker nested módu:** cache npm (`npm_config_cache`) a pip musí ležet pod `/work`, jinak
  `npm pack` padá bez hlášky; `HOME` do `/work` ale nedávat – srt povinně zakazuje čtení `~/.gitconfig` (mandatory deny) a git pak padá
  `Permission denied` → `GIT_CONFIG_GLOBAL=/dev/null`. Hosty mimo allow-list vrací srt jako `CONNECT … 403` (curl 56), ne TLS EOF od gateway.

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

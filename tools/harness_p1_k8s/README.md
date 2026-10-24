# Harness P1 – platforma v Kubernetes (kind → AKS)

Měří kroky fáze P1 ([plán](../../knowledge/platforma/p1-aks.md)). Měřítko není nová funkce, ale **tytéž harnessy z P0 spuštěné
proti clusteru**. Manifesty: [`infra/k8s`](../../infra/README.md).

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

## Spuštění

```bash
cd tools/harness_p1_k8s
export KUBECTL=… KIND=… OPA_BIN=… AGENTGATEWAY_BIN=…        # + venvy harnessů M1 a O1 (jejich README)
../harness_p0_o2/.venv/bin/python harness.py --step p1-2                 # proti běžícímu kind clusteru `platform`
../harness_p0_o2/.venv/bin/python harness.py --step p1-2 --create-kind   # + postaví obraz uzlu, cluster a nahraje obrazy (docker)
DAPR_BIN_DIR=… ../harness_p0_o2/.venv/bin/python harness.py --step p1-3  # identita: vyžaduje lokálně postavené obrazy (infra/images) nahrané do kind
../harness_p0_o2/.venv/bin/python harness.py --step p1-4                 # gateway: docker (bridge IP), venv G1, obraz platform/agentgateway v kind
```

Pasti prostředí (cgroup v1, chybějící `CAP_SYS_RESOURCE`, proxy uzlu): [`infra/README.md`](../../infra/README.md).

## Další kroky

P1-5 Dapr + aplikace zakázky + paměťový server + bridge na kind (O-1, O-2 `p0`/`sre`/`github-hitl` proti clusteru); P1-1 a P1-6 až na AKS.

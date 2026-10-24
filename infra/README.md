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

## Pasti (kind v cloudovém kontejneru)

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
- Docker daemon v kontejneru: `dockerd --data-root <scratch> --storage-driver overlay2` běží i na cgroup v1 (deprecated warning).

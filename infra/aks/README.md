# AKS dev cluster platformy (P1-1)

Skripty pro Adamův Mac (přihlášený `az`). Cloudové prostředí Adama na Azure nedosáhne (bez `az`, síť na `management.azure.com`
blokovaná), proto se tady jen připravují a **jsou neověřené spuštěním** – první běh je měření. Rozhodnutí a cena: [`knowledge/platforma/p1-aks.md`](../../knowledge/platforma/p1-aks.md).

| Skript | Co dělá | Čas / cena |
|---|---|---|
| `precheck.sh` | nic nevytváří: subscription, SKU `Standard_D4as_v5` a `Standard_D2ads_v7` v regionu, kvóty vCPU, výchozí AKS verze, Flexible Server B1ms; JSON do `results/` | 1 min, 0 |
| `create.sh` | RG, ACR Basic, AKS (Azure Linux, Azure CNI overlay + Cilium, system pool 1× D4as_v5, tier Free), node pool `kata` (D2ads_v7, `KataVmIsolation`, autoscale 0–1, taint `sandbox=kata`), Flexible Server PG 16 B1ms s 5 DB a `vector`; kubeconfig; `.env.local` s heslem PG (gitignore) | 15–20 min; ≈ 0,33 USD/h + PG ≈ 15 USD/měs. (*sek.*) |
| `images.sh` | oficiální obrazy do ACR přes `az acr import` (Mac nic netahá), aplikace přes `az acr build` z `infra/images/app/Dockerfile.aks` | 5–10 min |
| `deploy.sh` | `kubectl apply` overlay `infra/k8s/overlays/aks` s dosazeným ACR a Flexible Serverem | 2 min |
| `stop.sh` / `start.sh` | `az aks stop` + stop Flexible Serveru mimo práci (uzly se neúčtují; PG stop max. 7 dní) | – |
| `destroy.sh` | smaže resource group (ptá se) | – |

## Postup na Macu

```bash
cd ~/Developer/Github/akczcz/adam && git pull
source infra/aks/env.sh                 # LOC=swedencentral (záloha: LOC=westeurope source …)
infra/aks/precheck.sh                   # → kata_ok/system_ok/pg_ok; výsledek pošli
infra/aks/create.sh                     # ~15–20 min
infra/aks/images.sh
infra/aks/deploy.sh
RG=$RG CLUSTER=$CLUSTER SKU=$KATA_SKU tools/harness_sandbox_s1/aks/run-s1-aks.sh run   # S1h: Kata guest kernel, start podu, srt v guestu
infra/aks/stop.sh                       # na konci dne
```

Měření P1-1 = S1 na AKS (`tools/harness_sandbox_s1/aks/README.md`, checky S1h-1…6) + pody platformy Ready (`kubectl -n platform-data get pods`).
Výsledky (`tools/harness_sandbox_s1/results/aks-*.json`, `infra/aks/results/precheck-*.json`) a výstup `kubectl get pods` pošli do session.

## Co se na AKS liší od kind

| kind | AKS |
|---|---|
| obrazy stavěné lokálně (`infra/images`) | oficiální obrazy přes ACR import; aplikace `Dockerfile.aks` (python:3.12-slim, CLI z npm) |
| Postgres StatefulSet v clusteru | Flexible Server (ExternalName `postgres`, `sslmode=require`, admin `platform`) – dev: `--public-access 0.0.0.0` (jen Azure IP), cíl VNet integrace |
| NodePorty | žádné – přístup `kubectl port-forward`, později interní LB / AG-UI |
| runc | role pody na node poolu `kata` (`runtimeClassName: kata-vm-isolation`, toleration `sandbox=kata`) – P1-6 |
| Dapr placement/scheduler z binárek | totéž (oficiální `daprio/*` obrazy); Helm chart s operátorem a mTLS = další krok |
| tajemství v Secretech (dev) | zatím stejné; OpenBao + External Secrets v P2 |

## Pasti (očekávané, ověří první běh)
- `az aks create` s `--network-dataplane cilium` vyžaduje `--network-plugin azure --network-plugin-mode overlay`; Pod Sandboxing jen Azure Linux a gen2 SKU s nested virt.
- Dadsv7 pro Pod Sandboxing: AKS release notes 2026-06-19; pokud `az aks nodepool add` odmítne SKU, použít `KATA_SKU=Standard_D4s_v5` (dražší, ověřeno v docs).
- Flexible Server `--public-access 0.0.0.0` = pravidlo „Allow Azure services“; psql z Macu vyžaduje `az postgres flexible-server firewall-rule create` na vlastní IP.
- `azure.extensions=VECTOR` je nutné před `CREATE EXTENSION vector` (jinak „extension not allow-listed“).
- Cluster autoscaler s min 0: první Kata pod čeká ~3–5 min na uzel.

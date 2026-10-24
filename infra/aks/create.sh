#!/usr/bin/env bash
# P1-1: AKS dev cluster platformy (spouští Adam na Macu; ~15–20 min). Idempotentní (každý krok přeskočí existující zdroj).
#  - resource group, ACR (Basic)
#  - AKS: Azure Linux, Azure CNI overlay + Cilium dataplane (CNP default-deny v P1-6), managed identity, system pool 1× SYS_SKU, tier Free
#  - node pool kata: KATA_SKU s --workload-runtime KataVmIsolation, autoscale 0–1, taint sandbox=kata:NoSchedule (role pody v P1-6)
#  - Azure Database for PostgreSQL Flexible Server (PG 16, B1ms), databáze memory/dapr_state/org/agentgateway/keycloak, extension vector
#  - kubeconfig + infra/aks/.env.local (heslo PG; soubor je v .gitignore)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); source "$HERE/env.sh"
t0=$(date +%s); log() { echo "[$(( $(date +%s) - t0 ))s] $*"; }

log "resource group $RG v $LOC"
az group create -n "$RG" -l "$LOC" --tags $TAGS -o none

log "ACR $ACR"
az acr show -n "$ACR" -g "$RG" -o none 2>/dev/null || az acr create -n "$ACR" -g "$RG" --sku Basic --tags $TAGS -o none

log "AKS $CLUSTER (system pool 1× $SYS_SKU, Azure Linux, Cilium)"
if ! az aks show -g "$RG" -n "$CLUSTER" -o none 2>/dev/null; then
  az aks create -g "$RG" -n "$CLUSTER" --tier free --os-sku AzureLinux --node-count 1 --node-vm-size "$SYS_SKU" \
    --network-plugin azure --network-plugin-mode overlay --network-dataplane cilium \
    --enable-managed-identity --attach-acr "$ACR" --generate-ssh-keys --nodepool-name system --nodepool-labels pool=system \
    ${K8S_VERSION:+--kubernetes-version "$K8S_VERSION"} --tags $TAGS -o none
fi

log "node pool kata ($KATA_SKU, KataVmIsolation, autoscale 0–1)"
if ! az aks nodepool show -g "$RG" --cluster-name "$CLUSTER" -n kata -o none 2>/dev/null; then
  az aks nodepool add -g "$RG" --cluster-name "$CLUSTER" -n kata --os-sku AzureLinux --node-vm-size "$KATA_SKU" \
    --workload-runtime KataVmIsolation --enable-cluster-autoscaler --min-count 0 --max-count 1 --node-count 1 \
    --labels pool=kata --node-taints sandbox=kata:NoSchedule --tags $TAGS -o none
fi

log "PostgreSQL Flexible Server $PG ($PG_SKU, PG 16)"
if ! az postgres flexible-server show -g "$RG" -n "$PG" -o none 2>/dev/null; then
  PG_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-28)
  az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOC" --tier Burstable --sku-name "$PG_SKU" --version 16 --storage-size 32 \
    --admin-user "$PG_ADMIN" --admin-password "$PG_PASSWORD" --public-access 0.0.0.0 --yes --tags $TAGS -o none
  # --public-access 0.0.0.0 = povolit Azure služby (AKS egress) – jen dev; cíl = VNet integrace / private endpoint
  umask 077; printf 'export PG_HOST=%s.postgres.database.azure.com\nexport PG_ADMIN=%s\nexport PG_PASSWORD=%s\n' "$PG" "$PG_ADMIN" "$PG_PASSWORD" > "$HERE/.env.local"
  az postgres flexible-server parameter set -g "$RG" -s "$PG" --name azure.extensions --value VECTOR -o none
  for db in memory dapr_state org agentgateway keycloak; do az postgres flexible-server db create -g "$RG" -s "$PG" -d "$db" -o none; done
fi

log "kubeconfig (kontext $CLUSTER)"
az aks get-credentials -g "$RG" -n "$CLUSTER" --overwrite-existing -o none
kubectl get nodes -o wide
kubectl get runtimeclass
log "hotovo. Další: ./images.sh (obrazy do ACR), kubectl apply -k infra/k8s/overlays/aks, tools/harness_sandbox_s1/aks/run-s1-aks.sh run (S1h). Vypnutí: ./stop.sh"

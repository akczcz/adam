#!/usr/bin/env bash
# Nasazení platformy do AKS: overlay aks s dosazenými placeholdery (ACR, Flexible Server). Postgres StatefulSet se nenasazuje (ExternalName).
set -euo pipefail; HERE=$(cd "$(dirname "$0")" && pwd); source "$HERE/env.sh"; source "$HERE/.env.local"; ROOT=$(cd "$HERE/../.." && pwd)
kubectl config use-context "$CLUSTER" >/dev/null
kubectl kustomize "$ROOT/infra/k8s/overlays/aks" \
  | sed -e "s/ACR_PLACEHOLDER/$ACR/g" -e "s/PG_HOST_PLACEHOLDER/$PG_HOST/g" -e "s/PG_PASSWORD_PLACEHOLDER/$PG_PASSWORD/g" \
  | kubectl apply -f -
# schéma paměti (role memory_app, RLS) – stejné jako harness M1; vyžaduje psql a přístup z Macu (firewall Flexible Serveru: add-firewall-rule na vlastní IP)
echo "== pody:"; kubectl -n platform-data get pods
echo "== další: psql \"host=$PG_HOST user=$PG_ADMIN dbname=memory sslmode=require\" -f <(python3 -c 'import sys; sys.path.insert(0,\"$ROOT/tools/harness_memory_m1\"); import harness; print(harness.SCHEMA)') ; ALTER ROLE memory_app PASSWORD 'memory_app'"

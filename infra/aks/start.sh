#!/usr/bin/env bash
set -euo pipefail; HERE=$(cd "$(dirname "$0")" && pwd); source "$HERE/env.sh"
az postgres flexible-server start -g "$RG" -n "$PG" -o none && echo "PG started"
az aks start -g "$RG" -n "$CLUSTER" -o none && echo "AKS started"
kubectl get nodes

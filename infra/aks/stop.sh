#!/usr/bin/env bash
# Vypnutí dev prostředí mimo práci (uzly se neúčtují; Flexible Server stop = max. 7 dní, pak se sám zapne).
set -euo pipefail; HERE=$(cd "$(dirname "$0")" && pwd); source "$HERE/env.sh"
az aks stop -g "$RG" -n "$CLUSTER" -o none && echo "AKS stopped"
az postgres flexible-server stop -g "$RG" -n "$PG" -o none && echo "PG stopped"

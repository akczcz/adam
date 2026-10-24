#!/usr/bin/env bash
# Obrazy do ACR: oficiální (import z quay.io/ghcr.io/docker.io – ACR si je stáhne sám, Mac nic netahá) + build aplikace (az acr build, Dockerfile.aks).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); source "$HERE/env.sh"; ROOT=$(cd "$HERE/../.." && pwd)
imp() { # $1 zdroj, $2 cíl v ACR
  az acr repository show -n "$ACR" --image "$2" -o none 2>/dev/null && { echo "skip $2"; return; }
  echo "import $1 -> $2"; az acr import -n "$ACR" --source "$1" --image "$2" -o none
}
imp quay.io/keycloak/keycloak:26.8.1                       keycloak:26.8.1
imp ghcr.io/openbao/openbao:2.7.1                           openbao:2.7.1
imp ghcr.io/spiffe/spire-server:1.14.2                      spire-server:1.14.2
imp ghcr.io/spiffe/spire-agent:1.14.2                       spire-agent:1.14.2
imp ghcr.io/agentgateway/agentgateway:1.6.0                 agentgateway:1.6.0
imp docker.io/openpolicyagent/opa:1.11.0-static             opa:1.11.0
imp docker.io/otel/opentelemetry-collector-contrib:0.163.2 otel-collector-contrib:0.163.2
imp docker.io/library/clickhouse:26.8                       clickhouse:26.8
imp docker.io/daprio/daprd:1.18.9                           daprd:1.18.9
imp docker.io/daprio/placement:1.18.9                       placement:1.18.9
imp docker.io/daprio/scheduler:1.18.9                       scheduler:1.18.9
# aplikace zakázky (app, paměť, bridge, mock GitHub) – build v ACR z repa (zdroje z tools/, Dockerfile.aks)
BUILD=$(mktemp -d); mkdir -p "$BUILD/src/harness_p0_o2" "$BUILD/src/harness_memory_m1" "$BUILD/src/harness_gateway_g1"
cp "$ROOT"/tools/harness_p0_o2/{app.py,github_bridge.py,mock_github.py} "$BUILD/src/harness_p0_o2/"; cp -r "$ROOT/tools/harness_p0_o2/policies" "$BUILD/src/harness_p0_o2/"
cp "$ROOT/tools/harness_memory_m1/memory_server.py" "$BUILD/src/harness_memory_m1/"; cp "$ROOT/tools/harness_gateway_g1/mock_upstream.py" "$BUILD/src/harness_gateway_g1/"
cp "$ROOT/infra/images/app/requirements.txt" "$ROOT/infra/images/app/Dockerfile.aks" "$BUILD/"
az acr build -r "$ACR" -t zakazka-app:p1 -f "$BUILD/Dockerfile.aks" "$BUILD"
rm -rf "$BUILD"
az acr repository list -n "$ACR" -o table

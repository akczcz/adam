#!/usr/bin/env bash
# S1 na AKS: Kata Pod Sandboxing + srt uvnitř. Spouští se ručně (vyžaduje az, kubectl, jq). Výstup: results/aks-<datum>.json
set -euo pipefail
RG=${RG:-rg-harness-s1}; LOC=${LOC:-westeurope}; CLUSTER=${CLUSTER:-aks-harness-s1}; SKU=${SKU:-Standard_D4s_v5}   # P1-1: RG=rg-platform-dev CLUSTER=aks-platform-dev SKU=Standard_D2ads_v7 a jen `run` (workflow .github/workflows/measure.yml)
HERE=$(cd "$(dirname "$0")" && pwd); OUT="$HERE/../results/aks-$(date +%Y%m%d-%H%M%S).json"
case "${1:-}" in
  create)
    az group create -n "$RG" -l "$LOC" -o none
    az aks create -g "$RG" -n "$CLUSTER" --node-count 1 --node-vm-size "$SKU" --os-sku AzureLinux --network-plugin azure --generate-ssh-keys -o none
    # Pod Sandboxing: node pool s Katou (Azure Linux, gen2 SKU s nested virt). Ověř aktuální stav GA/preview v docs:
    # MicrosoftDocs/azure-aks-docs articles/aks/use-pod-sandboxing.md
    az aks nodepool add -g "$RG" --cluster-name "$CLUSTER" -n kata --node-count 1 --node-vm-size "$SKU" --os-sku AzureLinux --workload-runtime KataVmIsolation -o none
    az aks get-credentials -g "$RG" -n "$CLUSTER" --overwrite-existing
    kubectl get runtimeclass ;;
  run)
    kubectl apply -f "$HERE/networkpolicy.yaml"
    : "${S1_IMAGE:?S1_IMAGE=<acr>.azurecr.io/sandbox-s1:p1 (infra/images/sandbox-s1, workflow images)}"
    POD=$(mktemp); sed "s#image: S1_IMAGE.*#image: $S1_IMAGE#" "$HERE/pod-kata.yaml" > "$POD"
    kubectl delete pod s1-kata --ignore-not-found --wait=true >/dev/null   # pod spec nelze měnit přes apply (Forbidden) – vždy čerstvý pod
    kubectl apply -f "$POD"
    kubectl get runtimeclass runsc >/dev/null 2>&1 && kubectl apply -f "$HERE/pod-gvisor.yaml" || echo "RuntimeClass runsc není – gVisor přeskočen"
    kubectl wait --for=condition=Ready pod/s1-kata --timeout=600s
    for i in $(seq 1 60); do kubectl logs s1-kata 2>/dev/null | grep -q '^s1-done' && break; sleep 5; done   # apt + npm v guestu ~1–2 min
    kubectl logs s1-kata | tail -n 8
    NODE_KERNEL=$(kubectl get node -l pool=kata -o jsonpath='{.items[0].status.nodeInfo.kernelVersion}')
    GUEST=$(kubectl logs s1-kata | grep '^guest-kernel=' | cut -d= -f2 || true)
    SRTLINE=$(kubectl logs s1-kata | sed -n '/^guest-kernel=/,/^s1-done/p' | sed -n '2,3p' | tr '\n' ' ')
    T=(); for i in $(seq 1 3); do kubectl delete pod s1-kata --ignore-not-found --wait=true >/dev/null; S=$(date +%s%N); kubectl apply -f "$POD" >/dev/null; kubectl wait --for=condition=Ready pod/s1-kata --timeout=600s >/dev/null; T+=($(( ($(date +%s%N)-S)/1000000 ))); done
    kubectl delete pod s1-kata --ignore-not-found --wait=false >/dev/null   # úklid: autoscaler pak Kata uzel vrátí na 0
    jq -n --arg nk "$NODE_KERNEL" --arg gk "$GUEST" --arg srt "$SRTLINE" --argjson t "[$(IFS=,; echo "${T[*]}")]" \
      '{meta:{cluster:env.CLUSTER,sku:env.SKU,image:env.S1_IMAGE,date:(now|todate)},checks:[
        {id:"S1h-1",name:"Kata pod má vlastní guest kernel",status:(if $nk!=$gk then "PASS" else "FAIL" end),detail:{node_kernel:$nk,guest_kernel:$gk}},
        {id:"S1h-2",name:"start Kata podu (apply→Ready) ms, 3×",status:"INFO",detail:{ms:$t}},
        {id:"S1h-3",name:"srt uvnitř Kata podu: lo-only netns, seccomp, bez enableWeakerNestedSandbox",status:(if ($srt|test("lo") and test("Seccomp:\t2")) then "PASS" else "FAIL" end),detail:{srt:$srt}}]}' | tee "$OUT"
    echo "zapsáno $OUT – přidej S1h-4 (egress přes NetworkPolicy) po nasazení agentgateway do ns platform" ;;
  destroy) az group delete -n "$RG" --yes --no-wait ;;
  *) echo "použití: $0 create|run|destroy"; exit 2 ;;
esac

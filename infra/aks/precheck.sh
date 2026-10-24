#!/usr/bin/env bash
# P1-1 precheck (spouští Adam na Macu, nic nevytváří): subscription, dostupnost SKU v regionu, kvóty, AKS verze, Flexible Server SKU.
# Výstup: JSON do infra/aks/results/precheck-<datum>.json + čitelné shrnutí. Vyžaduje az ≥ 2.80, jq.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); source "$HERE/env.sh"; mkdir -p "$HERE/results"; OUT="$HERE/results/precheck-$(date +%Y%m%d-%H%M%S).json"
SUB=$(az account show --query '{id:id,name:name,user:user.name}' -o json 2>/dev/null) || { echo "nejsi přihlášen: az login"; exit 2; }
echo "== subscription: $(echo "$SUB" | jq -r .name) ($(echo "$SUB" | jq -r .user))"
check_sku() { # $1 SKU → JSON {sku, available, restrictions, zones}
  az vm list-skus -l "$LOC" --size "$1" --resource-type virtualMachines -o json 2>/dev/null | jq -c --arg sku "$1" \
    '(.[0] // {}) | {sku:$sku, found:(.name!=null), restrictions:[(.restrictions//[])[] | .reasonCode], zones:((.locationInfo//[])[0].zones//[]), hyperv:([(.capabilities//[])[] | select(.name=="HyperVGenerations") | .value][0])}'
}
SYS=$(check_sku "$SYS_SKU"); KATA=$(check_sku "$KATA_SKU")
# kvóty rodin (vCPU) – Dadsv7 a Dasv5
QUOTA=$(az vm list-usage -l "$LOC" -o json 2>/dev/null | jq -c '[.[] | select(.name.value|test("standardDADSv7Family|standardDASv5Family|cores")) | {family:.name.value, limit:.limit, used:.currentValue}]')
AKSV=$(az aks get-versions -l "$LOC" -o json 2>/dev/null | jq -c '[.values[] | select(.isDefault==true) | .version][0] // ([.values[].version] | sort | last)')
PGSKU=$(az postgres flexible-server list-skus -l "$LOC" -o json 2>/dev/null | jq -c '[.[] | .supportedServerEditions[]? | select(.name=="Burstable") | .supportedServerSkus[]? | .name] | index("Standard_B1ms") != null')
PROV=$(az provider show -n Microsoft.ContainerService --query registrationState -o tsv 2>/dev/null)
jq -n --argjson sub "$SUB" --arg loc "$LOC" --argjson sys "$SYS" --argjson kata "$KATA" --argjson quota "${QUOTA:-[]}" --arg aksv "${AKSV:-?}" --arg pg "${PGSKU:-false}" --arg prov "${PROV:-?}" \
  '{date:(now|todate), subscription:$sub, location:$loc, system_sku:$sys, kata_sku:$kata, quota:$quota, aks_default_version:$aksv, flexible_b1ms_available:$pg, containerservice_registered:$prov,
    verdict:{system_ok:($sys.found and ($sys.restrictions|length==0)), kata_ok:($kata.found and ($kata.restrictions|length==0)), pg_ok:($pg=="true"), provider_ok:($prov=="Registered")}}' | tee "$OUT" | jq .
echo "== zapsáno $OUT – pokud kata_ok=false, zkus LOC=westeurope ./precheck.sh nebo KATA_SKU=Standard_D4s_v5"

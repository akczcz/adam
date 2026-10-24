# Proměnné pro AKS dev cluster platformy (P1-1). Načíst: `source infra/aks/env.sh`. Hodnoty dle rozhodnutí 2026-10-24 (knowledge/platforma/p1-aks.md).
export LOC=${LOC:-swedencentral}                 # kandidát; záloha westeurope (precheck.sh ověří SKU)
export RG=${RG:-rg-platform-dev}
export CLUSTER=${CLUSTER:-aks-platform-dev}
export ACR=${ACR:-acrplatformdev$(whoami | tr -cd 'a-z0-9' | cut -c1-6)}   # globálně unikátní, jen [a-z0-9]
export SYS_SKU=${SYS_SKU:-Standard_D4as_v5}      # system pool: platformní komponenty (~6 GiB RAM)
export KATA_SKU=${KATA_SKU:-Standard_D2ads_v7}   # Kata pool: nested virt (Dadsv7 povoleno pro Pod Sandboxing od 2026-06), autoscale 0–1
export PG=${PG:-pg-platform-dev-$(whoami | tr -cd 'a-z0-9' | cut -c1-6)}
export PG_SKU=${PG_SKU:-Standard_B1ms}           # Flexible Server burstable, PG 16
export PG_ADMIN=${PG_ADMIN:-platform}
export K8S_VERSION=${K8S_VERSION:-}              # prázdné = výchozí verze regionu
export TAGS="projekt=adam-platform faze=P1 vlastnik=adam"

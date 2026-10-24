#!/usr/bin/env bash
# Smaže celou resource group (AKS, ACR, Flexible Server). Nevratné – ptá se.
set -euo pipefail; HERE=$(cd "$(dirname "$0")" && pwd); source "$HERE/env.sh"
read -r -p "smazat resource group $RG se všemi zdroji? [ano/NE] " a; [ "$a" = "ano" ] || exit 1
az group delete -n "$RG" --yes --no-wait && echo "mazání $RG běží na pozadí"; rm -f "$HERE/.env.local"

#!/usr/bin/env bash
# Jednorázový bootstrap (Adam na Macu, přihlášený `az`): resource group, storage account pro Terraform state, identita GitHub Actions
# s OIDC federací na repo akczcz/adam a role jen na resource group. Vypíše hodnoty pro GitHub repository variables.
# Idempotentní. Vyžaduje az ≥ 2.80 a oprávnění Owner na subscription (zakládá role assignments).
set -euo pipefail
LOC=${LOC:-swedencentral}; RG=${RG:-rg-platform-dev}; REPO=${REPO:-akczcz/adam}
SUFFIX=${SUFFIX:-$(az account show --query user.name -o tsv | cut -d@ -f1 | tr -cd 'a-z0-9' | cut -c1-8)}
SA=${SA:-sttfstate${SUFFIX}}; ID=${ID:-id-github-${REPO##*/}}
SUB=$(az account show --query id -o tsv); TENANT=$(az account show --query tenantId -o tsv)
echo "== subscription $SUB, tenant $TENANT, RG $RG ($LOC), suffix $SUFFIX"

az group create -n "$RG" -l "$LOC" --tags projekt=adam-platform faze=P1 vlastnik=adam -o none
for p in Microsoft.ContainerService Microsoft.KubernetesConfiguration Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL Microsoft.Storage Microsoft.ManagedIdentity; do
  az provider register -n "$p" -o none 2>/dev/null || true
done

echo "== Terraform state: $SA/tfstate"
az storage account show -n "$SA" -g "$RG" -o none 2>/dev/null || az storage account create -n "$SA" -g "$RG" -l "$LOC" --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false -o none
az storage container create -n tfstate --account-name "$SA" --auth-mode login -o none 2>/dev/null || true

echo "== identita GitHub Actions: $ID (OIDC)"
az identity show -n "$ID" -g "$RG" -o none 2>/dev/null || az identity create -n "$ID" -g "$RG" -l "$LOC" -o none
CLIENT_ID=$(az identity show -n "$ID" -g "$RG" --query clientId -o tsv); PRINCIPAL_ID=$(az identity show -n "$ID" -g "$RG" --query principalId -o tsv)
for sub in "repo:${REPO}:ref:refs/heads/main" "repo:${REPO}:pull_request" "repo:${REPO}:environment:dev"; do
  name=$(echo "$sub" | tr ':/' '--' | cut -c1-120)
  az identity federated-credential show -n "$name" --identity-name "$ID" -g "$RG" -o none 2>/dev/null || \
    az identity federated-credential create -n "$name" --identity-name "$ID" -g "$RG" --issuer https://token.actions.githubusercontent.com --subject "$sub" --audiences api://AzureADTokenExchange -o none
done
RG_ID=$(az group show -n "$RG" --query id -o tsv); SA_ID=$(az storage account show -n "$SA" -g "$RG" --query id -o tsv)
for role in Contributor "User Access Administrator"; do   # UAA: Terraform přiděluje AcrPull kubeletu a Cluster Admin identitě; jen v rámci RG
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "$role" --scope "$RG_ID" -o none 2>/dev/null || true
done
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope "$SA_ID" -o none 2>/dev/null || true

cat <<EOF

== Nastav GitHub repository variables (Settings → Secrets and variables → Actions → Variables), nebo:
gh variable set AZURE_CLIENT_ID       -R $REPO -b "$CLIENT_ID"
gh variable set AZURE_TENANT_ID       -R $REPO -b "$TENANT"
gh variable set AZURE_SUBSCRIPTION_ID -R $REPO -b "$SUB"
gh variable set AZURE_PRINCIPAL_ID    -R $REPO -b "$PRINCIPAL_ID"
gh variable set TF_STATE_RG           -R $REPO -b "$RG"
gh variable set TF_STATE_SA           -R $REPO -b "$SA"
gh variable set NAME_SUFFIX           -R $REPO -b "$SUFFIX"
gh variable set AZURE_LOCATION        -R $REPO -b "$LOC"
== pak: GitHub Actions → workflow „infra“ → Run workflow (plan) – nebo PR do main s infra/terraform/**.
EOF

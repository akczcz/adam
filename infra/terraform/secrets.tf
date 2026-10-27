# P3-6 E1: bootstrap tajemství platformy žijí v Key Vaultu (zapisuje Terraform), do clusteru je nese External Secrets Operator (ESO)
# s workload identitou SA external-secrets:eso-keyvault (UAMI + federated credential přes OIDC issuer AKS). Harness ani Flux substitute
# už žádné tajemství nenesou: heslo PG zmizelo z konfigurace Flux extension (flux.tf), TLS egressu gateway vydává cert-manager.
# Hodnoty, které Adam mění mimo Git (ostrý API klíč modelu, rotace client secretů rolí), Terraform po prvním založení nepřepisuje (ignore_changes).

# identita Actions (Terraform) musí tajemství založit – Contributor na RG data-plane Key Vaultu nedává (jako Crypto Officer v keyvault.tf)
resource "azurerm_role_assignment" "deployer_kv_secrets_officer" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# propagace RBAC role na data-plane Key Vaultu trvá až minuty (první apply klíče openbao-unseal padal 403) → počkat
resource "time_sleep" "kv_rbac" {
  create_duration = "90s"
  depends_on      = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

resource "random_password" "git_backend_token" {
  length  = 32
  special = false
}

resource "random_password" "bridge_webhook" {
  length  = 32
  special = false
}

# ESO ClusterSecretStore azure-kv čte `secret/<name>` (remoteRef.key bez prefixu = secret)
resource "azurerm_key_vault_secret" "pg_password" {
  name         = "pg-platform-password"
  value        = random_password.pg.result
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "heslo admin účtu Flexible Serveru (postgres-auth, DSN gateway/FinOps/Dapr)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
}

resource "azurerm_key_vault_secret" "git_backend_token" {
  name         = "git-backend-token"
  value        = "git-${random_password.git_backend_token.result}"
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "token, který gateway vkládá do requestů na git backend (mock-github jen otisk)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
}

resource "azurerm_key_vault_secret" "bridge_webhook" {
  name         = "bridge-webhook-secret"
  value        = random_password.bridge_webhook.result
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "sdílené tajemství webhooku mock-github → bridge"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
}

# API klíč upstreamu modelu: výchozí mock (gateway na AKS míří na mock-upstream); ostrý klíč nastaví Adam v Key Vaultu, Terraform ho nepřepíše
resource "azurerm_key_vault_secret" "anthropic_api_key" {
  name         = "anthropic-api-key"
  value        = var.anthropic_api_key
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "ANTHROPIC_API_KEY pro gateway (mock) – ostrý klíč jen tady, ne v Gitu"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  lifecycle { ignore_changes = [value] }
}

# client secrety service-account klientů rolí v Keycloaku (realm p0 z Gitu – dev hodnoty); rotace = změna v Keycloaku + tady
resource "azurerm_key_vault_secret" "role_client_secrets" {
  name         = "role-client-secrets"
  value        = jsonencode({ for r in var.role_clients : r => "p0-${r}-secret" })
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "P0_ROLE_CLIENT_SECRETS (JSON role → client secret Keycloak)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  lifecycle { ignore_changes = [value] }
}

# --- ESO: workload identita pro čtení Key Vaultu ------------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "eso" {
  name                = "id-eso-${var.name_suffix}"
  location            = var.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "eso" {
  name                      = "aks-external-secrets-eso-keyvault"
  user_assigned_identity_id = azurerm_user_assigned_identity.eso.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = azurerm_kubernetes_cluster.aks.oidc_issuer_url
  subject                   = "system:serviceaccount:external-secrets:eso-keyvault"
}

resource "azurerm_role_assignment" "eso_kv_secrets_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.eso.principal_id
}

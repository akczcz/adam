# P2-3: auto-unseal OpenBao přes Azure Key Vault (seal "azurekeyvault") s workload identitou podu (UAMI + federated credential na SA
# platform-data:openbao přes OIDC issuer AKS) – žádné tajemství v podu; klíče Key Vault spravuje RBAC.
locals {
  kv_name = "kv-platform-dev-${var.name_suffix}" # ≤ 24 znaků, globálně unikátní
}

resource "azurerm_key_vault" "kv" {
  name                       = local.kv_name
  location                   = var.location
  resource_group_name        = data.azurerm_resource_group.rg.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false # dev: destroy bez 90denní karantény
  tags                       = var.tags
}

# identita Actions (Terraform) musí klíč založit – Contributor na RG data-plane Key Vaultu nedává
resource "azurerm_role_assignment" "deployer_kv_crypto_officer" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_key" "openbao_unseal" {
  name         = "openbao-unseal"
  key_vault_id = azurerm_key_vault.kv.id
  key_type     = "RSA"
  key_size     = 2048
  key_opts     = ["wrapKey", "unwrapKey", "encrypt", "decrypt"]
  tags         = var.tags

  depends_on = [azurerm_role_assignment.deployer_kv_crypto_officer] # propagace role trvá až minuty → první apply může selhat 403, opakovat
}

resource "azurerm_user_assigned_identity" "openbao" {
  name                = "id-openbao-${var.name_suffix}"
  location            = var.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "openbao" {
  name                      = "aks-platform-data-openbao"
  user_assigned_identity_id = azurerm_user_assigned_identity.openbao.id # azurerm 5: místo resource_group_name/parent_id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = azurerm_kubernetes_cluster.aks.oidc_issuer_url
  subject                   = "system:serviceaccount:platform-data:openbao"
}

resource "azurerm_role_assignment" "openbao_kv_crypto_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Crypto User"
  principal_id         = azurerm_user_assigned_identity.openbao.principal_id
}

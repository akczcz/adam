# Azure Database for PostgreSQL Flexible Server – jedna instance, databáze memory/dapr_state/org/agentgateway/keycloak, extension vector.
# P3-6 E12: jen privátní síť – private endpoint ve VNet platformy (network.tf), veřejný přístup vypnutý, žádné firewall pravidlo
# (do E11 dev běžel přes veřejný endpoint + „Allow Azure services“ = dosažitelný heslem z celého Azure).
resource "random_password" "pg" {
  length  = 28
  special = false
}

resource "azurerm_postgresql_flexible_server" "pg" {
  name                   = local.pg_name
  resource_group_name    = data.azurerm_resource_group.rg.name
  location               = coalesce(var.pg_location, var.location)
  version                = "16"
  sku_name               = var.pg_sku_name
  storage_mb             = 32768
  administrator_login    = var.pg_admin
  administrator_password = random_password.pg.result
  # zónu nepinujeme: Sweden Central 2026-10-24 vrátil RegionalAllocationFailed pro B1ms v zóně 1; Azure si zónu vybere
  backup_retention_days         = 7
  public_network_access_enabled = false # P3-6 E12: přístup jen přes private endpoint (network.tf)
  tags                          = var.tags

  authentication {
    password_auth_enabled = true
  }

  # Azure přidělí zónu sám; bez ignore by Terraform chtěl zónu „vrátit“ na null → "zone can only be changed when exchanged with standby" (apply 2026-10-25)
  lifecycle { ignore_changes = [zone] }
}

# pgvector musí být na allow-listu rozšíření, jinak CREATE EXTENSION vector selže
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.pg.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "db" {
  for_each  = toset(var.databases)
  name      = each.key
  server_id = azurerm_postgresql_flexible_server.pg.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

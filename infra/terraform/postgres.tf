# Azure Database for PostgreSQL Flexible Server – jedna instance, databáze memory/dapr_state/org/agentgateway/keycloak, extension vector.
# Dev: veřejný endpoint + pravidlo „Allow Azure services“ (AKS egress); cíl = VNet integrace / private endpoint (P2).
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
  public_network_access_enabled = true
  tags                          = var.tags

  authentication {
    password_auth_enabled = true
  }
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.pg.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
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

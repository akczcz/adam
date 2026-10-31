# P3-6 E12: Flexible Server jen přes privátní síť – private endpoint ve vlastní VNet (rg-platform-dev), peering na managed VNet AKS (node RG),
# privátní DNS zóna privatelink.postgres.database.azure.com nalinkovaná na VNet AKS (pody dál používají FQDN serveru – verify-full z E11 drží),
# veřejný přístup serveru vypnutý, firewall „Allow Azure services“ pryč. Harness z runneru na server nedosáhne → socat pod (pgfwd) jako dosud záloha.
# Identita Actions potřebuje navíc „Network Contributor“ na node RG (peering z druhé strany + join VNet pro DNS link) – uděluje Adam ručně
# (bootstrap azure-oidc.sh, viz infra/README.md E12); vše ostatní je v rg-platform-dev.

data "azurerm_resources" "aks_vnet" {
  resource_group_name = azurerm_kubernetes_cluster.aks.node_resource_group
  type                = "Microsoft.Network/virtualNetworks"
}

data "azurerm_virtual_network" "aks" {
  name                = data.azurerm_resources.aks_vnet.resources[0].name
  resource_group_name = azurerm_kubernetes_cluster.aks.node_resource_group
}

resource "azurerm_virtual_network" "pe" {
  name                = "vnet-platform-pe-${var.name_suffix}"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  address_space       = [var.pe_vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "pe" {
  name                              = "snet-private-endpoints"
  resource_group_name               = data.azurerm_resource_group.rg.name
  virtual_network_name              = azurerm_virtual_network.pe.name
  address_prefixes                  = [var.pe_vnet_cidr]
  private_endpoint_network_policies = "Disabled"
}

resource "azurerm_virtual_network_peering" "pe_to_aks" {
  name                      = "pe-to-aks"
  resource_group_name       = data.azurerm_resource_group.rg.name
  virtual_network_name      = azurerm_virtual_network.pe.name
  remote_virtual_network_id = data.azurerm_virtual_network.aks.id
  allow_forwarded_traffic   = true
}

resource "azurerm_virtual_network_peering" "aks_to_pe" {
  name                      = "aks-to-pe"
  resource_group_name       = azurerm_kubernetes_cluster.aks.node_resource_group
  virtual_network_name      = data.azurerm_virtual_network.aks.name
  remote_virtual_network_id = azurerm_virtual_network.pe.id
  allow_forwarded_traffic   = true
}

resource "azurerm_private_dns_zone" "pg" {
  name                = "privatelink.postgres.database.azure.com"
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "aks" {
  name                 = "aks"
  private_dns_zone_id  = azurerm_private_dns_zone.pg.id
  virtual_network_id   = data.azurerm_virtual_network.aks.id
  registration_enabled = false
}

resource "azurerm_private_endpoint" "pg" {
  name                = "pe-${local.pg_name}"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  subnet_id           = azurerm_subnet.pe.id
  tags                = var.tags

  private_service_connection {
    name                           = "pg"
    private_connection_resource_id = azurerm_postgresql_flexible_server.pg.id
    subresource_names              = ["postgresqlServer"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "pg"
    private_dns_zone_ids = [azurerm_private_dns_zone.pg.id]
  }
}

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

locals {
  acr_name = "acrplatformdev${var.name_suffix}"
  # jméno Flexible Serveru je globální DNS; po neúspěšném vytvoření ve Sweden Central zůstalo "pg-platform-dev-akcz" rezervované
  # (InvalidResourceLocation, server přitom neexistuje) → do jména jde i region
  pg_name = "pg-platform-dev-${var.name_suffix}-${var.location}"
}

# --- registr obrazů (oficiální obrazy přes `az acr import`, aplikace přes `az acr build` – workflow images.yml) ---------------
resource "azurerm_container_registry" "acr" {
  name                = local.acr_name
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.tags
}

# --- AKS: Azure Linux, Azure CNI overlay + Cilium, workload identity, system pool ----------------------------------------------
resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.cluster_name
  location            = var.location
  resource_group_name = data.azurerm_resource_group.rg.name
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.kubernetes_version
  sku_tier            = "Free"

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  default_node_pool {
    name                        = "system"
    vm_size                     = var.system_vm_size
    node_count                  = 1
    os_sku                      = "AzureLinux"
    temporary_name_for_rotation = "systmp"
    node_labels                 = { pool = "system" }
    upgrade_settings { max_surge = "1" }
  }

  identity { type = "SystemAssigned" }

  # azurerm 5.x blok vyžaduje; Manual = klasické node pooly bez Node Auto Provisioning (Karpenter)
  node_provisioning_profile { mode = "Manual" }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    network_policy      = "cilium"
  }

  tags = var.tags

  # AKS vzniká 5–10 min; výchozích 90 min jen prodlužuje zaseknutý Creating (Sweden Central 2026-10-24)
  timeouts { create = "40m" }
}

# kubelet smí tahat z ACR
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                            = azurerm_container_registry.acr.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

# identita GitHub Actions může číst admin kubeconfig (workflow measure.yml: S1 na Katě, kubectl get pods)
resource "azurerm_role_assignment" "deployer_aks_admin" {
  count                = var.deployer_principal_id == null ? 0 : 1
  scope                = azurerm_kubernetes_cluster.aks.id
  role_definition_name = "Azure Kubernetes Service Cluster Admin Role"
  principal_id         = var.deployer_principal_id
}

# --- node pool kata: Pod Sandboxing (KataVmIsolation), autoscale 0–1, taint pro pody rolí ---------------------------------------
resource "azurerm_kubernetes_cluster_node_pool" "kata" {
  name                        = "kata"
  kubernetes_cluster_id       = azurerm_kubernetes_cluster.aks.id
  vm_size                     = var.kata_vm_size
  os_sku                      = "AzureLinux"
  workload_runtime            = "KataVmIsolation"
  temporary_name_for_rotation = "katatmp" # změna vm_size = rotace poolu přes dočasný pool (azurerm 5)
  auto_scaling_enabled        = true
  min_count                   = 0
  max_count                   = var.kata_max_count
  node_count                  = 0 # VM až při prvním Kata podu: Poland Central 2026-10-25 vrátil AllocationFailed pro D2ads_v7 při vzniku poolu
  node_labels                 = { pool = "kata" }
  node_taints                 = ["sandbox=kata:NoSchedule"]
  tags                        = var.tags

  lifecycle { ignore_changes = [node_count] } # řídí autoscaler
}

# Adopce poolu kata: vznikl při apply 2026-10-25 (AllocationFailed → stav Failed), ale do tf state se nedostal („already exists – needs to be
# imported“). Import blok je po úspěšném importu no-op; smazat při úklidu.
import {
  to = azurerm_kubernetes_cluster_node_pool.kata
  id = "${data.azurerm_resource_group.rg.id}/providers/Microsoft.ContainerService/managedClusters/${var.cluster_name}/agentPools/kata"
}

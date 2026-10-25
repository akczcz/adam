# GitOps: AKS GitOps extension (Microsoft.Flux) sleduje repo a aplikuje infra/k8s/overlays/aks. Proměnné pro manifesty
# (${ACR_LOGIN_SERVER}, ${PG_HOST}, ${PG_PASSWORD}) dosazuje postBuild substitute – heslo PG tak leží v konfiguraci Flux
# extension a v tf state (dev); cíl P2 = External Secrets Operator nad Key Vault/OpenBao a substitute_from Secret.
resource "azurerm_kubernetes_cluster_extension" "flux" {
  name           = "flux"
  cluster_id     = azurerm_kubernetes_cluster.aks.id
  extension_type = "microsoft.flux"

  # AKS povolí na clusteru jen jednu operaci naráz: paralelní vznik node poolu kata a extension skončil 409 AnotherOperationInProgress
  # (apply 2026-10-25) → pořadí cluster → node pool → extension → flux konfigurace
  depends_on = [azurerm_kubernetes_cluster_node_pool.kata]
}

resource "azurerm_kubernetes_flux_configuration" "platform" {
  name       = "platform"
  cluster_id = azurerm_kubernetes_cluster.aks.id
  namespace  = "flux-system"
  scope      = "cluster"

  git_repository {
    url                      = var.gitops_repo_url
    reference_type           = "branch"
    reference_value          = var.gitops_branch
    sync_interval_in_seconds = 120
  }

  kustomizations {
    name                     = "platform"
    path                     = var.gitops_path
    sync_interval_in_seconds = 120
    post_build {
      substitute = {
        ACR_LOGIN_SERVER = azurerm_container_registry.acr.login_server
        PG_HOST          = azurerm_postgresql_flexible_server.pg.fqdn
        PG_PASSWORD      = random_password.pg.result
      }
    }
  }

  depends_on = [azurerm_kubernetes_cluster_extension.flux, azurerm_kubernetes_cluster_node_pool.kata, azurerm_role_assignment.aks_acr_pull]
}

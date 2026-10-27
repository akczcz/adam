# GitOps: AKS GitOps extension (Microsoft.Flux) sleduje repo a aplikuje čtyři kustomizace: operators (cert-manager, trust-manager, ESO – P3-6 E1),
# trust (CA, bundle, ClusterSecretStore; závisí na operators), roles (namespace tenantů) a platform (infra/k8s/overlays/aks, závisí na trust). Proměnné pro manifesty
# (${ACR_LOGIN_SERVER}, ${PG_HOST}, ${KV_NAME}, ${OPENBAO_CLIENT_ID}, ${ESO_CLIENT_ID}) dosazuje postBuild substitute – žádné tajemství: heslo PG
# a ostatní bootstrap tajemství nese ESO z Key Vaultu (secrets.tf), substitute jen identifikátory.
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

  # P3-6 E1: operátoři (HelmRelease cert-manager, trust-manager, external-secrets; obrazy chartů z ACR – images.yml je importuje)
  kustomizations {
    name                     = "operators"
    path                     = "infra/k8s/operators"
    sync_interval_in_seconds = 120
    timeout_in_seconds       = 900
    post_build {
      substitute = { ACR_LOGIN_SERVER = azurerm_container_registry.acr.login_server }
    }
  }

  # P3-6 E1: interní CA (ClusterIssuer platform-ca), trust bundle (ConfigMap platform-ca) a ClusterSecretStore Key Vaultu – až po CRD operátorů
  kustomizations {
    name                     = "trust"
    path                     = "infra/k8s/trust"
    sync_interval_in_seconds = 120
    timeout_in_seconds       = 600
    depends_on               = ["operators"]
    post_build {
      substitute = {
        KV_NAME       = azurerm_key_vault.kv.name
        ESO_CLIENT_ID = azurerm_user_assigned_identity.eso.client_id
      }
    }
  }

  # ns rolí (P1-6): vlastní kustomization bez namespace transformeru overlay (NetworkPolicy, RBAC pro pody rolí)
  kustomizations {
    name                     = "roles"
    path                     = "infra/k8s/roles"
    sync_interval_in_seconds = 120
  }

  kustomizations {
    name                     = "platform"
    path                     = var.gitops_path
    sync_interval_in_seconds = 120
    timeout_in_seconds       = 900
    depends_on               = ["trust"] # Certificate agentgateway-tls a ExternalSecrety potřebují ClusterIssuer a ClusterSecretStore
    post_build {
      substitute = {
        ACR_LOGIN_SERVER  = azurerm_container_registry.acr.login_server
        PG_HOST           = azurerm_postgresql_flexible_server.pg.fqdn
        KV_NAME           = azurerm_key_vault.kv.name                        # P2-3: auto-unseal OpenBao
        OPENBAO_CLIENT_ID = azurerm_user_assigned_identity.openbao.client_id # workload identity SA openbao
      }
    }
  }

  depends_on = [azurerm_kubernetes_cluster_extension.flux, azurerm_kubernetes_cluster_node_pool.kata, azurerm_role_assignment.aks_acr_pull]
}

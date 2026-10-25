output "acr_login_server" { value = azurerm_container_registry.acr.login_server }
output "acr_name" { value = azurerm_container_registry.acr.name }
output "aks_name" { value = azurerm_kubernetes_cluster.aks.name }
output "aks_oidc_issuer_url" { value = azurerm_kubernetes_cluster.aks.oidc_issuer_url }
output "pg_fqdn" { value = azurerm_postgresql_flexible_server.pg.fqdn }
output "kubeconfig_cmd" { value = "az aks get-credentials -g ${var.resource_group_name} -n ${var.cluster_name} --admin" }
output "key_vault_name" { value = azurerm_key_vault.kv.name }
output "openbao_client_id" { value = azurerm_user_assigned_identity.openbao.client_id }

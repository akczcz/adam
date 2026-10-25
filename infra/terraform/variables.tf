# Rozhodnutí 2026-10-25 (knowledge/platforma/p1-aks.md): Poland Central (záloha Italy North), system pool D4as_v5, Kata pool D4s_v5 autoscale 0–1 (D2ads_v7 bez kapacity),
# Flexible Server B1ms, Contributor jen na resource group (RG zakládá bootstrap, Terraform ji jen čte).
variable "location" {
  type    = string
  default = "polandcentral" # 2026-10-25: Sweden Central bez kapacity (AKS Creating 90 min, PG RegionalAllocationFailed), West Europe nepřijímá nové subscription (locationineligible), GWC+France NotAvailableForSubscription
}
variable "pg_location" {
  type        = string
  default     = null
  description = "Region Flexible Serveru, pokud se má lišit od clusteru (kapacita Burstable SKU); null = var.location"
}
variable "resource_group_name" {
  type        = string
  default     = "rg-platform-dev"
  description = "Existující RG z infra/bootstrap/azure-oidc.sh"
}
variable "name_suffix" {
  type        = string
  description = "Krátký unikátní suffix pro globálně unikátní jména (ACR, Flexible Server), např. GitHub login"
  validation {
    condition     = can(regex("^[a-z0-9]{3,10}$", var.name_suffix))
    error_message = "name_suffix: 3–10 znaků [a-z0-9]"
  }
}
variable "cluster_name" {
  type    = string
  default = "aks-platform-dev"
}
variable "kubernetes_version" {
  type    = string
  default = null # výchozí verze regionu
}
variable "system_vm_size" {
  type    = string
  default = "Standard_D4as_v5"
}
variable "kata_vm_size" {
  type        = string
  default     = "Standard_D4s_v5" # nested virt, Pod Sandboxing (docs); D2ads_v7 v Poland Central jen zóna 1 a 2026-10-25 AllocationFailed → DSv5 (kvóta 8 vCPU)
  description = "SKU pro node pool kata (KataVmIsolation)"
}
variable "kata_max_count" {
  type    = number
  default = 1
}
variable "pg_sku_name" {
  type    = string
  default = "B_Standard_B1ms"
}
variable "pg_admin" {
  type    = string
  default = "platform"
}
variable "databases" {
  type    = list(string)
  default = ["memory", "dapr_state", "org", "agentgateway", "keycloak"]
}
variable "gitops_repo_url" {
  type    = string
  default = "https://github.com/akczcz/adam"
}
variable "gitops_branch" {
  type    = string
  default = "main"
}
variable "gitops_path" {
  type    = string
  default = "infra/k8s/overlays/aks"
}
variable "deployer_principal_id" {
  type        = string
  default     = null
  description = "Object ID identity GitHub Actions (OIDC) → Azure Kubernetes Service Cluster Admin Role na clusteru (workflow measure.yml)"
}
variable "tags" {
  type    = map(string)
  default = { projekt = "adam-platform", faze = "P1", vlastnik = "adam", sprava = "terraform" }
}

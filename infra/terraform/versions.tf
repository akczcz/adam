terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.11" }
    random  = { source = "hashicorp/random", version = "~> 3.7" }
  }
  # State v Azure Storage (účet z infra/bootstrap/azure-oidc.sh); parametry přes -backend-config v GitHub Actions, auth OIDC.
  backend "azurerm" {
    use_oidc = true
  }
}

provider "azurerm" {
  features {
    resource_group { prevent_deletion_if_contains_resources = true }
  }
  use_oidc                        = true
  resource_provider_registrations = "none" # providery registruje bootstrap (identita má Contributor jen na RG)
}

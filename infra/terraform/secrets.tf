# P3-6 E1: bootstrap tajemství platformy žijí v Key Vaultu (zapisuje Terraform), do clusteru je nese External Secrets Operator (ESO)
# s workload identitou SA external-secrets:eso-keyvault (UAMI + federated credential přes OIDC issuer AKS). Harness ani Flux substitute
# už žádné tajemství nenesou: heslo PG zmizelo z konfigurace Flux extension (flux.tf), TLS egressu gateway vydává cert-manager.
# Hodnoty, které Adam mění mimo Git (ostrý API klíč modelu, rotace client secretů rolí), Terraform po prvním založení nepřepisuje (ignore_changes).

# identita Actions (Terraform) musí tajemství založit – Contributor na RG data-plane Key Vaultu nedává (jako Crypto Officer v keyvault.tf)
resource "azurerm_role_assignment" "deployer_kv_secrets_officer" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# propagace RBAC role na data-plane Key Vaultu trvá až minuty (první apply klíče openbao-unseal padal 403) → počkat
resource "time_sleep" "kv_rbac" {
  create_duration = "90s"
  depends_on      = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

resource "random_password" "git_backend_token" {
  length  = 32
  special = false
}

resource "random_password" "bridge_webhook" {
  length  = 32
  special = false
}

# ESO ClusterSecretStore azure-kv čte `secret/<name>` (remoteRef.key bez prefixu = secret)
resource "azurerm_key_vault_secret" "pg_password" {
  name         = "pg-platform-password"
  value        = random_password.pg.result
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "heslo admin účtu Flexible Serveru (postgres-auth, DSN gateway/FinOps/Dapr)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  # P4-9: rotace = ARM PATCH hesla serveru + nová verze zde (harness --rotate pg-admin / workflow rotate); Terraform hodnotu po založení nevrací
  lifecycle { ignore_changes = [value] }
}

resource "azurerm_key_vault_secret" "git_backend_token" {
  name         = "git-backend-token"
  value        = "git-${random_password.git_backend_token.result}"
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "token, který gateway vkládá do requestů na git backend (mock-github jen otisk)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
}

resource "azurerm_key_vault_secret" "bridge_webhook" {
  name         = "bridge-webhook-secret"
  value        = random_password.bridge_webhook.result
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "sdílené tajemství webhooku mock-github → bridge"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
}

# API klíč upstreamu modelu: výchozí mock (gateway na AKS míří na mock-upstream); ostrý klíč nastaví Adam v Key Vaultu, Terraform ho nepřepíše
resource "azurerm_key_vault_secret" "anthropic_api_key" {
  name         = "anthropic-api-key"
  value        = var.anthropic_api_key
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "ANTHROPIC_API_KEY pro gateway (mock) – ostrý klíč jen tady, ne v Gitu"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  lifecycle { ignore_changes = [value] }
}

# P4-2: PAT GitHubu pro ostrý běh – vidí ho jen agentgateway (routa github-api vkládá Authorization, aplikace token nemá); výchozí hodnota je
# neplatná (GitHub → 401 Bad credentials = důkaz zapojení bez tajemství), ostrý PAT nastaví Adam v Key Vaultu a po běhu revokuje
resource "azurerm_key_vault_secret" "github_token" {
  name         = "github-token"
  value        = var.github_token
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "GitHub fine-grained PAT (repo platformy: contents, issues, pull_requests) pro ostrý běh – jen v gateway (backendAuth), ne v Gitu ani v aplikaci"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  lifecycle { ignore_changes = [value] }
}

# P4-4: Cloudflare Tunnel sidecaru aplikace – token pojmenovaného tunelu a veřejný hostname; výchozí "quick" = quick tunnel bez účtu (měření).
# Ostré hodnoty nastaví Adam v Key Vaultu (Terraform je nepřepisuje): token z Cloudflare Zero Trust (Networks → Tunnels), hostname = published application.
resource "azurerm_key_vault_secret" "cloudflare_tunnel_token" {
  name         = "cloudflare-tunnel-token"
  value        = var.cloudflare_tunnel_token
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "Cloudflare Tunnel token pojmenovaného tunelu pro sidecar cloudflared aplikace zakázky; 'quick' = quick tunnel *.trycloudflare.com bez účtu"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  lifecycle { ignore_changes = [value] }
}

resource "azurerm_key_vault_secret" "cloudflare_tunnel_hostname" {
  name         = "cloudflare-tunnel-hostname"
  value        = var.cloudflare_tunnel_hostname
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "Veřejný hostname pojmenovaného tunelu (published application) – harness a dokumentace; 'quick' = hostname se čte z logu sidecaru"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  lifecycle { ignore_changes = [value] }
}

# client secrety service-account klientů rolí v Keycloaku (realm p0 z Gitu – dev hodnoty); rotace = změna v Keycloaku + tady
resource "azurerm_key_vault_secret" "role_client_secrets" {
  name         = "role-client-secrets"
  value        = jsonencode({ for r in var.role_clients : r => "p0-${r}-secret" })
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "P0_ROLE_CLIENT_SECRETS (JSON role → client secret Keycloak)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  lifecycle { ignore_changes = [value] }
}

# --- P3-6 E9: hesla, která dosud ležela jako dev literály v manifestech (base/keycloak keycloak-admin `admin-dev`, DSN paměti a Governance MCP
# `memory_app:memory_app` / `org_reader:org_reader`) – náhodná hodnota v Key Vaultu, do clusteru přes ESO (overlays/aks/secrets-eso.yaml);
# hesla DB rolí nastavuje aplikace zakázky při startu (ALTER ROLE z P0_DB_ROLE_PASSWORDS), admina Keycloaku otočí harness jako operátor
# (KC_BOOTSTRAP_ADMIN_* platí jen pro prázdnou DB). Base hodnoty zůstávají jen pro kind. Rotace = `terraform taint`/nová hodnota tady.
resource "random_password" "keycloak_admin" {
  length  = 32
  special = false
}

resource "random_password" "pg_role" {
  for_each = toset(["memory_app", "org_reader", "org_writer"])
  length   = 32
  special  = false
}

resource "azurerm_key_vault_secret" "keycloak_admin_password" {
  name         = "keycloak-admin-password"
  value        = random_password.keycloak_admin.result
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "heslo bootstrap admina Keycloaku (realm master; Secret keycloak-admin přes ESO, harness ho při migraci otočí admin API)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  # P4-7: hodnota z random_password jen při založení; rotace = nová verze v Key Vaultu (operátor), Terraform ji nevrací
  lifecycle { ignore_changes = [value] }
}

resource "azurerm_key_vault_secret" "pg_role_password" {
  for_each     = random_password.pg_role
  name         = "pg-${replace(each.key, "_", "-")}-password"
  value        = each.value.result
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "heslo DB role ${each.key} (RLS, ne admin; nastavuje aplikace zakázky při startu, DSN přes ESO)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  # P4-7: hodnota z random_password jen při založení; rotace = nová verze v Key Vaultu (operátor), Terraform ji nevrací
  lifecycle { ignore_changes = [value] }
}

# --- P4-6: hesla lidí harnessu (adam, bea, platform-admin, probe) – dosud dev literály v realm-p0.json (Git) a tím i na veřejné URL (P4-4).
# Náhodná hodnota v Key Vaultu → ESO Secret keycloak-humans (KC_HUMAN_PW_* pro placeholdery ${...} v realm JSON při importu, P0_HUMAN_PASSWORDS
# pro harness/promo). Existující realm import nemění → běžící instanci otočí harness jako operátor (admin API reset-password), jako u admina (E9).
resource "random_password" "kc_human" {
  for_each = toset(["adam", "bea", "platform-admin", "probe"])
  length   = 24
  special  = false
}

resource "azurerm_key_vault_secret" "kc_human_password" {
  for_each     = random_password.kc_human
  name         = "kc-user-${each.key}-password"
  value        = each.value.result
  key_vault_id = azurerm_key_vault.kv.id
  content_type = "heslo člověka harnessu ${each.key} v realmu p0 (Secret keycloak-humans přes ESO; Keycloak import $${KC_HUMAN_PW_*}, běžící realm otočí harness admin API)"
  tags         = var.tags
  depends_on   = [time_sleep.kv_rbac]
  # P4-7: hodnota z random_password jen při založení; rotace = nová verze v Key Vaultu (operátor), Terraform ji nevrací
  lifecycle { ignore_changes = [value] }
}

# --- ESO: workload identita pro čtení Key Vaultu ------------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "eso" {
  name                = "id-eso-${var.name_suffix}"
  location            = var.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "eso" {
  name                      = "aks-external-secrets-eso-keyvault"
  user_assigned_identity_id = azurerm_user_assigned_identity.eso.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = azurerm_kubernetes_cluster.aks.oidc_issuer_url
  subject                   = "system:serviceaccount:external-secrets:eso-keyvault"
}

resource "azurerm_role_assignment" "eso_kv_secrets_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.eso.principal_id
}

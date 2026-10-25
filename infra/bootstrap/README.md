# AKS dev prostředí platformy (P1-1): bootstrap → Terraform → GitHub Actions → Flux

Jediný ruční krok je `azure-oidc.sh` na Adamově Macu. Všechno ostatní dělají GitHub Actions s OIDC identitou (žádný secret v repu
ani v chatu) a Flux v clusteru (GitOps z `infra/k8s/overlays/aks`). Claude workflow spouští a čte přes GitHub API, Azure sám nepotřebuje.
Rozhodnutí a cena: [`knowledge/platforma/p1-aks.md`](../../knowledge/platforma/p1-aks.md).

```mermaid
flowchart LR
    Mac[Adam · Mac · az login] -->|azure-oidc.sh jednou| B[RG rg-platform-dev<br/>storage tfstate<br/>identita id-github-adam + federace OIDC<br/>role Contributor + UAA na RG]
    GH[GitHub Actions] -->|OIDC token → Entra| B
    GH -->|infra.yml: terraform plan/apply| TF[ACR · AKS Azure Linux + Cilium<br/>Kata pool · Flexible Server PG16<br/>Flux extension + konfigurace]
    GH -->|images.yml: acr import / acr build| ACR[(ACR)]
    TF -->|Flux sleduje main| K8s[infra/k8s/overlays/aks<br/>postBuild ${ACR_LOGIN_SERVER} ${PG_HOST} ${PG_PASSWORD}]
    GH -->|measure.yml, cluster.yml| K8s
    Claude[Claude · GitHub API] -->|run / status / logs| GH
```

| Vrstva | Kde | Co |
|---|---|---|
| bootstrap (1×, ručně) | `infra/bootstrap/azure-oidc.sh` | RG, storage account pro state, user-assigned identita s federovanými credentials pro `repo:akczcz/adam` (`ref:refs/heads/main`, `pull_request`, `environment:dev`), role **Contributor + User Access Administrator jen na RG**, Storage Blob Data Contributor na state; registrace providerů. Vypíše `gh variable set …` |
| IaC | `infra/terraform/` (azurerm 5.x) | ACR Basic; AKS Free tier, Azure Linux, Azure CNI overlay + Cilium, OIDC issuer + workload identity, system pool 1× D4as_v5; node pool `kata` D2ads_v7 `KataVmIsolation` autoscale 0–1, taint `sandbox=kata`; Flexible Server B1ms PG 16, DB memory/dapr_state/org/agentgateway/keycloak, `azure.extensions=VECTOR`, firewall Allow Azure services; AcrPull kubeletu; Cluster Admin pro identitu Actions; Flux extension + konfigurace `platform` |
| pipelines | `.github/workflows/` | `infra` (plan na PR, apply na push do main / ručně; destroy ručně), `images` (ACR import pinovaných oficiálních obrazů + `az acr build` aplikace z `infra/images/app/Dockerfile.aks`), `measure` (stav podů, S1 na Katě, artifact s výsledky), `cluster` (stop/start/status – šetření) |
| GitOps | Flux (AKS extension `microsoft.flux`) | kustomization `platform` z `infra/k8s/overlays/aks` na větvi `main`, sync 120 s; proměnné dosazuje `post_build.substitute` z Terraformu |

## Postup

1. **Mac** (přihlášený `az`, Owner subscription): `infra/bootstrap/azure-oidc.sh` → spustit vypsané `gh variable set …` (nebo hodnoty vložit v
   Settings → Secrets and variables → Actions → Variables). V repu vytvořit environment `dev` (Settings → Environments; volitelně required reviewer = Adam,
   pak každý `apply` čeká na klik).
2. **PR s `infra/terraform/**`** → workflow `infra` udělá `plan` a napíše ho do job summary. Merge do `main` → `apply` (environment `dev`).
3. Workflow `images` (ručně) → obrazy v ACR. Flux do 2 minut nasadí overlay; pody se po doběhnutí importu rozběhnou samy (do té doby `ImagePullBackOff`).
4. Workflow `measure` → S1h na Katě + `kubectl get pods`; výsledky jako artifact. Workflow `cluster` → `stop` na konci dne.

Claude: `actions_run_trigger` → `actions_get` → `get_job_logs` přes GitHub MCP; výsledky čte z job summary a artifactů.

## Co se na AKS liší od kind

| kind | AKS |
|---|---|
| obrazy stavěné lokálně (`infra/images`) | oficiální obrazy přes ACR import; aplikace `Dockerfile.aks` (python:3.12-slim, CLI z npm) |
| Postgres StatefulSet v clusteru | Flexible Server (ExternalName `postgres`, `sslmode=require`, admin `platform`) – dev: Allow Azure services (jen Azure IP), cíl VNet integrace / private endpoint |
| NodePorty | žádné – přístup `kubectl port-forward`, později interní LB / AG-UI |
| runc | role pody na node poolu `kata` (`runtimeClassName: kata-vm-isolation`, toleration `sandbox=kata`) – P1-6 |
| Dapr placement/scheduler z binárek | totéž (oficiální `daprio/*` obrazy); Dapr Helm chart jako Flux HelmRelease = další krok |
| `kubectl apply -k` z harnessu | Flux z `main`; tajemství zatím `post_build.substitute` (heslo PG v konfiguraci Flux a tf state) – P2: External Secrets nad Key Vault/OpenBao |

## Bezpečnostní model
- OIDC: GitHub vydá krátkodobý token, Entra ho vymění za Azure token jen pro subjekty `repo:akczcz/adam:*` výše; žádný client secret neexistuje.
- Identita má Contributor + UAA **jen na `rg-platform-dev`** (UAA kvůli role assignments AcrPull / Cluster Admin v Terraformu). Subscription-wide nic.
- `apply` běží v environmentu `dev` → lze vyžadovat ruční schválení; `plan` na PR má jen `pull_request` subjekt (čtení + plan, zápis do state locku).
- Tf state obsahuje heslo PG → storage account bez veřejného blob přístupu, přístup jen identita Actions + Adam.

## Pasti (očekávané, ověří první `apply`)
- **Kapacita regionu (změřeno 2026-10-24, Sweden Central):** Flexible Server B1ms zóna 1 → `RegionalAllocationFailed`; AKS system pool D4as_v5 visel
  v `Creating` 90 min do timeoutu Terraformu a zůstal v Azure mimo state (smazat `az aks delete`, Terraform ho nezná). Proto West Europe jako
  výchozí region, PG bez `zone`, `timeouts.create = 40m` u AKS. Při `RegionalAllocationFailed` zkusit `TF_VAR_pg_location` jiný region nebo jiné SKU.
- azurerm 5.x vyžaduje v `azurerm_kubernetes_cluster` blok `node_provisioning_profile` (`mode = "Manual"`).
- Pod Sandboxing jen Azure Linux + gen2 SKU s nested virt; Dadsv7 podle AKS release notes 2026-06-19. Pokud `kata` pool odmítne SKU →
  `TF_VAR_kata_vm_size=Standard_D4s_v5` (dražší, ověřeno v docs). Cluster autoscaler s min 0: první Kata pod čeká ~3–5 min na uzel.
- `azure.extensions=VECTOR` musí být nastaveno před `CREATE EXTENSION vector` (M1 schema seed) – Terraform to dělá; jinak „extension not allow-listed“.
- Flux extension vyžaduje registrovaný provider `Microsoft.KubernetesConfiguration` (bootstrap) – identita Actions providery registrovat nesmí
  (`resource_provider_registrations = "none"`).
- **OIDC `sub` s ID (změřeno 2026-10-24, první `plan`):** GitHub posílá `repo:akczcz@51314480/adam@1386473812:environment:dev`, ne
  `repo:akczcz/adam:environment:dev` → Entra `AADSTS700213 No matching federated identity record`. Bootstrap zakládá federaci pro obě podoby
  (6 credentials); při dalším podobném selhání porovnat subjekt z chyby s `az identity federated-credential list`.
- `terraform plan` z PR cizího forku OIDC token nedostane (subjekt `pull_request` platí jen pro PR z vlastního repa) – záměr.
- Flux `postBuild.substitute` nahrazuje každé `${var}`/`$var` v manifestech a **nedefinované proměnné mění na prázdný řetězec** (fluxcd/pkg
  `kustomize_varsub.go`, non-strict). ConfigMapy `agentgateway-config` (`$AGW_DATABASE_URL`) a `keycloak-realm` (`${username}`) mají proto
  v overlay anotaci `kustomize.toolkit.fluxcd.io/substitute: disabled`; `$(POD_IP)` substituce nezná a nechává.

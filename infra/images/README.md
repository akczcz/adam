# Lokálně stavěné obrazy pro kind (ne pro AKS)

Prostředí harnessu nedosáhne na quay.io, ghcr.io ani api.adoptium.net a Docker Hub má rate limit, proto se obrazy identity vrstvy
staví z GitHub release artefaktů. Build kontext si připraví skript/ruční kroky (viz `../README.md`):

| Obraz | Základ | Obsah build kontextu |
|---|---|---|
| `platform/keycloak:26.8.1` | `pgvector/pgvector:pg16` (Debian, už lokálně) | `jdk/` = Temurin JRE 21 (`github.com/adoptium/temurin21-binaries` release `jdk-21.0.10+7`), `keycloak/` = `keycloak-26.8.1` dist bez `data/` |
| `platform/openbao:2.7.1` | `busybox:latest` | `bao` z `openbao_2.7.1_linux_amd64.tar.gz` |
| `platform/spire:1.14.2` | `busybox:latest` | `spire-server`, `spire-agent` z `spire-1.14.2-linux-amd64-musl.tar.gz` |

Na AKS: `quay.io/keycloak/keycloak:26.8.1`, `ghcr.io/openbao/openbao:2.7.1`, `ghcr.io/spiffe/spire-server:1.14.2`, `ghcr.io/spiffe/spire-agent:1.14.2`
(přes interní registr / ACR import).

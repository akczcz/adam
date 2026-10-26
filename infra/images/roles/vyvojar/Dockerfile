# GENEROVÁNO rolegen z vyvojar.yaml (sha256 59f961e19cad0d0b) – obraz role vyvojar 0.1.0; cíl: registry.platform.internal/roles/vyvojar:0.1.0
ARG BASE_IMAGE=platform/zakazka-app:p1
FROM ${BASE_IMAGE}
LABEL org.opencontainers.image.title="platform role vyvojar" org.opencontainers.image.version="0.1.0"       platform.role="vyvojar" platform.role.version="0.1.0" platform.role.source_sha256_16="59f961e19cad0d0b" platform.role.owner="adam"
USER 0
COPY etc/platform/ /etc/platform/
RUN mkdir -p /etc/claude && cp /etc/platform/managed-settings.json /etc/claude/managed-settings.json  && for b in az gcloud aws kubectl docker helm terraform; do p=$(command -v "$b" 2>/dev/null) && rm -f "$p"; done; true   # žádný cloud CLI v obrazu role (role.md sandbox)
USER 1000

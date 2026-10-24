# Keycloak 26.8.1 pro kind harness: distribuce z GitHub releases + Temurin JRE 21 z GitHub releases nad Debian základem (pgvector obraz, už lokálně)
# (quay.io a api.adoptium.net nejsou z prostředí dostupné; Docker Hub rate limit). Na AKS = oficiální quay.io/keycloak/keycloak:26.8.1.
FROM pgvector/pgvector:pg16
USER root
COPY jdk /opt/jdk
COPY keycloak /opt/keycloak
ENV JAVA_HOME=/opt/jdk PATH=/opt/jdk/bin:/opt/keycloak/bin:$PATH JAVA_TOOL_OPTIONS=
RUN useradd -u 1000 -m keycloak 2>/dev/null || true; mkdir -p /opt/keycloak/data/import && chown -R 1000:0 /opt/keycloak \
 && su keycloak -c "/opt/keycloak/bin/kc.sh build --db=postgres --health-enabled=true --metrics-enabled=true"
USER 1000
WORKDIR /opt/keycloak
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]

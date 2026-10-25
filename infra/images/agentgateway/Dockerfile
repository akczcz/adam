# agentgateway 1.6.0 pro kind harness: statická binárka z GitHub releases nad busyboxem (ghcr.io není z prostředí dostupné).
# Na AKS = ghcr.io/agentgateway/agentgateway:1.6.0.
FROM busybox:latest
COPY agentgateway /usr/local/bin/agentgateway
RUN mkdir -p /etc/agentgateway && adduser -D -u 1000 agw
USER 1000
ENTRYPOINT ["/usr/local/bin/agentgateway"]

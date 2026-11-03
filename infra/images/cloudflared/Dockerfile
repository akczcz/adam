# P4-4: cloudflared jako sidecar aplikace zakázky – vstup do GUI/AG-UI přes Cloudflare Tunnel místo kubectl port-forward / veřejné IP.
# Oficiální obraz je bez shellu; sidecar potřebuje při startu rozhodnout režim (pojmenovaný tunnel s TUNNEL_TOKEN z Key Vaultu, nebo
# quick tunnel *.trycloudflare.com bez účtu), proto statická binárka nad Alpine. Verze: cloudflare/cloudflared 2026.10.7 (Docker Hub 2026-11-02).
# Běh 1 P4-4: busybox bez CA certifikátů → „x509: certificate signed by unknown authority“ k api.trycloudflare.com a CrashLoop sidecaru shodil
# readiness celého podu – proto ca-certificates a smyčka: výpadek tunelu se loguje a opakuje, kontejner nikdy nekončí (aplikace uvnitř clusteru běží dál).
FROM docker.io/cloudflare/cloudflared:2026.10.7 AS cf
FROM docker.io/library/alpine:3.22
RUN apk add --no-cache ca-certificates && adduser -D -u 65532 cloudflared
COPY --from=cf /usr/local/bin/cloudflared /usr/local/bin/cloudflared
USER 65532:65532
ENTRYPOINT ["/bin/sh", "-c"]
# režim podle TUNNEL_TOKEN: prázdné nebo "quick" = quick tunnel na veřejný listener aplikace (APP_PUBLIC_URL), jinak pojmenovaný tunnel (token jen v env, ne v argumentech)
CMD ["while true; do if [ -n \"$TUNNEL_TOKEN\" ] && [ \"$TUNNEL_TOKEN\" != quick ]; then cloudflared tunnel --no-autoupdate --metrics 0.0.0.0:2000 --protocol ${TUNNEL_PROTOCOL:-http2} run; else cloudflared tunnel --no-autoupdate --metrics 0.0.0.0:2000 --protocol ${TUNNEL_PROTOCOL:-http2} --url ${APP_PUBLIC_URL:-http://127.0.0.1:8011}; fi; echo \"cloudflared skončil ($?), nový pokus za 15 s\"; sleep 15; done"]

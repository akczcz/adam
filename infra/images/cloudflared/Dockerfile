# P4-4: cloudflared jako sidecar aplikace zakázky – vstup do GUI/AG-UI přes Cloudflare Tunnel místo kubectl port-forward / veřejné IP.
# Oficiální obraz je bez shellu; sidecar potřebuje při startu rozhodnout režim (pojmenovaný tunnel s TUNNEL_TOKEN z Key Vaultu, nebo
# quick tunnel *.trycloudflare.com bez účtu), proto statická binárka nad busyboxem. Verze: cloudflare/cloudflared 2026.10.7 (Docker Hub 2026-11-02).
FROM docker.io/cloudflare/cloudflared:2026.10.7 AS cf
FROM docker.io/library/busybox:1.37.0-uclibc
COPY --from=cf /usr/local/bin/cloudflared /usr/local/bin/cloudflared
USER 65532:65532
ENTRYPOINT ["/bin/sh", "-c"]
# režim podle TUNNEL_TOKEN: prázdné nebo "quick" = quick tunnel na veřejný listener aplikace (APP_PUBLIC_URL), jinak pojmenovaný tunnel (token jen v env, ne v argumentech)
CMD ["if [ -n \"$TUNNEL_TOKEN\" ] && [ \"$TUNNEL_TOKEN\" != quick ]; then exec cloudflared tunnel --no-autoupdate --metrics 0.0.0.0:2000 --protocol ${TUNNEL_PROTOCOL:-http2} run; else exec cloudflared tunnel --no-autoupdate --metrics 0.0.0.0:2000 --protocol ${TUNNEL_PROTOCOL:-http2} --url ${APP_PUBLIC_URL:-http://127.0.0.1:8011}; fi"]

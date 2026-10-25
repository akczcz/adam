# Měřicí obraz S1 pro Kata pod na AKS: nástroje předinstalované, protože sandbox nemá egress (default-deny NetworkPolicy; apt/npm za běhu
# selže na "Network is unreachable" – změřeno 2026-10-25). Staví images.yml přes `az acr build` jako sandbox-s1:p1.
FROM node:22-bookworm
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends bubblewrap socat ripgrep curl util-linux ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && npm i -g --silent @anthropic-ai/sandbox-runtime@0.0.81

# Aplikace zakázky (Dapr Workflow + Claude Agent SDK), server paměti M1 a GitHub bridge – jeden obraz, tři příkazy.
# kind: Debian základ (pgvector obraz, už lokálně) + Python 3.12 standalone (python-build-standalone přes uv) + Node 22 (nodejs.org)
# + Claude Code CLI (kopie z hostitele, glibc ≥ 2.26) – Docker Hub rate limit, apt nedostupné. Bez srt/bubblewrap: v P1-5 je hranicí
# pod (sandboxed_bash = bash v podu, P0_SRT=none); srt + Kata přijdou s pody rolí v P1-6. Na AKS: python:3.12-slim + oficiální CLI.
FROM pgvector/pgvector:pg16
COPY python /opt/python
COPY uv /usr/local/bin/uv
ADD node.tar.xz /opt/
COPY claude-code /opt/claude-code
RUN ln -s /opt/node-v22.*-linux-x64 /opt/node && ln -sf /opt/claude-code/bin/claude /usr/local/bin/claude
ENV PATH=/opt/venv/bin:/opt/python/bin:/opt/node/bin:/opt/claude-code/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
COPY ccr-ca.crt /usr/local/share/ca-certificates/ccr-ca.crt
# build v prostředí s TLS-inspekcí (agent proxy): CA do systémového úložiště + uv s nativním TLS; za běhu v kind se TLS ven nepoužívá
ENV UV_NATIVE_TLS=1 SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
RUN cat /usr/local/share/ca-certificates/ccr-ca.crt >> /etc/ssl/certs/ca-certificates.crt && uv venv -q -p /opt/python/bin/python3.12 /opt/venv && uv pip install -q -p /opt/venv/bin/python -r /tmp/requirements.txt \
 && uv pip install -q -p /opt/venv/bin/python --reinstall --no-deps "dapr-ext-workflow==1.18.3" durabletask-dapr \
 && useradd -u 1000 -m app && mkdir -p /app /tmp/p0-o2 && chown -R app /app /tmp/p0-o2
COPY src/ /app/
USER 1000
WORKDIR /app

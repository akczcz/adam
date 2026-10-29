# Obraz `platform/zakazka-app` (kind)

Build kontext (připraví harness/operátor, ne v repu): `python/` = python-build-standalone 3.12 (`uv python install 3.12`),
`uv` binárka, `node.tar.xz` z nodejs.org (22.x), `claude-code/` = kopie `/opt/claude-code` (Claude Code CLI 2.1.x, glibc ≥ 2.26),
`ccr-ca.crt` = CA proxy prostředí (jen pro build za TLS-inspekcí), `src/` = `tools/harness_p0_o2/{app.py,…,zakazka_wf.py,wf_versions.py,policies/,wf_versions/}`
(úplný seznam v `.github/workflows/images.yml`; `wf_versions/` = snímky verzí orchestrátoru, P3-6 E6),
`tools/harness_memory_m1/memory_server.py`, `tools/harness_gateway_g1/mock_upstream.py`.

Na AKS: `python:3.12-slim` + `pip install -r requirements.txt` + oficiální instalace Claude Code CLI; pody rolí (P1-6) mají navíc srt + bubblewrap.

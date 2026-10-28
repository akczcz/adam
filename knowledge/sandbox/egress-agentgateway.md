---
tema: agentgateway jako egress proxy sandboxu (CONNECT + SNI allow-list, terminace pro git/modely) a inspect_k8s_sandbox jako eval provider
naposledy_overeno: 2026-10-23
zralost: změřeno harnessem S1 lokálně (1.6.0); loopback ochrana dynamic backendu až 1.7.0-alpha.1
primarni_zdroje:
  - https://github.com/agentgateway/agentgateway/tree/v1.6.0/examples/traffic-egress-proxy
  - https://github.com/agentgateway/agentgateway/blob/v1.6.0/crates/agentgateway/src/types/local.rs
  - https://github.com/agentgateway/agentgateway/blob/v1.6.0/crates/agentgateway/src/proxy/gateway.rs
  - https://github.com/agentgateway/agentgateway/blob/v1.6.0/crates/agentgateway/src/proxy/tcpproxy.rs
  - https://github.com/agentgateway/agentgateway/blob/v1.6.0/crates/agentgateway/src/http/auth/mod.rs
  - https://github.com/agentgateway/agentgateway/pull/3318
  - https://github.com/agentgateway/agentgateway/pull/3889
  - https://github.com/agent-substrate/substrate
  - https://github.com/UKGovernmentBEIS/inspect_k8s_sandbox/tree/main/docs/docs
  - https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/docs/approval.qmd
  - https://code.claude.com/docs/en/network-config
---

# Egress sandboxu přes agentgateway

Kolo 2, hloubka C (2026-10-23), z kódu tagu v1.6.0 a examples; část tvrzení změřil [harness S1](../../tools/harness_sandbox_s1/README.md).

## Závěr

- agentgateway 1.6.0 funguje jako egress proxy sandboxu podle `examples/traffic-egress-proxy`: CONNECT bind → interní bind 443 →
  TLS listener `hostname: "*"` sniffuje SNI → `tcpRoutes.hostnames` allow-list → `dynamic: {}` dialuje **SNI hostname přes DNS gateway,
  ne IP z CONNECT** (agent IP nepinne). **Změřeno S1e/S1g:** pkg projde passthrough, nepovolené SNI = `error: route not found` v logu,
  klient vidí TLS EOF (curl exit 35), ne 403.
- Vložení git tokenu a per-repo autorizace vyžadují **terminaci HTTPS pro daný hostname** (vzor `config-conditional`) + `backendAuth: key`
  (watched soubor) nebo `oauthTokenExchange`; **na TLS passthrough tcpRoute `backendAuth` nejde**. **Změřeno S1f:** sandbox bez tokenu,
  backend dostal `Bearer`, `git-receive-pack` → 403 `directResponse`, cizí org → 404.
- **1.6.0 nekontroluje loopback/link-local u dynamic backendů** (PR #3889 až 1.7.0-alpha.1, link-local nepotvrzen; schema main
  `config.backend.allowDynamicLoopback`) → **CNP na gateway podu** (deny 169.254.0.0/16, 168.63.129.16/32, RFC1918 mimo služby) je povinná.
- `substrateEgress` je PEP pro cizí control plane **agent-substrate** (`ateapi`, gVisor/microVM aktoři, mTLS sidecar `atunnel`) – jen vzor.
- `inspect_k8s_sandbox` 0.14.0 umí `runtimeClassName` per service (Kata fix v 0.14.0), bez Cilia (`networkPolicy.enabled: false`) nic
  nevynucuje a `allowDomains` **odmítá** → egress = CNP + agentgateway v custom chartu. Inspect approval = **fnmatch nad renderovaným
  voláním** (`bash(cmd='*git push*`), ne regex. **Změřeno S-E2:** `sandboxed_bash(cmd=*git-receive-pack*)` → reject funguje.

## CONNECT proxy – konfigurace (v1.6.0)

```yaml
binds:
- port: 3000
  tunnelProtocol: connect      # sandbox: HTTPS_PROXY=http://gw:3000
  listeners: []
gateways:
  secure:
    port: 443                  # virtuální – cíl CONNECT host:443 se mapuje sem podle portu, hostname se zahodí
    listeners:
    - name: git                # terminace jen pro vybrané hosty (vzor config-conditional)
      hostname: git.example.com
      protocol: HTTPS
      tls: { cert: …, key: … }   # nebo mode: dynamicCa (CA klíč žije v gateway, ne v sandboxu)
    - name: public-egress
      hostname: "*"
      protocol: TLS            # SNI bez terminace
tcpRoutes:
- name: public-egress-allowlist
  gateways: secure/public-egress
  hostnames: [pypi.org, files.pythonhosted.org, github.com, objects.githubusercontent.com]
  backends:
  - dynamic: {}                # nebo target: CEL → mirror v air-gapu bez změny sandboxu
```

| Situace | Chování (kód `gateway.rs`, `tcpproxy.rs`; S1 změřeno kde uvedeno) |
|---|---|
| CONNECT host:443, SNI v allow-listu | 200 + tunel, log `tls.sni`, `route`, `endpoint` (S1e ✅) |
| SNI mimo allow-list | `RouteNotFound`, spojení zavřeno bez TLS alertu, log `error: "route not found"` (S1e/S1g ✅ – curl exit 35) |
| CONNECT na :80 / :22, IP literál | bind pro port neexistuje → 404 → **plaintext HTTP a SSH ven nejdou** (git jen HTTPS) |
| GET absolute-form na CONNECT bind | 405 |
| `dynamic.target` CEL | `destination.hostname + ":8443"` přepíše cíl (S1 používá pro mock; air-gap mirror) |

CA do sandboxu: gateway bundle negeneruje → CA jako ConfigMap `platform-ca` v ns tenanta (od P3-6 E1 ji rozdává trust-manager z interní CA
cert-manageru; 2026-10-28) připojená do podu role + `SSL_CERT_FILE`, `GIT_SSL_CAINFO`, `NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `PIP_CERT`.
Smazání env agentem jen rozbije TLS.

## Git přes gateway

- HTTPS listener per hostname (`github.com`, `dev.azure.com`) + `routes` s `backendAuth`. Typy v1.6.0: `passthrough`, **`key`**
  (`value.file` – „File references are watched, so rotating the file reloads it without a restart“; `location.header {name, prefix}`),
  `gcp`, `aws`, `azure`, `copilot`, `jwtSign`, `oauthTokenExchange` (RFC 8693/7523 – jen proti AS s exchange, tj. Keycloak → interní
  Gitea/GitLab, ne GitHub), `crossAppAccess`.
- GitHub: installation token GitHub App (1 h) píše sidecar/ESO do souboru v gateway podu → `key` s `prefix: "Basic "` a
  `base64(x-access-token:TOKEN)` (git smart HTTP = Basic; Bearer u GitHubu neověřeno). Azure DevOps: `azure` backendAuth (scope ADO neověřen) nebo PAT v `key`.
- Per repo/metoda: `policies.authorization.rules[].allow: request.path.startsWith("/org/repo.git/") && request.method == "GET"`;
  push = `POST …/git-receive-pack` (+ `GET …/info/refs?service=git-receive-pack`); `extAuthz` → OPA, táž Rego jako hook Agent SDK.
  Log: `config.logging.fields.add: {git.repo: request.path, git.op: request.method, agent: source.spiffeId}`.
- Hypotéza: CONNECT bind s vnějším mTLS (`tls.spiffe`) → SVID podu jako `source.identity` i na passthrough egressu – nedokumentováno, harness.

## DNS a SSRF

Dial = SNI hostname resolvovaný gateway (`config.dns`, systémový resolv.conf; **bez nameserverů fallback na Google Public DNS** – past A3);
zbývá DNS rebinding allow-listed jména a domain fronting (stejný limit jako srt). CIDR deny-list v gateway není → CNP na gateway podu.
`substrateEgress` bere CONNECT IP jako autoritativní („atunnel is a trusted component validated with mTLS“) – pro nás nepoužitelné bez `ateapi`.

## Claude Code a srt

- CC respektuje `HTTPS_PROXY`/`NO_PROXY` i pro `ANTHROPIC_BASE_URL`; SOCKS ne. **Varianta A** (dvě cesty): `ANTHROPIC_BASE_URL=http://gw:4100`
  (plaintext `llm` bind) + `HTTPS_PROXY=http://gw:3000` + `NO_PROXY=.svc,localhost` – CONNECT bind má `listeners: []`, `/v1/messages` na něm = 405.
  **Varianta B** (jeden port): `ANTHROPIC_BASE_URL=https://llm.platform.internal` + HTTPS listener na `gateways.secure` + CA v obrazu →
  veškerý egress jen port 3000, CNP triviální. Doporučení: B pro sandbox, A pro platformní agenty. S1 měřil A.
- Vedlejší provoz CC: `api.anthropic.com` (WebFetch preflight → `skipWebFetchPreflight: true`), Datadog (`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`),
  `registry.npmjs.org` (npx MCP), `raw.githubusercontent.com` (changelog). Node `fetch()` bez `NODE_USE_ENV_PROXY=1` ignoruje proxy → Node MCP servery fail-closed.
- srt: `parentProxy` → gateway **bez resolved-address checku** (dělá CNP/gateway); `httpProxyPort` nepoužívat (vypne kontroly CC); `tlsTerminate` + mask ne.

## inspect_k8s_sandbox 0.14.0

- Built-in chart `agent-env`: `services.<name>.runtimeClassName` (default `gvisor`; `kata-vm-isolation` libovolný string), `image, command, env[],
  securityContext, volumes, initContainers, resources` (2Gi/500m Guaranteed); globální `allowDomains` (80/443; wildcard Cilium ≥ 1.18), `allowCIDR`,
  `allowEntities`, `networkPolicy.enabled`, `additionalResources` (libovolné objekty vč. CNP), `automountServiceAccountToken: false`.
- Bez Cilia: `networkPolicy.enabled: false` → nic se nerenderuje, `allowDomains` **odmítnuty**; `INSPECT_SANDBOX_VALUES` neplatí pro custom chart.
- Custom chart: pod s labely `app.kubernetes.io/instance: {{ .Release.Name }}` a `inspect/service: default`, jen lokální chart;
  `SandboxEnvironmentSpec("k8s", K8sSandboxEnvironmentConfig(chart=…, values=…))`.
- Exec: kubernetes-python websocket (ne kubectl), skript přes stdin, `timeout -k 5s`, retry 5× (idempotence!); `load_kube_config()` → fallback in-cluster.
- Limity: `INSPECT_MAX_HELM_INSTALL/UNINSTALL` = 8, `INSPECT_MAX_POD_OPS` = CPU×4, `INSPECT_HELM_TIMEOUT` 600 s; Cilium drop = tichý hang.
- AKS: nedokumentováno → custom chart s `kata-vm-isolation` + CNP na IP agentgateway + env `HTTPS_PROXY`, CA v obrazu.

## Approval na nevratné akce (`approval.qmd`)

```yaml
approvers:
  - name: human
    tools: ["bash(cmd='*git push*", "bash(cmd='*git-receive-pack*"]
  - name: auto
    tools: "*"
```
`_policy.py`: `fnmatch(format_function_call(name, arguments), pattern)` – glob nad renderovaným voláním. `auto_approver(decision=approve|reject|terminate|escalate|modify)`;
bridged Claude Code pravděpodobně `Bash(command='*git push*` (hypotéza). V platformě totéž pravidlo jako PreToolUse hook Agent SDK + OPA.

## Co ověřit dál

- [ ] agentgateway 1.7: `allowDynamicLoopback` a link-local (S-E3 proti 168.63.129.16 přes gateway s rebindingem); PR #2162 generická chybová těla vs. kontrakt Anthropic (přeměřit G1).
- [ ] mTLS/SPIFFE na CONNECT bindu → `source.identity` v `tcpRoutes[].policies.authorization` (release note 1.6.0 „destination (SNI) attribute in network authz“).
- [ ] `backendAuth: azure` scope pro Azure DevOps git; GitHub git-http Bearer vs Basic.
- [ ] custom chart s `runtimeClassName: kata-vm-isolation` na AKS; ConfigMap volume pro CA; `Bash(command='*git push*` v `sandbox_agent_bridge`.
- [ ] agent-substrate: release a vztah k kubernetes-sigs/agent-sandbox.

## Changelog
- 2026-10-23: první verze (kolo 2, hloubka C) + výsledky harnessu S1.

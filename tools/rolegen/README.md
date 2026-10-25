# rolegen – z definic rolí vznikají konfigurace všech vrstev

První „zakázka“, kterou platforma staví sama sobě (fáze P0, `knowledge/platforma/produkt.md`): **jeden zdroj pravdy
`knowledge/organization/roles/*.yaml`** (schéma `role.md` §2) → konfigurace pro OPA, agentgateway, sandbox-runtime,
Claude Code, Kubernetes, Inspect AI a registr agentů. Každý výstup ověřuje **nástroj té vrstvy**, ne generátor sám.

```bash
python3 rolegen.py --roles ../../knowledge/organization/roles --out build --tenant acme --zakazka Z1
```

| Výstup | Pro vrstvu | Ověřeno čím |
|---|---|---|
| `build/opa/data.json` (`data.roles.<role>`) + `policies/roles.rego` (jedna politika `authz.decision`) | identita (gateway extAuthz, hook Agent SDK, PEP paměti) | OPA: 17 případů podle `autonomie.md` |
| `build/agentgateway/apikeys-<tenant>-<zakazka>.yaml` (`policies.apiKey.keys[].budgets`), `egress-allowlist.yaml` (`tcpRoutes.hostnames`) | gateway a FinOps, egress | `agentgateway --validate-only` |
| `build/srt/<role>.json` | sandbox (srt settings) | `srt -s … -c echo` |
| `build/claude/<role>-managed-settings.json` | Claude Code managed settings | – (JSON) |
| `build/k8s/<role>-pod.yaml` | sandbox (Kata, non-root, SA token off, drop ALL, seccomp Localhost) | kontrola polí |

P2-2 (2026-10-25): `build/images/<role>/` = obraz role (Dockerfile vrstvy nad obrazem platformy, devcontainer.json, `etc/platform/*`), `render_k8s.py` → `infra/images/roles/`, CI `images.yml` → `roles/<role>:<verze>` v ACR; `build/k8s/<role>-pod.yaml` je od P2-2 skutečná šablona podu role (`role_pod.py` ji doplní o běh).

P2-1 (2026-10-25): `render_k8s.py` převádí build na manifesty `infra/k8s/rolegen/` (ConfigMap `rolegen-build` vč. `apikeys-template.yaml`, patch `agentgateway-config`); CI `rolegen.yml` selže, když manifesty neodpovídají rolím (`--check`); po merge je aplikuje Flux. Klíče per zakázka ze šablony vydává aplikace (`tools/harness_p0_o2/gateway_keys.py`).

P1-6 (2026-10-25): pody rolí na AKS zakládá aplikace zakázky (`tools/harness_p0_o2/role_pod.py`) se stejnými poli, ale spec staví z env, ne z `build/k8s/<role>-pod.yaml`; srt settings a ClaudeAgentOptions bere z ConfigMapy `rolegen-build` (`srt-<role>.json`, `<role>.json`). Sjednocení na jeden zdroj (`k8s/<role>-pod.yaml` jako šablona podu) = P2. R1 běží v CI (workflow `measure`, krok „R1 – rolegen bundle v CI“, 0,2 s).
| `build/inspect/<role>-approval.yaml`, `<role>-evals.json` | evaluace (approval policy, vrstvy L0–L4 s gate) | `inspect_ai.approval_policies_from_config` |
| `build/registry/roles.json` | registr agentů (T12), řádky `org.role_definitions` | sha zdroje, verze, vlastník |
| `build/agent_sdk/<role>.json` | runtime role (`ClaudeAgentOptions`: `tools=[]`, `strict_mcp_config`, `setting_sources=[]`, `cwd`, MCP servery) – harness O-2 je načítá přes `P0_ROLE_OPTIONS` | R1g + O-2 scénář sre |

## Výsledek harnessu R1 (2026-10-23)

| Check | Tvrzení | Výsledek |
|---|---|---|
| R1a | Generování deterministické (dva běhy = stejný hash), registr nese verzi, vlastníka, SPIFFE ID, sha zdroje – 5 rolí (2026-10-24) | ✅ |
| R1b | OPA (24 případů vč. SRE 2026-10-24: `deploy.plan` ✅, `deploy.apply` jen se schválením, `destroy`/`k8s_raw.exec` ✗, push ✗, runbook GET ✅, approve paměti ✗): vývojář čte repo ✅, zapisuje ✗, merguje ✗, přiřazuje issue ✗ (příloha III), push na větev zakázky ✅, push do main ✗, cizí tenant ✗, schvaluje paměť ✗, navrhuje poučení ✅, čte personal ✗, vypíná sandbox ✗; reviewer schvaluje firma/internal ✅, personal ✗, push ✗, merge ✗, forget ✗; neznámá role ✗ | ✅ 17/17 |
| R1c | srt 0.0.81 přijme settings obou rolí | ✅ |
| R1d | agentgateway 1.6.0 přijme klíče s rozpočty (USD, 24h/30d, Audit/Block) a egress route | ✅ |
| R1e | Inspect načte approval policy (reviewer dostal výchozí: `*git-receive-pack*` → reject) | ✅ |
| R1f | Pod spec: Kata RuntimeClass, non-root, SA token off, drop ALL, seccomp Localhost | ✅ |
| R1g | `ClaudeAgentOptions` rolí: žádné vestavěné nástroje CLI, strict MCP, bez user/project settings, cwd mimo repo | ✅ |

Soubory: `results/r1-20261024-052755.json` (3 role, 2026-10-24), `results/r1-20261023-224112.json`. Adresář `build/` je generovaný, není v gitu.

## Pasti

- Rego: package nesmí být `roles`, když data mají kořen `roles` – `data.roles.decision` → rekurze. Politika je `package authz`.
- Pravidla `tool_allowed` a `dangerous_tool_input` se překrývala → OPA vrátí konflikt (null). Allow pravidla mají `not dangerous`.
- agentgateway: klíč s `budgets` **musí mít `metadata.name`** a **budgets vyžadují `config.database`** (sqlite/postgres) – jinak `--validate-only` padá.
- Hodnoty klíčů gateway negeneruj: do configu patří `keyHash` (`sha256:<hex>`), hodnotu vydává OpenBao; placeholder v buildu je jen název klíče.
- Role bez `inspect_approval_policy` dostane výchozí (push přes nástroj role nikdy) – explicitně prázdný seznam neexistuje.

"""
render_k8s.py – z výstupu rolegen vyrobí Kubernetes manifesty do infra/k8s/rolegen/ (P2-1: role → Git → Flux, harness už konfiguraci nenosí).

  rolegen-build.yaml        ConfigMap `rolegen-build`: <role>.json (ClaudeAgentOptions), srt-<role>.json, roles.json (registr), opa-data.json,
                            apikeys-template.yaml (policies.apiKey.keys[] s rozpočty per role a placeholderem {zakazka} – klíče per zakázka
                            vydává aplikace při založení zakázky, viz tools/harness_p0_o2/gateway_keys.py)
  infra/images/roles/<role>/  Dockerfile, devcontainer.json, etc/platform/{role.json,srt.json,managed-settings.json} – obraz role (P2-2)
  agentgateway-config.yaml  ConfigMap `agentgateway-config` = base config (infra/k8s/base/agentgateway) + upstream z env $LLM_UPSTREAM_URL
                            + prázdná apiKey policy (mode optional) – component ho aplikuje jako patch base ConfigMapy (overlaye: components: [../../rolegen])

Spuštění: python tools/rolegen/render_k8s.py [--check]   (--check: nic nezapisuje, exit 1 když se vygenerované soubory liší od Gitu – CI gate)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "infra/k8s/rolegen"
IMG = ROOT / "infra/images/roles"   # P2-2: Dockerfile + devcontainer.json + etc/platform per role (az acr build v images.yml)
HEADER = "# GENEROVÁNO: python tools/rolegen/render_k8s.py z knowledge/organization/roles/*.yaml – neupravovat ručně (CI kontroluje `--check`).\n"


def render(tenant="acme"):
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, str(HERE / "rolegen.py"), "--roles", str(ROOT / "knowledge/organization/roles"), "--out", td, "--tenant", tenant, "--zakazka", "{zakazka}"], capture_output=True, text=True)
        if r.returncode != 0: raise SystemExit(f"rolegen selhal:\n{r.stderr}")
        b = Path(td)
        data = {}
        for f in sorted((b / "agent_sdk").glob("*.json")): data[f.name] = f.read_text()
        for f in sorted((b / "srt").glob("*.json")): data[f"srt-{f.name}"] = f.read_text()
        for f in sorted((b / "k8s").glob("*-pod.yaml")): data[f"pod-{f.name.replace('-pod.yaml', '')}.yaml"] = f.read_text()   # P2-2: šablona podu role pro role_pod.py
        data["roles.json"] = (b / "registry/roles.json").read_text()
        images = {}
        for d in sorted((b / "images").iterdir()):
            for f in sorted(d.rglob("*")):
                if f.is_file(): images[f"{d.name}/{f.relative_to(d)}"] = f.read_text()
        data["opa-data.json"] = (b / "opa/data.json").read_text()
        tpl = yaml.safe_load((b / f"agentgateway/apikeys-{tenant}-{{zakazka}}.yaml").read_text())
        tpl["policies"]["apiKey"]["mode"] = "optional"   # bez klíče projde request bez role (harnessy G1); klíče rolí jsou strict per budget
        data["apikeys-template.yaml"] = yaml.safe_dump(tpl, sort_keys=False, allow_unicode=True)
    # Flux postBuild.substitute by nedefinované ${VAR} v datech (env rolí, např. ${SVID_JWT}) nahradil prázdným řetězcem (P21a 2026-10-25) → vypnout
    build_cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "rolegen-build", "annotations": {"kustomize.toolkit.fluxcd.io/substitute": "disabled"}}, "data": data}
    base_cm = next(d for d in yaml.safe_load_all((ROOT / "infra/k8s/base/agentgateway/agentgateway.yaml").read_text()) if d and d.get("kind") == "ConfigMap" and d["metadata"]["name"] == "agentgateway-config")
    cfg = yaml.safe_load(base_cm["data"]["config.yaml"])
    cfg["llm"]["models"][0]["params"]["baseUrl"] = "$LLM_UPSTREAM_URL"   # env gateway (Deployment): aks mock-upstream v clusteru / živé API
    cfg["llm"]["policies"] = {"apiKey": {"mode": "optional", "location": tpl["policies"]["apiKey"]["location"], "keys": []}}   # klíče doplní aplikace per zakázka
    gw_cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "agentgateway-config"}, "data": {"config.yaml": yaml.safe_dump(cfg, sort_keys=False)}}
    return images, {"rolegen-build.yaml": HEADER + yaml.safe_dump(build_cm, sort_keys=False, allow_unicode=True),
            "agentgateway-config.yaml": HEADER + yaml.safe_dump(gw_cm, sort_keys=False),
            # Component (ne Kustomization): patch base ConfigMapy gateway smí ležet jen pod adresářem kustomizace, component ho může nést sám
            "kustomization.yaml": HEADER + yaml.safe_dump({"apiVersion": "kustomize.config.k8s.io/v1alpha1", "kind": "Component", "resources": ["rolegen-build.yaml"], "patches": [{"path": "agentgateway-config.yaml"}]}, sort_keys=False)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); ap.add_argument("--tenant", default="acme"); a = ap.parse_args()
    images, files = render(a.tenant)
    OUT.mkdir(parents=True, exist_ok=True); IMG.mkdir(parents=True, exist_ok=True)
    targets = {OUT / n: c for n, c in files.items()} | {IMG / n: c for n, c in images.items()}
    extra = [str(f.relative_to(ROOT)) for f in IMG.rglob("*") if f.is_file() and f not in targets]   # soubory obrazů, které už rolegen negeneruje
    stale = [str(f.relative_to(ROOT)) for f, c in targets.items() if not f.exists() or f.read_text() != c] + extra
    if a.check:
        if stale: print(json.dumps({"stale": stale, "hint": "python tools/rolegen/render_k8s.py && git add infra/k8s/rolegen infra/images/roles"})); sys.exit(1)
        print(json.dumps({"ok": True, "files": len(targets)})); return
    for f in extra: Path(ROOT / f).unlink()
    for f, c in targets.items(): f.parent.mkdir(parents=True, exist_ok=True); f.write_text(c)
    print(json.dumps({"written": len(targets), "changed": stale}))


if __name__ == "__main__":
    main()

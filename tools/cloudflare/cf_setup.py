#!/usr/bin/env python3
"""
P4-10b: Cloudflare pro stálý vstup platformy – pojmenovaný tunnel + Access – založí API (idempotentně) a hodnoty uloží rovnou do Key Vaultu.

Co dělá `setup` (každý krok najde existující objekt, nebo ho založí):
  1. zóna (doména) v účtu Cloudflare → account_id, zone_id (zóna musí být `active`)
  2. Zero Trust organizace (team domain `https://<team>.cloudflareaccess.com`) – když chybí, zkusí ji založit; když to API odmítne,
     musí Adam projít onboarding v dashboardu (team name + Free plán + platební údaje, podle docs i u Free)
  3. identity provider One-time PIN (e-mail OTP)
  4. service token harnessu/operátora (`platforma-harness`; existující se rotuje – secret vydá API jen jednou)
  5. Access aplikace (self-hosted) na `<host>.<zóna>` s policy *Service Auth* (service token) a *Allow* (e-maily, OTP) → AUD tag
  6. pojmenovaný tunnel (remotely-managed) `platforma` + ingress `<host>.<zóna>` → `http://127.0.0.1:8011` → token tunelu
  7. DNS CNAME `<host>` → `<tunnel_id>.cfargotunnel.com` (proxied)
  8. Key Vault: cloudflare-tunnel-token, cloudflare-tunnel-hostname, cloudflare-access-team-domain, cloudflare-access-aud,
     cloudflare-access-client-id, cloudflare-access-client-secret (`az keyvault secret set --file` – hodnota není v argumentech procesu)
`status` jen čte (žádné hodnoty), `teardown` vrátí quick tunnel bez Access (smaže DNS, tunnel, aplikaci, service token; organizace a OTP zůstávají).

Token API: env CLOUDFLARE_API_TOKEN (GitHub secret CLOUDFLARE_ZT_TOKEN) s právy Account: Cloudflare Tunnel Edit, Access: Apps and Policies Edit,
Access: Service Tokens Edit, Access: Organizations, Identity Providers, and Groups Edit; Zone: Zone Read, DNS Edit (jen zóna platformy).
Do logu jdou jen identifikátory (zone_id, app_id, tunnel_id, AUD tag – není tajný), nikdy token tunelu, client secret ani e-maily (jen hash).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("CLOUDFLARE_API_BASE") or "https://api.cloudflare.com/client/v4"   # přepis jen pro lokální test proti falešnému API
ST_NAME = "platforma-harness"
TUNNEL_NAME = "platforma"
APP_NAME = "platforma"
ORIGIN = "http://127.0.0.1:8011"
KV_NAMES = {   # Key Vault secret → content type (shodné s infra/terraform/secrets.tf)
    "cloudflare-tunnel-token": "Cloudflare Tunnel token pojmenovaného tunelu pro sidecar cloudflared aplikace zakázky; 'quick' = quick tunnel *.trycloudflare.com bez účtu",
    "cloudflare-tunnel-hostname": "Veřejný hostname pojmenovaného tunelu (published application) – harness a dokumentace; 'quick' = hostname se čte z logu sidecaru",
    "cloudflare-access-team-domain": "Cloudflare Access (P4-10) team-domain; 'none' = Access není nasazen (quick tunnel). Ostrou hodnotu nastaví Adam, Terraform nepřepisuje",
    "cloudflare-access-aud": "Cloudflare Access (P4-10) aud; 'none' = Access není nasazen (quick tunnel). Ostrou hodnotu nastaví Adam, Terraform nepřepisuje",
    "cloudflare-access-client-id": "Cloudflare Access (P4-10) client-id; 'none' = Access není nasazen (quick tunnel). Ostrou hodnotu nastaví Adam, Terraform nepřepisuje",
    "cloudflare-access-client-secret": "Cloudflare Access (P4-10) client-secret; 'none' = Access není nasazen (quick tunnel). Ostrou hodnotu nastaví Adam, Terraform nepřepisuje",
}


class CfError(Exception):
    pass


def api(method: str, path: str, body=None, params=None):
    """Volání Cloudflare API v4; vrací `result`. Chyba = CfError se zprávami API (bez těla requestu)."""
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not tok:
        raise CfError("CLOUDFLARE_API_TOKEN chybí v prostředí")
    url = f"{API}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "User-Agent": "adam-platforma-cf-setup"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            j = json.load(e)
        except Exception:
            raise CfError(f"{method} {path}: HTTP {e.code}") from None
        msgs = "; ".join(f"{x.get('code')}: {x.get('message')}" for x in (j.get("errors") or [])) or f"HTTP {e.code}"
        raise CfError(f"{method} {path}: {msgs}") from None
    if not j.get("success", True):
        raise CfError(f"{method} {path}: " + "; ".join(f"{x.get('code')}: {x.get('message')}" for x in (j.get("errors") or [])))
    return j.get("result")


def h(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()[:12]


# --- Key Vault (identita runneru: Key Vault Secrets Officer z Terraformu) ---------------------------------------------------------------
def kv_set(kv: str, name: str, value: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(value); tmp = f.name
    try:
        r = subprocess.run(["az", "keyvault", "secret", "set", "--vault-name", kv, "-n", name, "--file", tmp, "--encoding", "utf-8", "--content-type", KV_NAMES[name], "-o", "none"], capture_output=True, text=True, timeout=180)
    finally:
        os.unlink(tmp)
    if r.returncode == 0:
        return "ok"
    err = (r.stderr or "").strip().splitlines()
    return "chyba: " + (err[-1][:200] if err else f"exit {r.returncode}")


def kv_attrs(kv: str, name: str):
    r = subprocess.run(["az", "keyvault", "secret", "show", "--vault-name", kv, "-n", name, "--query", "{contentType:contentType,updated:attributes.updated}", "-o", "json"], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return {"error": (r.stderr or "").strip().splitlines()[-1][:160] if (r.stderr or "").strip() else f"exit {r.returncode}"}
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"error": "json"}


def kv_value(kv: str, name: str):
    """Jen pro ne-tajné hodnoty (hostname, aud, team domain) – kontrola shody s Cloudflare."""
    r = subprocess.run(["az", "keyvault", "secret", "show", "--vault-name", kv, "-n", name, "--query", "value", "-o", "tsv"], capture_output=True, text=True, timeout=120)
    return r.stdout.strip() if r.returncode == 0 else None


# --- Cloudflare objekty -----------------------------------------------------------------------------------------------------------------
def zone(name: str):
    """Zóna a účet. Bez zónových práv tokenu (Zone Read / DNS Edit) se účet vezme z GET /accounts a DNS se přeskočí – CNAME pak nakliká Adam ručně
    (skript vypíše cíl `<tunnel_id>.cfargotunnel.com`)."""
    try:
        zs = api("GET", "/zones", params={"name": name}) or []
    except CfError as e:
        zs = None; err = str(e)
    if zs:
        z = zs[0]
        return {"zone_id": z["id"], "account_id": z["account"]["id"], "status": z.get("status"), "name_servers": z.get("name_servers")}
    if zs == [] :
        raise CfError(f"zóna {name} v účtu není (nebo token nemá Zone Read na ni) – doménu přidat do Cloudflare (Add a domain) nebo koupit přes Registrar")
    accs = api("GET", "/accounts") or []
    if not accs:
        raise CfError(f"token nemá Zone Read ({err}) a GET /accounts nic nevrátil – přidat do tokenu scope zóny {name} (Zone Read, DNS Edit)")
    return {"zone_id": None, "account_id": accs[0]["id"], "status": "no-zone-scope", "name_servers": None, "note": f"token bez zónových práv ({err[:120]}) – DNS CNAME ručně"}


def organization(acc: str, team: str | None, create: bool):
    try:
        org = api("GET", f"/accounts/{acc}/access/organizations")
    except CfError as e:
        org = None; err = str(e)
    if org and org.get("auth_domain"):
        return {"auth_domain": org["auth_domain"], "name": org.get("name"), "created": False}
    if not create:
        return {"auth_domain": None, "missing": True}
    body = {"name": team or "platforma"}
    if team:
        body["auth_domain"] = f"{team}.cloudflareaccess.com"
    try:
        org = api("POST", f"/accounts/{acc}/access/organizations", body)
        return {"auth_domain": org.get("auth_domain"), "name": org.get("name"), "created": True}
    except CfError as e:
        raise CfError("Zero Trust organizace chybí a API ji nezaložilo (" + str(e) + ") → Adam: dashboard → Zero Trust → onboarding: team name, Free plán, platební údaje (docs: i u Free); pak workflow spustit znovu")


def otp_idp(acc: str):
    for i in api("GET", f"/accounts/{acc}/access/identity_providers") or []:
        if i.get("type") == "onetimepin":
            return {"id": i["id"], "created": False}
    i = api("POST", f"/accounts/{acc}/access/identity_providers", {"name": "One-time PIN", "type": "onetimepin", "config": {}})
    return {"id": i["id"], "created": True}


def service_token(acc: str):
    """Existující token rotuje (secret vydá API jen při create/rotate), jinak založí. Vrací i tajemství – volající je zapíše do Key Vaultu, nikam jinam."""
    cur = next((t for t in (api("GET", f"/accounts/{acc}/access/service_tokens") or []) if t.get("name") == ST_NAME), None)
    if cur:
        try:
            t = api("POST", f"/accounts/{acc}/access/service_tokens/{cur['id']}/rotate", {})
            if t and t.get("client_secret"):
                return {"id": t.get("id") or cur["id"], "client_id": t.get("client_id") or cur.get("client_id"), "client_secret": t["client_secret"], "op": "rotate", "expires_at": t.get("expires_at") or cur.get("expires_at")}
        except CfError as e:
            print(f"  service token rotate selhal ({e}) → delete + create", flush=True)
        api("DELETE", f"/accounts/{acc}/access/service_tokens/{cur['id']}")
    t = api("POST", f"/accounts/{acc}/access/service_tokens", {"name": ST_NAME, "duration": "8760h"})
    return {"id": t["id"], "client_id": t["client_id"], "client_secret": t["client_secret"], "op": "create", "expires_at": t.get("expires_at")}


def access_app(acc: str, fqdn: str, idp_id: str, st_id: str, emails: list[str]):
    """Self-hosted aplikace na hostname: policy 1 Service Auth (service token harnessu), policy 2 Allow e-maily (OTP). Existující aplikaci přepíše stejným tělem (PUT)."""
    cur = next((a for a in (api("GET", f"/accounts/{acc}/access/apps") or []) if a.get("domain") == fqdn or any((d or {}).get("uri") == fqdn for d in (a.get("destinations") or []))), None)
    policies = [{"name": "harness service token", "decision": "non_identity", "precedence": 1, "include": [{"service_token": {"token_id": st_id}}]}]
    if emails:
        policies.append({"name": "lide OTP", "decision": "allow", "precedence": 2, "include": [{"email": {"email": e}} for e in emails]})
    elif cur:   # bez zadaných e-mailů zachovat existující Allow policy (rozšíření o další lidi = zadat všechny)
        for p in (api("GET", f"/accounts/{acc}/access/apps/{cur['id']}/policies") or []):
            if p.get("decision") == "allow":
                policies.append({"name": p.get("name") or "lide OTP", "decision": "allow", "precedence": 2, "include": p.get("include") or []})
                break
    body = {"name": APP_NAME, "type": "self_hosted", "domain": fqdn, "destinations": [{"type": "public", "uri": fqdn}], "session_duration": "24h",
            "allowed_idps": [idp_id], "auto_redirect_to_identity": True, "app_launcher_visible": False, "service_auth_401_redirect": False,
            "http_only_cookie_attribute": True, "policies": policies}
    a = api("PUT", f"/accounts/{acc}/access/apps/{cur['id']}", body) if cur else api("POST", f"/accounts/{acc}/access/apps", body)
    return {"id": a["id"], "aud": a.get("aud"), "domain": a.get("domain"), "created": not cur, "policies": [(p.get("name"), p.get("decision")) for p in (a.get("policies") or [])], "humans": len(emails)}


def tunnel(acc: str, fqdn: str):
    cur = next((t for t in (api("GET", f"/accounts/{acc}/cfd_tunnel", params={"name": TUNNEL_NAME, "is_deleted": "false"}) or []) if t.get("name") == TUNNEL_NAME), None)
    t = cur or api("POST", f"/accounts/{acc}/cfd_tunnel", {"name": TUNNEL_NAME, "config_src": "cloudflare"})
    api("PUT", f"/accounts/{acc}/cfd_tunnel/{t['id']}/configurations", {"config": {"ingress": [{"hostname": fqdn, "service": ORIGIN}, {"service": "http_status:404"}]}})
    token = api("GET", f"/accounts/{acc}/cfd_tunnel/{t['id']}/token")
    return {"id": t["id"], "created": not cur, "status": t.get("status"), "token": token if isinstance(token, str) else (token or {}).get("token")}


def dns(zone_id: str, fqdn: str, tunnel_id: str):
    target = f"{tunnel_id}.cfargotunnel.com"
    recs = api("GET", f"/zones/{zone_id}/dns_records", params={"name": fqdn}) or []
    cur = next((r for r in recs if r.get("type") == "CNAME"), None)
    other = [r for r in recs if r.get("type") != "CNAME"]
    for r in other:   # A/AAAA na stejném jméně by CNAME blokovaly
        api("DELETE", f"/zones/{zone_id}/dns_records/{r['id']}")
    if cur and cur.get("content") == target and cur.get("proxied"):
        return {"id": cur["id"], "op": "keep", "target": target}
    if cur:
        r = api("PATCH", f"/zones/{zone_id}/dns_records/{cur['id']}", {"content": target, "proxied": True, "ttl": 1})
        return {"id": r["id"], "op": "update", "target": target}
    r = api("POST", f"/zones/{zone_id}/dns_records", {"type": "CNAME", "name": fqdn, "content": target, "proxied": True, "ttl": 1, "comment": "P4-10 pojmenovaný tunnel platformy"})
    return {"id": r["id"], "op": "create", "target": target}


# --- akce -------------------------------------------------------------------------------------------------------------------------------
def setup(a):
    fqdn = f"{a.host}.{a.zone}"; out = {"fqdn": fqdn}
    z = zone(a.zone); out["zone"] = {k: v for k, v in z.items() if k != "account_id"}; acc = z["account_id"]
    if z.get("zone_id") and z.get("status") != "active":
        raise CfError(f"zóna {a.zone} není active ({z.get('status')}) – nameservery u registrátora musí mířit na {z.get('name_servers')}")
    out["organization"] = organization(acc, a.team, create=True); team_domain = "https://" + out["organization"]["auth_domain"]
    out["otp"] = otp_idp(acc)
    st = service_token(acc); out["service_token"] = {k: v for k, v in st.items() if k not in ("client_id", "client_secret")}
    emails = [e.strip() for e in (a.email or "").split(",") if e.strip()]; out["emails_hash"] = [h(e) for e in emails]
    out["app"] = access_app(acc, fqdn, out["otp"]["id"], st["id"], emails)
    tn = tunnel(acc, fqdn); out["tunnel"] = {k: v for k, v in tn.items() if k != "token"}
    out["dns"] = dns(z["zone_id"], fqdn, tn["id"]) if z.get("zone_id") else {"op": "manual", "todo": f"DNS → Records → CNAME `{a.host}` → `{tn['id']}.cfargotunnel.com`, Proxied (token nemá práva na zónu)"}
    if a.kv:
        vals = {"cloudflare-tunnel-token": tn["token"], "cloudflare-tunnel-hostname": fqdn, "cloudflare-access-team-domain": team_domain, "cloudflare-access-aud": out["app"]["aud"],
                "cloudflare-access-client-id": st["client_id"], "cloudflare-access-client-secret": st["client_secret"]}
        missing = [k for k, v in vals.items() if not v]
        if missing:
            raise CfError(f"chybí hodnoty pro Key Vault: {missing}")
        out["key_vault"] = {k: kv_set(a.kv, k, v) for k, v in vals.items()}
    else:
        out["key_vault"] = "přeskočeno (--kv chybí)"
    out["gui"] = f"https://{fqdn}/gui"
    return out


def status(a):
    fqdn = f"{a.host}.{a.zone}"; out = {"fqdn": fqdn}
    z = zone(a.zone); out["zone"] = {k: v for k, v in z.items() if k != "account_id"}; acc = z["account_id"]
    out["organization"] = organization(acc, None, create=False)
    out["otp"] = any(i.get("type") == "onetimepin" for i in (api("GET", f"/accounts/{acc}/access/identity_providers") or []))
    st = next((t for t in (api("GET", f"/accounts/{acc}/access/service_tokens") or []) if t.get("name") == ST_NAME), None)
    out["service_token"] = {"id": st["id"], "expires_at": st.get("expires_at")} if st else None
    app = next((x for x in (api("GET", f"/accounts/{acc}/access/apps") or []) if x.get("domain") == fqdn or any((d or {}).get("uri") == fqdn for d in (x.get("destinations") or []))), None)
    if app:
        pols = api("GET", f"/accounts/{acc}/access/apps/{app['id']}/policies") or []
        out["app"] = {"id": app["id"], "aud": app.get("aud"), "policies": [(p.get("name"), p.get("decision"), len(p.get("include") or [])) for p in pols], "allowed_idps": len(app.get("allowed_idps") or [])}
    else:
        out["app"] = None
    tn = next((t for t in (api("GET", f"/accounts/{acc}/cfd_tunnel", params={"name": TUNNEL_NAME, "is_deleted": "false"}) or []) if t.get("name") == TUNNEL_NAME), None)
    if tn:
        cfg = (api("GET", f"/accounts/{acc}/cfd_tunnel/{tn['id']}/configurations") or {}).get("config") or {}
        out["tunnel"] = {"id": tn["id"], "status": tn.get("status"), "connections": len(tn.get("connections") or []), "ingress": [(i.get("hostname"), i.get("service")) for i in (cfg.get("ingress") or [])]}
        recs = (api("GET", f"/zones/{z['zone_id']}/dns_records", params={"name": fqdn}) or []) if z.get("zone_id") else None
        out["dns"] = [(r.get("type"), r.get("content"), r.get("proxied")) for r in recs] if recs is not None else f"bez zónových práv – očekávaný CNAME {tn['id']}.cfargotunnel.com"
    else:
        out["tunnel"] = None; out["dns"] = None
    if a.kv:
        out["key_vault"] = {n: kv_attrs(a.kv, n) for n in KV_NAMES}
        out["key_vault_matches"] = {"hostname": kv_value(a.kv, "cloudflare-tunnel-hostname") == fqdn, "aud": bool(app) and kv_value(a.kv, "cloudflare-access-aud") == app.get("aud"),
                                    "team_domain": kv_value(a.kv, "cloudflare-access-team-domain") == ("https://" + (out["organization"].get("auth_domain") or "-"))}
    return out


def teardown(a):
    fqdn = f"{a.host}.{a.zone}"; out = {"fqdn": fqdn}
    z = zone(a.zone); acc = z["account_id"]
    for r in (api("GET", f"/zones/{z['zone_id']}/dns_records", params={"name": fqdn}) or []) if z.get("zone_id") else []:
        api("DELETE", f"/zones/{z['zone_id']}/dns_records/{r['id']}"); out.setdefault("dns_deleted", []).append(r.get("type"))
    if not z.get("zone_id"):
        out["dns"] = f"bez zónových práv – CNAME {a.host} smazat ručně"
    for t in api("GET", f"/accounts/{acc}/cfd_tunnel", params={"name": TUNNEL_NAME, "is_deleted": "false"}) or []:
        if t.get("name") != TUNNEL_NAME:
            continue
        try:
            api("DELETE", f"/accounts/{acc}/cfd_tunnel/{t['id']}/connections")
        except CfError as e:
            out["tunnel_connections"] = str(e)[:160]
        api("DELETE", f"/accounts/{acc}/cfd_tunnel/{t['id']}"); out["tunnel_deleted"] = t["id"]
    for x in api("GET", f"/accounts/{acc}/access/apps") or []:
        if x.get("domain") == fqdn or any((d or {}).get("uri") == fqdn for d in (x.get("destinations") or [])):
            api("DELETE", f"/accounts/{acc}/access/apps/{x['id']}"); out["app_deleted"] = x["id"]
    for t in api("GET", f"/accounts/{acc}/access/service_tokens") or []:
        if t.get("name") == ST_NAME:
            api("DELETE", f"/accounts/{acc}/access/service_tokens/{t['id']}"); out["service_token_deleted"] = t["id"]
    if a.kv:
        out["key_vault"] = {n: kv_set(a.kv, n, "quick" if n.startswith("cloudflare-tunnel") else "none") for n in KV_NAMES}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--action", choices=["setup", "status", "teardown"], default="status")
    p.add_argument("--zone", required=True, help="doména (zóna) v účtu Cloudflare, např. autonomous.place")
    p.add_argument("--host", default="platforma", help="subdoména GUI (jedna úroveň – víceúrovňová potřebuje Advanced Certificate)")
    p.add_argument("--team", default="", help="team name pro založení Zero Trust organizace, když ještě není (jinak se použije existující)")
    p.add_argument("--email", default="", help="e-maily lidí pro Access policy Allow (OTP), oddělené čárkou; prázdné = zachovat existující")
    p.add_argument("--kv", default="", help="jméno Key Vaultu (hodnoty zapsat tam); prázdné = jen Cloudflare")
    a = p.parse_args()
    try:
        out = {"setup": setup, "status": status, "teardown": teardown}[a.action](a)
    except CfError as e:
        print(f"❌ {a.action}: {e}", flush=True); sys.exit(2)
    print(f"✅ {a.action}: " + json.dumps(out, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()

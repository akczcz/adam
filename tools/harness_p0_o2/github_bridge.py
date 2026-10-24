r"""
GitHub → HITL bridge (PEP mezi GitHubem a workflow zakázky). Člověk schvaluje přímo v GitHubu, bridge ověří identitu a vazbu
na artefakt a teprve pak vyvolá schvalovací event (app podepíše approval token – OpenBao transit v cíli).

Pravidla (knowledge/organization/procesy.md „HITL přes GitHub“):
  H1 Schválení zadání   = komentář `/schvaluji` na issue zakázky od člověka z allow-listu (ne od bota, ne od autora issue = platformy)
  H4 Schválení merge    = PR review APPROVED od člověka z allow-listu, jehož commit_id == aktuální head SHA PR (review na starý commit neplatí)
  stop                  = komentář `/stop` na issue → pause zakázky
Vazba na artefakt: hash z těla issue/PR (`hash \`<16 hex>\``), zapsaný platformou při publikaci. Každá GitHub událost se zpracuje
nejvýš jednou (dedup podle id). Dva vstupy, stejný handler: polling (REST, interval POLL_S) a webhook (HMAC X-Hub-Signature-256).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

GH = os.environ.get("P0_GITHUB_API", "https://api.github.com"); REPO = os.environ.get("P0_GITHUB_REPO", "akczcz/adam")
APP = os.environ["BRIDGE_APP_URL"]; HUMANS = set(os.environ.get("P0_HUMANS", "adam").split(","))
BOT = os.environ.get("P0_BOT_LOGIN", "platform-bot"); POLL_S = float(os.environ.get("BRIDGE_POLL_S", "2"))
WEBHOOK_SECRET = os.environ.get("BRIDGE_WEBHOOK_SECRET", "").encode()
TOKEN = os.environ.get("GITHUB_TOKEN", "mock")
LEDGER = os.environ.get("BRIDGE_LEDGER", "logs/bridge.jsonl")
app = FastAPI(); SEEN = set(); LOCK = threading.Lock()


def log(kind, **kw):
    with open(LEDGER, "a") as f: f.write(json.dumps({"ts": time.time(), "kind": kind, **kw}, ensure_ascii=False) + "\n")


def gh(path):
    return httpx.get(f"{GH}/repos/{REPO}{path}", headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}, timeout=10).json()


def published():
    """Mapování zakázka ↔ issue/PR číslo z ledgeru app (v cíli org.handoffs). Když se číslo opakuje (mock GitHub po restartu čísluje
    od 1, ledger přežívá na PVC), platí nejnovější záznam – starší zakázka mapování ztrácí."""
    out, owner = {}, {}
    for e in httpx.get(f"{APP}/_debug/ledger", timeout=10).json():
        if e.get("kind") == "PUBLISHED" and e.get("number"):
            key = (e["publish_kind"], e["number"])
            if key in owner and owner[key] != e["zakazka"]: out[owner[key]].pop(e["publish_kind"], None)
            owner[key] = e["zakazka"]; out.setdefault(e["zakazka"], {})[e["publish_kind"]] = e["number"]
    return out


def art_hash(body: str):
    m = re.search(r"hash `([0-9a-f]{16})`", body or ""); return m.group(1) if m else None


def approve(zid, bod, by, artifact_hash, source):
    r = httpx.post(f"{APP}/zakazky/{zid}/approve/{bod}", json={"by": by, "by_kind": "human", "artifact_hash": artifact_hash, "exp_s": 86400}, timeout=10)
    log("APPROVAL_FORWARDED", zakazka=zid, bod=bod, by=by, artifact_hash=artifact_hash, source=source, http=r.status_code)


def handle_comment(zid, number, c, issue_body, source):
    key = f"c:{c['id']}"
    with LOCK:
        if key in SEEN: return
        SEEN.add(key)
    login = c["user"]["login"]; body = (c.get("body") or "").strip()
    if not body.startswith("/"): return
    if login == BOT or login not in HUMANS:
        log("REJECTED", zakazka=zid, bod="H1", by=login, reason="not_allowlisted_human", source=source); return
    if body.startswith("/schvaluji"):
        hh = art_hash(issue_body)
        if not hh: log("REJECTED", zakazka=zid, bod="H1", by=login, reason="no_artifact_hash_in_issue", source=source); return
        approve(zid, "H1", login, hh, source)
    elif body.startswith("/stop"):
        r = httpx.post(f"{APP}/zakazky/{zid}/stop", json={"by": login, "reason": body}, timeout=10)
        log("STOP_FORWARDED", zakazka=zid, by=login, http=r.status_code, source=source)


def handle_review(zid, number, rv, pr, source):
    key = f"r:{rv['id']}"
    with LOCK:
        if key in SEEN: return
        SEEN.add(key)
    login = rv["user"]["login"]
    if rv.get("state") != "APPROVED": return
    if login == BOT or login not in HUMANS:
        log("REJECTED", zakazka=zid, bod="H4", by=login, reason="not_allowlisted_human", source=source); return
    head = (pr.get("head") or {}).get("sha")
    if rv.get("commit_id") != head:
        log("REJECTED", zakazka=zid, bod="H4", by=login, reason="review_not_on_head_sha", review_commit=rv.get("commit_id"), head=head, source=source); return
    hh = art_hash(pr.get("body"))
    if not hh: log("REJECTED", zakazka=zid, bod="H4", by=login, reason="no_artifact_hash_in_pr", source=source); return
    approve(zid, "H4", login, hh, source)


def poll():
    while True:
        try:
            for zid, nums in published().items():
                if "issue" in nums:
                    issue = gh(f"/issues/{nums['issue']}")
                    for c in gh(f"/issues/{nums['issue']}/comments"): handle_comment(zid, nums["issue"], c, issue.get("body", ""), "poll")
                if "pull_request" in nums:
                    pr = gh(f"/pulls/{nums['pull_request']}")
                    for rv in gh(f"/pulls/{nums['pull_request']}/reviews"): handle_review(zid, nums["pull_request"], rv, pr, "poll")
        except Exception as e:
            log("POLL_ERROR", error=str(e)[:200])
        time.sleep(POLL_S)


@app.post("/webhook")
async def webhook(req: Request, x_hub_signature_256: str | None = Header(None), x_github_event: str = Header("")):
    raw = await req.body()
    want = "sha256=" + hmac.new(WEBHOOK_SECRET, raw, hashlib.sha256).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(want, x_hub_signature_256):
        log("WEBHOOK_REJECTED", reason="bad_signature", event=x_github_event); raise HTTPException(401, "bad signature")
    p = json.loads(raw); pub = published()
    if x_github_event == "issue_comment":
        n = p["issue"]["number"]; zid = next((z for z, v in pub.items() if v.get("issue") == n), None)
        if zid: handle_comment(zid, n, p["comment"], p["issue"].get("body", ""), "webhook")
    elif x_github_event == "pull_request_review":
        n = p["pull_request"]["number"]; zid = next((z for z, v in pub.items() if v.get("pull_request") == n), None)
        if zid: handle_review(zid, n, p["review"], p["pull_request"], "webhook")
    log("WEBHOOK_OK", event=x_github_event)
    return {"ok": True}


@app.get("/health")
async def health(): return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    threading.Thread(target=poll, daemon=True).start()
    uvicorn.run(app, host=os.environ.get("BRIDGE_HOST", "127.0.0.1"), port=int(os.environ.get("BRIDGE_PORT", "9802")), log_level="warning")

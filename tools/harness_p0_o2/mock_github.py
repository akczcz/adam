"""
Mock GitHub REST API pro harness O-2 scénář github-hitl: issues, komentáře, git objekty, pull requesty, reviews, merge.
Stejná cesta kódu jako proti api.github.com (app.gh_api s P0_GITHUB_API). Autor zápisu = hlavička X-Mock-User (výchozí platform-bot).
GET /_debug/state vrací vše. P2-4: git smart HTTP (`/{o}/{r}.git/...` přes `git http-backend`, bare repa s pre-receive hookem na povolené větve),
GET /_debug/git vrací refy a zaznamenané git requesty (schéma Authorization + otisk tokenu, který vložila gateway).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
import uuid

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

app = FastAPI()
S = {"issues": {}, "comments": {}, "refs": {"main": "0" * 40}, "commits": {"0" * 40: {"tree": "t0", "parents": []}}, "blobs": {}, "trees": {}, "pulls": {}, "reviews": {}, "n": 0, "events": [], "git_requests": []}
WEBHOOK = os.environ.get("MOCK_GH_WEBHOOK")            # URL bridge; když je nastavená, mock posílá podepsané webhooky
SECRET = os.environ.get("MOCK_GH_WEBHOOK_SECRET", "").encode()
# P2-4: git smart HTTP (clone/push z podu role přes gateway) – bare repa pod GIT_ROOT obsluhuje `git http-backend` (CGI). Pre-receive hook
# pouští jen větve s povoleným prefixem (branch protection jako na GitHubu: main/release odmítne server, ne gateway – ref je v těle pkt-line).
GIT_ROOT = os.environ.get("MOCK_GIT_ROOT", "/tmp/mock-git"); GIT_REPOS = [x for x in os.environ.get("MOCK_GIT_REPOS", "acme/platform").split(",") if x]
BRANCH_ALLOW = os.environ.get("MOCK_GIT_BRANCH_ALLOW", "refs/heads/agent/,refs/heads/zakazka/")
HOOK = """#!/bin/sh
# pre-receive (mock GitHub, P2-4): push jen na větve s prefixem %s – ostatní refy (main, release/*) jsou chráněné
status=0
while read old new ref; do
  ok=0
  for p in $(echo "%s" | tr ',' ' '); do case "$ref" in "$p"*) ok=1;; esac; done
  [ "$ok" = 1 ] || { echo "platform: ref $ref je chráněný – push jen na %s*" >&2; status=1; }
done
exit $status
"""


def git_init():
    for repo in GIT_REPOS:
        d = f"{GIT_ROOT}/{repo}.git"
        if os.path.exists(d): continue
        os.makedirs(d, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", d], check=True)
        subprocess.run(["git", "-C", d, "config", "http.receivepack", "true"], check=True)
        w = tempfile.mkdtemp(); genv = {"GIT_AUTHOR_NAME": "platform-bot", "GIT_AUTHOR_EMAIL": "bot@platform.internal", "GIT_COMMITTER_NAME": "platform-bot", "GIT_COMMITTER_EMAIL": "bot@platform.internal", "PATH": os.environ.get("PATH", ""), "HOME": w}
        subprocess.run(["git", "init", "-q", "-b", "main", w], check=True, env=genv)
        open(f"{w}/README.md", "w").write(f"# {repo}\n\nmock repo platformy (P2-4)\n")
        subprocess.run(["git", "-C", w, "add", "."], check=True, env=genv); subprocess.run(["git", "-C", w, "commit", "-q", "-m", "init"], check=True, env=genv)
        subprocess.run(["git", "-C", w, "push", "-q", d, "main"], check=True, env=genv)
        hook = f"{d}/hooks/pre-receive"; open(hook, "w").write(HOOK % (BRANCH_ALLOW, BRANCH_ALLOW, BRANCH_ALLOW)); os.chmod(hook, 0o755)


@app.api_route("/{o}/{r}.git/{rest:path}", methods=["GET", "POST"])
async def git_http(o: str, r: str, rest: str, req: Request):
    """git smart HTTP přes `git http-backend` (CGI). Zaznamená metodu, cestu a schéma Authorization (token vložila gateway; hodnotu neukládá – jen otisk)."""
    body = await req.body(); auth = req.headers.get("authorization", "")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": GIT_ROOT, "GIT_PROJECT_ROOT": GIT_ROOT, "GIT_HTTP_EXPORT_ALL": "1", "REQUEST_METHOD": req.method, "PATH_INFO": f"/{o}/{r}.git/{rest}",
           "QUERY_STRING": req.url.query or "", "REMOTE_USER": "platform-bot", "REMOTE_ADDR": req.client.host if req.client else "0.0.0.0", "CONTENT_TYPE": req.headers.get("content-type", ""), "CONTENT_LENGTH": str(len(body)),
           "SERVER_PROTOCOL": "HTTP/1.1", "GATEWAY_INTERFACE": "CGI/1.1"}
    for k, v in req.headers.items(): env["HTTP_" + k.upper().replace("-", "_")] = v
    S["git_requests"].append({"ts": time.time(), "method": req.method, "path": env["PATH_INFO"], "query": env["QUERY_STRING"], "auth_scheme": auth.split(" ", 1)[0] if auth else None,
                              "auth_sha256_12": hashlib.sha256(auth.split(" ", 1)[1].encode()).hexdigest()[:12] if " " in auth else None, "forwarded": req.headers.get("x-forwarded-for")})
    del S["git_requests"][:-200]
    p = subprocess.run(["git", "http-backend"], input=body, env=env, capture_output=True, timeout=120)
    head, _, out = p.stdout.partition(b"\r\n\r\n")
    status, headers = 200, {}
    for line in head.decode(errors="replace").split("\r\n"):
        if ":" not in line: continue
        k, v = (x.strip() for x in line.split(":", 1))
        if k.lower() == "status": status = int(v.split()[0])
        elif k.lower() not in ("content-length",): headers[k] = v
    if p.returncode and not head: return Response(p.stderr[-500:], status_code=500)
    return Response(content=out, status_code=status, headers=headers)


@app.get("/_debug/git")
async def dbg_git():
    refs = {}
    for repo in GIT_REPOS:
        d = f"{GIT_ROOT}/{repo}.git"
        r = subprocess.run(["git", "-C", d, "for-each-ref", "--format=%(refname) %(objectname)"], capture_output=True, text=True)
        refs[repo] = dict(l.split(" ", 1) for l in r.stdout.splitlines() if " " in l)
    return {"refs": refs, "branch_allow": BRANCH_ALLOW, "requests": S["git_requests"][-40:]}


def nxt():
    S["n"] += 1; return S["n"]


def sha(x): return hashlib.sha1(json.dumps(x, sort_keys=True).encode() + uuid.uuid4().bytes).hexdigest()


def emit(event, payload):
    S["events"].append({"event": event, "payload": payload, "ts": time.time()})
    if WEBHOOK:
        body = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        try: httpx.post(WEBHOOK, content=body, headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig, "X-GitHub-Delivery": uuid.uuid4().hex, "Content-Type": "application/json"}, timeout=5)
        except Exception: pass


@app.post("/repos/{o}/{r}/issues")
async def create_issue(o, r, req: Request, x_mock_user: str = Header("platform-bot")):
    b = await req.json(); n = nxt()
    S["issues"][n] = {"number": n, "title": b["title"], "body": b.get("body", ""), "labels": b.get("labels", []), "user": {"login": x_mock_user}, "html_url": f"https://github.mock/{o}/{r}/issues/{n}", "state": "open"}
    return S["issues"][n]


@app.post("/repos/{o}/{r}/issues/{n}/comments")
async def create_comment(o, r, n: int, req: Request, x_mock_user: str = Header("platform-bot")):
    b = await req.json(); cid = nxt()
    c = {"id": cid, "body": b["body"], "user": {"login": x_mock_user}, "created_at": time.time()}
    S["comments"].setdefault(n, []).append(c)
    emit("issue_comment", {"action": "created", "issue": {"number": n, "body": S["issues"].get(n, S["pulls"].get(n, {})).get("body", "")}, "comment": c, "repository": {"full_name": f"{o}/{r}"}})
    return c


@app.get("/repos/{o}/{r}/issues/{n}/comments")
async def list_comments(o, r, n: int): return S["comments"].get(n, [])


@app.get("/repos/{o}/{r}/issues/{n}")
async def get_issue(o, r, n: int):
    if n not in S["issues"]: raise HTTPException(404)
    return S["issues"][n]


@app.get("/repos/{o}/{r}/git/ref/heads/{branch:path}")
async def get_ref(o, r, branch):
    if branch not in S["refs"]: raise HTTPException(404, "ref not found")
    return {"ref": f"refs/heads/{branch}", "object": {"sha": S["refs"][branch]}}


@app.get("/repos/{o}/{r}/git/commits/{s}")
async def get_commit(o, r, s):
    if s not in S["commits"]: raise HTTPException(404)
    return {"sha": s, **S["commits"][s], "tree": {"sha": S["commits"][s]["tree"]}}


@app.post("/repos/{o}/{r}/git/blobs")
async def post_blob(o, r, req: Request):
    b = await req.json(); s = sha(b); S["blobs"][s] = b; return {"sha": s}


@app.post("/repos/{o}/{r}/git/trees")
async def post_tree(o, r, req: Request):
    b = await req.json(); s = sha(b); S["trees"][s] = b; return {"sha": s}


@app.post("/repos/{o}/{r}/git/commits")
async def post_commit(o, r, req: Request):
    b = await req.json(); s = sha(b); S["commits"][s] = {"tree": b["tree"], "parents": b.get("parents", []), "message": b["message"]}; return {"sha": s}


@app.post("/repos/{o}/{r}/git/refs")
async def post_ref(o, r, req: Request):
    b = await req.json(); br = b["ref"].replace("refs/heads/", "")
    if br in S["refs"]: raise HTTPException(422, "Reference already exists")
    S["refs"][br] = b["sha"]; return {"ref": b["ref"], "object": {"sha": b["sha"]}}


@app.patch("/repos/{o}/{r}/git/refs/heads/{branch:path}")
async def patch_ref(o, r, branch, req: Request):
    b = await req.json(); S["refs"][branch] = b["sha"]; return {"ref": f"refs/heads/{branch}", "object": {"sha": b["sha"]}}


@app.post("/repos/{o}/{r}/pulls")
async def create_pull(o, r, req: Request, x_mock_user: str = Header("platform-bot")):
    b = await req.json(); n = nxt()
    S["pulls"][n] = {"number": n, "title": b["title"], "body": b.get("body", ""), "head": {"ref": b["head"], "sha": S["refs"].get(b["head"])}, "base": {"ref": b["base"]}, "user": {"login": x_mock_user}, "html_url": f"https://github.mock/{o}/{r}/pull/{n}", "state": "open", "merged": False}
    return S["pulls"][n]


@app.get("/repos/{o}/{r}/pulls/{n}")
async def get_pull(o, r, n: int):
    if n not in S["pulls"]: raise HTTPException(404)
    return S["pulls"][n]


@app.post("/repos/{o}/{r}/pulls/{n}/reviews")
async def create_review(o, r, n: int, req: Request, x_mock_user: str = Header("platform-bot")):
    b = await req.json(); rid = nxt()
    rv = {"id": rid, "state": b.get("event", "COMMENTED").replace("APPROVE", "APPROVED"), "user": {"login": x_mock_user}, "commit_id": b.get("commit_id") or S["pulls"][n]["head"]["sha"], "body": b.get("body", ""), "submitted_at": time.time()}
    S["reviews"].setdefault(n, []).append(rv)
    emit("pull_request_review", {"action": "submitted", "review": rv, "pull_request": S["pulls"][n], "repository": {"full_name": f"{o}/{r}"}})
    return rv


@app.get("/repos/{o}/{r}/pulls/{n}/reviews")
async def list_reviews(o, r, n: int): return S["reviews"].get(n, [])


@app.put("/repos/{o}/{r}/pulls/{n}/merge")
async def merge_pull(o, r, n: int, req: Request):
    if n not in S["pulls"]: raise HTTPException(404)
    p = S["pulls"][n]
    if p["merged"]: raise HTTPException(405, "already merged")
    m = sha({"merge": n}); S["commits"][m] = {"tree": "merged", "parents": [S["refs"]["main"], p["head"]["sha"]], "message": f"Merge PR #{n}"}; S["refs"]["main"] = m
    p["merged"] = True; p["state"] = "closed"; p["merge_commit_sha"] = m
    return {"merged": True, "sha": m, "message": "Pull Request successfully merged"}


@app.get("/_debug/state")
async def dbg(): return S


@app.get("/health")
async def health(): return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    git_init()
    uvicorn.run(app, host=os.environ.get("MOCK_GH_HOST", "127.0.0.1"), port=int(os.environ.get("MOCK_GH_PORT", "9801")), log_level="warning")

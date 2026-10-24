"""
Mock GitHub REST API pro harness O-2 scénář github-hitl: issues, komentáře, git objekty, pull requesty, reviews, merge.
Stejná cesta kódu jako proti api.github.com (app.gh_api s P0_GITHUB_API). Autor zápisu = hlavička X-Mock-User (výchozí platform-bot).
GET /_debug/state vrací vše.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()
S = {"issues": {}, "comments": {}, "refs": {"main": "0" * 40}, "commits": {"0" * 40: {"tree": "t0", "parents": []}}, "blobs": {}, "trees": {}, "pulls": {}, "reviews": {}, "n": 0, "events": []}
WEBHOOK = os.environ.get("MOCK_GH_WEBHOOK")            # URL bridge; když je nastavená, mock posílá podepsané webhooky
SECRET = os.environ.get("MOCK_GH_WEBHOOK_SECRET", "").encode()


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
    uvicorn.run(app, host=os.environ.get("MOCK_GH_HOST", "127.0.0.1"), port=int(os.environ.get("MOCK_GH_PORT", "9801")), log_level="warning")

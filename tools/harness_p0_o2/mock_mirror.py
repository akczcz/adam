"""
Mock mirror balíčků (P2-4): pypi simple index + npm registry pro `mirror.platform.internal` za terminovaným listenerem agentgateway.
Sonda role (role_runner.py) stáhne `platform-hello` přes pip (index /pypi/simple) a npm (registry /npm/). Balíčky se generují při startu
(wheel a tgz v paměti), GET /_debug/requests vrací, co kdo stáhl (metoda, cesta, User-Agent – důkaz, že klient šel přes gateway).
Ostrý provoz: Nexus/Artifactory se stejnou cestou (routa mirror-<tenant> v gateway, jen GET).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tarfile
import time
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

app = FastAPI()
NAME, VER = "platform-hello", "0.1.0"
BASE = os.environ.get("MOCK_MIRROR_URL", "https://mirror.platform.internal")   # URL, pod kterou mirror vidí klient (tarball URL v packumentu)
REQ: list[dict] = []


def build_wheel() -> bytes:
    files = {f"{NAME.replace('-', '_')}/__init__.py": "VERSION = '0.1.0'\n",
             f"{NAME.replace('-', '_')}-{VER}.dist-info/METADATA": f"Metadata-Version: 2.1\nName: {NAME}\nVersion: {VER}\nSummary: mock balíček mirroru platformy (P2-4)\n",
             f"{NAME.replace('-', '_')}-{VER}.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: mock_mirror\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    rec = []
    for n, c in files.items():
        d = hashlib.sha256(c.encode()).digest(); rec.append(f"{n},sha256={base64.urlsafe_b64encode(d).rstrip(b'=').decode()},{len(c.encode())}")
    rec.append(f"{NAME.replace('-', '_')}-{VER}.dist-info/RECORD,,")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in files.items(): z.writestr(zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0)), c)
        z.writestr(zipfile.ZipInfo(f"{NAME.replace('-', '_')}-{VER}.dist-info/RECORD", (2026, 1, 1, 0, 0, 0)), "\n".join(rec) + "\n")
    return buf.getvalue()


def build_tgz() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for n, c in {"package/package.json": json.dumps({"name": NAME, "version": VER, "main": "index.js", "license": "MIT"}), "package/index.js": "module.exports = { hello: 'platform' };\n"}.items():
            ti = tarfile.TarInfo(n); data = c.encode(); ti.size = len(data); ti.mtime = 1767225600; t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


WHEEL = build_wheel(); WHEEL_NAME = f"{NAME.replace('-', '_')}-{VER}-py3-none-any.whl"; WHEEL_SHA = hashlib.sha256(WHEEL).hexdigest()
TGZ = build_tgz(); TGZ_NAME = f"{NAME}-{VER}.tgz"


@app.middleware("http")
async def record(req: Request, call_next):
    REQ.append({"ts": time.time(), "method": req.method, "path": req.url.path, "ua": req.headers.get("user-agent", "")[:80], "via_gateway": "x-forwarded-for" in req.headers or "x-envoy-original-path" in req.headers})
    del REQ[:-200]
    return await call_next(req)


@app.get("/pypi/simple/", response_class=HTMLResponse)
async def simple_index(): return f'<!DOCTYPE html><html><body><a href="{NAME}/">{NAME}</a></body></html>'


@app.get("/pypi/simple/{name}/", response_class=HTMLResponse)
async def simple_project(name: str):
    if name.replace("_", "-").lower() != NAME: raise HTTPException(404)
    return f'<!DOCTYPE html><html><body><h1>Links for {NAME}</h1><a href="{BASE}/pypi/files/{WHEEL_NAME}#sha256={WHEEL_SHA}">{WHEEL_NAME}</a></body></html>'


@app.get("/pypi/files/{fn}")
async def wheel(fn: str):
    if fn != WHEEL_NAME: raise HTTPException(404)
    return Response(WHEEL, media_type="application/octet-stream")


@app.get("/npm/{name}")
async def packument(name: str):
    if name != NAME: raise HTTPException(404)
    return {"name": NAME, "dist-tags": {"latest": VER}, "versions": {VER: {"name": NAME, "version": VER, "main": "index.js",
            "dist": {"tarball": f"{BASE}/npm/{NAME}/-/{TGZ_NAME}", "shasum": hashlib.sha1(TGZ).hexdigest(), "integrity": "sha512-" + base64.b64encode(hashlib.sha512(TGZ).digest()).decode()}}}}


@app.get("/npm/{name}/-/{fn}")
async def tarball(name: str, fn: str):
    if name != NAME or fn != TGZ_NAME: raise HTTPException(404)
    return Response(TGZ, media_type="application/octet-stream")


@app.get("/_debug/requests")
async def dbg(): return {"requests": REQ[-50:], "wheel_sha256": WHEEL_SHA}


@app.get("/health")
async def health(): return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("MOCK_MIRROR_HOST", "127.0.0.1"), port=int(os.environ.get("MOCK_MIRROR_PORT", "9803")), log_level="warning")

"""
Mocky cílů egressu pro harness S1 (jeden proces, tři servery):
  - git backend (plain HTTP, port GIT_PORT): za terminací TLS v agentgateway; zaznamenává Authorization a cestu
  - pkg.harness.test (TLS, port PKG_PORT): passthrough přes CONNECT allow-list gateway (SNI)
  - evil.harness.test (TLS, port EVIL_PORT): exfiltrační cíl – nesmí dostat nic
GET /_debug/requests na git backendu vrací všechny záznamy (všech tří serverů).
"""
from __future__ import annotations

import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LEDGER: list[dict] = []
LOCK = threading.Lock()


def handler(name):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # ticho
            pass

        def _rec(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            with LOCK:
                LEDGER.append({"server": name, "method": self.command, "path": self.path, "host": self.headers.get("Host"),
                               "authorization": self.headers.get("Authorization"), "body": body[:200].decode("utf-8", "replace")})

        def do_GET(self):
            if self.path == "/_debug/requests":
                out = json.dumps(LEDGER).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out); return
            self._rec()
            out = json.dumps({"server": name, "ok": True, "path": self.path}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

        do_POST = do_GET
        do_PUT = do_GET
    return H


def serve(name, port, cert=None, key=None):
    srv = ThreadingHTTPServer(("0.0.0.0", port), handler(name))
    if cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    certs = os.environ["S1_CERTS"]
    serve("git-backend", int(os.environ["GIT_PORT"]))
    serve("pkg", int(os.environ["PKG_PORT"]), f"{certs}/pkg.harness.test.crt", f"{certs}/pkg.harness.test.key")
    serve("evil", int(os.environ["EVIL_PORT"]), f"{certs}/evil.harness.test.crt", f"{certs}/evil.harness.test.key")
    threading.Event().wait()

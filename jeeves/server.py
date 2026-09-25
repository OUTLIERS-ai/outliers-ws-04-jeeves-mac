# -*- coding: utf-8 -*-
"""server.py - the local web server behind the Jeeves cockpit.

Python's own standard library only: nothing to install. It listens on
127.0.0.1 (this computer only), never on your network.

Three guards, each with a reason:
- Host check: a request must be addressed to 127.0.0.1 or localhost. This
  stops a trick called DNS rebinding, where a web page you visit pretends to be
  "localhost" and reads your notes.
- Origin check on every POST: only a page served by Jeeves itself may send a
  chat message. Without it, any website open in your browser could quietly ask
  your Claude Code to do work.
- Read-only vault routes: nothing here writes to your vaults.
- 1 copy per port: on Windows a normal server socket lets a second program
  listen on the same port as the first, so 2 copies of Jeeves could both
  answer on 4040. The socket here asks Windows for the port to itself.

Routes (all GET unless marked):
  /                     the cockpit            /api/today      CRM Today.md + day in the second brain
  /api/config           safe settings          /api/vaults     both vaults
  /api/vault/tree       notes in a vault       /api/vault/file one note
  /api/vault/search     search both vaults     /api/agents     your agents
  /api/vault/resolve    which vault a [[link]] is in             /api/health     "this is Jeeves"
  /api/activity         recent Claude sessions /api/tokens     today's tokens
  /api/apps             board + FleetView up?  /api/inbox      recommendations file
  POST /api/chat        stream a reply         POST /api/chat/stop, /api/chat/new
"""

import json
import mimetypes
import os
import socket
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import agents, apps, chat, sessions, vaults
from . import config as C

STATIC = Path(__file__).resolve().parent / "static"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class Handler(BaseHTTPRequestHandler):
    server_version = "Jeeves/1.0"
    cfg = None  # set by make_server

    def log_message(self, fmt, *args):  # quiet by default
        if getattr(self.server, "verbose", False):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ------------------------------------------------------------ helpers
    def _host_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ALLOWED_HOSTS

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True  # same-origin fetches from older browsers, and tests
        o = urlparse(origin)
        return o.hostname in ALLOWED_HOSTS and o.port == self.server.server_address[1]

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str))

    def _cfg(self):
        return C.load(self.server.config_file)

    # ------------------------------------------------------------ GET
    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "wrong host"}, 403)
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path
        cfg = self._cfg()
        try:
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/health":
                return self._json({"ok": True, "app": "jeeves", "pid": os.getpid(),
                                   "port": self.server.server_address[1]})
            if path == "/api/config":
                return self._json(public_config(cfg))
            if path == "/api/vaults":
                return self._json(vaults.listing(cfg))
            if path == "/api/vault/tree":
                return self._json(vaults.tree(cfg, q.get("v", "brain")))
            if path == "/api/vault/file":
                return self._json(vaults.read(cfg, q.get("v", "brain"), q.get("p", "")))
            if path == "/api/vault/resolve":
                return self._json(vaults.resolve(cfg, q.get("name", ""), q.get("prefer")))
            if path == "/api/vault/search":
                return self._json(vaults.search(cfg, q.get("q", "")))
            if path == "/api/today":
                return self._json(vaults.today(cfg))
            if path == "/api/inbox":
                return self._json(vaults.inbox(cfg))
            if path == "/api/agents":
                return self._json(agents.listing(cfg))
            if path == "/api/activity":
                return self._json(sessions.activity(cfg))
            if path == "/api/tokens":
                return self._json(sessions.tokens(cfg))
            if path == "/api/apps":
                return self._json(apps.status(cfg))
        except Exception as exc:  # noqa: BLE001 - a panel shows the error, the server lives on
            return self._json({"error": str(exc)}, 500)
        return self._json({"error": "not found"}, 404)

    def _static(self, rel):
        target = vaults.safe_path(STATIC, rel)
        if target is None or not target.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ------------------------------------------------------------ POST
    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            return self._json({"error": "refused: not from this page"}, 403)
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 200_000)) or b"{}") if n else {}
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self._json({"error": "send application/json"}, 415)
        cfg = self._cfg()
        key = str(body.get("session") or "main")[:40]
        if u.path == "/api/chat/stop":
            return self._json({"stopped": chat.stop(key)})
        if u.path == "/api/chat/new":
            chat.forget(key)
            return self._json({"ok": True})
        if u.path == "/api/chat":
            return self._chat(cfg, body, key)
        return self._json({"error": "not found"}, 404)

    def _chat(self, cfg, body, key):
        """Server-sent events: one `data:` line per event, flushed as it arrives."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        model = str(body.get("model") or cfg.get("default_model") or "best")
        try:
            for ev in chat.stream(cfg, str(body.get("message") or ""), model, key):
                self.wfile.write(("data: %s\n\n" % json.dumps(ev)).encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            chat.stop(key)  # the page went away: do not leave Claude running for nobody


def public_config(cfg):
    """Settings the page may see. Paths are shown so you know what Jeeves is reading."""
    return {
        "name": cfg.get("name", "Jeeves"),
        "models": cfg.get("models"),
        "default_model": cfg.get("default_model", "best"),
        "permission_mode": cfg.get("permission_mode"),
        "second_brain": cfg.get("second_brain"),
        "crm_vault": cfg.get("crm_vault"),
        "apps": cfg.get("apps"),
        "orb": cfg.get("orb"),
        "claude_found": chat.resolve_command(cfg) is not None,
        "read_only": chat.read_only(cfg),
        "chat_updated": chat.last_updated("main"),
        "chat_timeout_seconds": cfg.get("chat_timeout_seconds"),
        # the command this computer runs Python with, for commands the page prints
        "python": "python3" if sys.platform == "darwin" else "python",
    }


class JeevesServer(ThreadingHTTPServer):
    """The standard server, but the port is this program's alone.

    http.server turns on SO_REUSEADDR, and on Windows that lets a second program
    bind the same port while the first still listens (on Mac and Linux it does
    not). So on Windows: no reuse, and SO_EXCLUSIVEADDRUSE.
    """
    daemon_threads = True
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # http.server's own server_bind also asks for this address's name
        # (socket.getfqdn), only to fill in server_name, which nothing here uses.
        # On GitHub's test Macs that look-up took 35 seconds on every start
        # (measured 2026-09-24), so the page answered 35 seconds late and the
        # checks that wait 15 or 20 seconds for it failed. The name is now the
        # address as given, with no look-up.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = str(host), port


def make_server(port=None, config_file=None, verbose=False):
    cfg = C.load(config_file)
    port = int(port if port is not None else cfg.get("port", 4040))
    srv = JeevesServer(("127.0.0.1", port), Handler)
    srv.config_file = config_file
    srv.verbose = verbose
    return srv


def serve_in_thread(port=0, config_file=None):
    """For tests: start on a free port in the background; returns the server."""
    srv = make_server(port, config_file)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv

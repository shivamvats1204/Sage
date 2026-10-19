import argparse
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import re

from .agent import Agent
from .config import Settings, WORKSPACES, data_directory, load_environment, profile_name
from .documents import extract_text
from .store import Store
from .presentation import render_markdown, old_sources
from .integrations import capabilities

STATIC = Path(__file__).resolve().parents[1] / "web"


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, provider=None):
        super().__init__(address, Handler)
        self.store = store
        self.agent = Agent(store, provider)
        self.secret = secrets.token_bytes(32)
        self.locks = {}
        self.locks_guard = threading.Lock()

    def token(self, session):
        return hmac.new(self.secret, session.encode(), hashlib.sha256).hexdigest()

    def session_lock(self, session):
        with self.locks_guard:
            return self.locks.setdefault(session, threading.Lock())


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass  # Request content, cookies, and keys never enter access logs.

    def valid_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            current = cookie["sage_session"].value if "sage_session" in cookie else None
        except Exception:
            current = None
        return self.server.store.session(current)

    def send(self, code, data, content_type="application/json", session=None):
        if content_type == "application/json":
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if session:
            self.send_header("Set-Cookie", f"sage_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.valid_host():
            self.send(403, {"error": "Host not allowed"})
            return
        if self.path in {"/", "/app.js", "/style.css"}:
            name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[self.path]
            mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[name]
            self.send(200, (STATIC / name).read_bytes(), mime)
        elif re.fullmatch(r"/api/assets/[a-f0-9]{32}", self.path):
            session = self.session()
            asset = self.server.store.asset(session, self.path.rsplit("/", 1)[-1])
            if not asset:
                self.send(404, {"error": "Asset not found in this session"})
            elif asset["kind"] == "image":
                self.send(200, asset["payload"], "image/png")
            else:
                self.send(200, {k: v for k, v in asset.items() if k != "payload"})
        elif self.path == "/api/state":
            session = self.session()
            store = self.server.store
            settings = Settings.parse(store.settings(session))
            history = store.history(session, rich=True)
            for message in history:
                message["html"] = render_markdown(message["content"]) if message["role"] == "assistant" else ""
                if message["role"] == "assistant" and not message["metadata"].get("sources"):
                    message["metadata"]["sources"] = old_sources(store, session, message["content"])
            self.send(200, {"settings": settings.to_dict(), "profile": {"display_name": profile_name(settings)},
                "capabilities": capabilities(), "assets": store.assets(session),
                "workspaces": list(WORKSPACES), "history": history,
                "documents": [{"id": d["id"], "name": d["name"]} for d in store.documents(session)],
                "drafts": [{**d, "html": render_markdown(d["content"])} for d in store.drafts(session)], "model_available": self.server.agent.provider.available,
                "csrf": self.server.token(session)}, session=session)
        else:
            self.send(404, {"error": "Not found"})

    def do_POST(self):
        if not self.valid_host():
            self.send(403, {"error": "Host not allowed"})
            return
        session = self.session()
        expected_origin = "http://" + self.headers.get("Host", "")
        if self.headers.get("Origin") != expected_origin or not hmac.compare_digest(
            self.headers.get("X-Sage-CSRF", ""), self.server.token(session)):
            self.send(403, {"error": "Refresh this page before making changes"})
            return
        lock = self.server.session_lock(session)
        if not lock.acquire(blocking=False):
            self.send(409, {"error": "This session is already working. Wait for the current request."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 7_000_000 or not self.headers.get("Content-Type", "").startswith("application/json"):
                raise ValueError("Expected JSON smaller than 7 MB")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object")
            store = self.server.store
            if self.path == "/api/chat":
                settings = Settings.parse(body.get("settings", store.settings(session))).to_dict()
                store.save_settings(session, settings)
                result = self.server.agent.respond(session, body.get("message"), settings)
                result["html"] = render_markdown(result["answer"])
            elif self.path == "/api/settings":
                settings = Settings.parse(body).to_dict()
                store.save_settings(session, settings)
                result = {"settings": settings}
            elif self.path == "/api/documents":
                name = body.get("name", "")
                raw = base64.b64decode(body.get("content", ""), validate=True)
                result = {"id": store.add_document(session, name, extract_text(name, raw))}
            elif self.path == "/api/documents/remove":
                if not isinstance(body.get("id"), str):
                    raise ValueError("Document ID required")
                store.remove_document(session, body["id"])
                result = {"ok": True}
            elif self.path == "/api/history/clear":
                store.clear_history(session)
                result = {"ok": True}
            else:
                self.send(404, {"error": "Not found"})
                return
            self.send(200, result)
        except (ValueError, TypeError, UnicodeError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception:
            self.send(500, {"error": "Request failed. Your saved workspace is preserved."})
        finally:
            lock.release()


def main():
    parser = argparse.ArgumentParser(description="Sage local web workspace")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    load_environment()
    server = Server(("127.0.0.1", args.port), Store(data_directory() / "sage.db"))
    print(f"Sage web: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

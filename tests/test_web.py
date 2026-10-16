import base64
from http.cookiejar import CookieJar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from sage.store import Store
from sage.web import Server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.server = Server(("127.0.0.1", 0), Store(Path(self.tmp.name) / "web.db"), type("Offline", (), {"available": False})())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), urllib.request.ProxyHandler({}))
        self.state = json.load(self.client.open(self.url + "/api/state"))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def post(self, route, value, csrf=True, origin=None):
        headers = {"Content-Type": "application/json", "Origin": origin or self.url}
        if csrf:
            headers["X-Sage-CSRF"] = self.state["csrf"]
        return self.client.open(urllib.request.Request(self.url + route, json.dumps(value).encode(), headers))

    def test_upload_search_remove_and_export_state(self):
        data = {"name": "notes.txt", "content": base64.b64encode(b"Research budget is 250 dollars").decode()}
        doc = json.load(self.post("/api/documents", data))
        response = json.load(self.post("/api/chat", {"message": "Research budget"}))
        self.assertEqual(response["mode"], "local-search")
        self.assertIn(doc["id"], response["answer"])
        other = json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(self.url + "/api/state"))
        self.assertEqual(other["documents"], [])
        self.assertEqual(other["history"], [])
        json.load(self.post("/api/documents/remove", {"id": doc["id"]}))
        state = json.load(self.client.open(self.url + "/api/state"))
        self.assertEqual(state["documents"], [])
        self.assertEqual(len(state["history"]), 2)

    def test_csrf_and_origin_are_required(self):
        for kwargs in [{"csrf": False}, {"origin": "https://attacker.invalid"}]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post("/api/history/clear", {}, **kwargs)
            self.assertEqual(error.exception.code, 403)

    def test_invalid_payload_and_host(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/api/settings", {"max_steps": 999})
        self.assertEqual(error.exception.code, 400)
        req = urllib.request.Request(self.url + "/api/state", headers={"Host": "attacker.invalid"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.client.open(req)
        self.assertEqual(error.exception.code, 403)

    def test_static_pages_and_no_path_traversal(self):
        response = self.client.open(self.url + "/")
        self.assertIn(b"What are we", response.read())
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.client.open(self.url + "/../.env")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

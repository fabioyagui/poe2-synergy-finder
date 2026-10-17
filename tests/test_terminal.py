"""Terminal na página: WebSocket mínimo, handshake com token/origem e pseudo-terminal."""
import io
import json
import os
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from src import terminal


class FakeHandler:
    def __init__(self, headers):
        self.headers = headers
        self.out = io.BytesIO()
        self.wfile = self.out
        self.status = None

    def send_response(self, code, msg=""):
        self.status = code

    def send_header(self, k, v):
        self.out.write(f"{k}: {v}\r\n".encode())

    def end_headers(self):
        self.out.write(b"\r\n")


def masked(payload: bytes, opcode=0x1, mask=b"\x01\x02\x03\x04") -> bytes:
    n = len(payload)
    if n < 126:
        head = bytes([0x80 | opcode, 0x80 | n])
    else:
        head = bytes([0x80 | opcode, 0x80 | 126]) + n.to_bytes(2, "big")
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class WebSocketTests(unittest.TestCase):
    def test_accept_key_matches_rfc_6455_example(self):
        self.assertEqual(terminal.accept_key("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_frames_round_trip_including_medium_payloads(self):
        for payload in (b"oi", b"x" * 300):
            opcode, data = terminal.read_frame(io.BytesIO(masked(payload)))
            self.assertEqual((opcode, data), (0x1, payload))
        encoded = terminal.encode_frame(b"abc")
        self.assertEqual(encoded, b"\x81\x03abc")
        self.assertEqual(terminal.encode_frame(b"y" * 200)[:4], b"\x81\x7e\x00\xc8")
        self.assertIsNone(terminal.read_frame(io.BytesIO(b"")))

    def test_handshake_refuses_bad_origin_token_and_non_upgrade(self):
        base = {"Upgrade": "websocket", "Connection": "keep-alive, Upgrade", "Origin": "http://127.0.0.1:1",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}
        allowed = {"http://127.0.0.1:1"}
        self.assertEqual(terminal.handshake(FakeHandler({**base, "Origin": "http://evil.example"}), allowed, terminal.TOKEN), "origem não permitida")
        self.assertEqual(terminal.handshake(FakeHandler(base), allowed, "errado"), "token inválido")
        self.assertEqual(terminal.handshake(FakeHandler({**base, "Upgrade": "h2c"}), allowed, terminal.TOKEN), "não é um pedido de WebSocket")
        ok = FakeHandler(base)
        self.assertIsNone(terminal.handshake(ok, allowed, terminal.TOKEN))
        self.assertEqual(ok.status, 101)
        self.assertIn(b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=", ok.out.getvalue())

    def test_only_known_clis_and_token_is_random(self):
        self.assertEqual(set(terminal.CLIS), {"claude", "codex"})
        self.assertGreaterEqual(len(terminal.TOKEN), 24)
        clis = terminal.available_clis()
        self.assertEqual(set(clis), {"claude", "codex"})
        for info in clis.values():
            self.assertEqual(set(info), {"label", "available", "path", "install"})


@unittest.skipUnless(terminal.pty_available()[0], terminal.pty_available()[1])
class PtyTests(unittest.TestCase):
    def test_pty_runs_a_command_and_reports_exit(self):
        argv = ["cmd", "/c", "echo pty-ok"] if os.name == "nt" else ["sh", "-c", "echo pty-ok"]
        session = terminal.PtySession(argv, terminal.PROJECT, rows=20, cols=80)
        out = ""
        for _ in range(50):
            chunk = session.read()
            if not chunk:
                break
            out += chunk
        session.close()
        self.assertIn("pty-ok", out)
        self.assertFalse(session.alive())


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(app.Application()))
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_status_exposes_clis_token_and_cwd(self):
        with urllib.request.urlopen(self.base + "/api/terminal/status", timeout=10) as r:
            data = json.load(r)
        self.assertEqual(data["token"], terminal.TOKEN)
        self.assertEqual(set(data["clis"]), {"claude", "codex"})
        self.assertTrue(data["cwd"].endswith("poe2-synergy-finder"))

    def test_websocket_without_token_or_origin_is_refused(self):
        req = urllib.request.Request(self.base + "/ws/terminal?cli=claude&token=errado", headers={
            "Upgrade": "websocket", "Connection": "Upgrade", "Origin": self.base, "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)
        req = urllib.request.Request(self.base + "/ws/terminal?cli=claude&token=" + terminal.TOKEN, headers={
            "Upgrade": "websocket", "Connection": "Upgrade", "Origin": "http://evil.example", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)
        req = urllib.request.Request(self.base + "/ws/terminal?cli=bash&token=" + terminal.TOKEN, headers={"Origin": self.base})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)

    def test_static_terminal_assets_are_served_with_csp_allowing_ws(self):
        for path in ("/terminal.js", "/terminal.css", "/vendor/xterm.js", "/vendor/addon-fit.js", "/vendor/xterm.css"):
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                self.assertEqual(r.status, 200, path)
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            csp = r.headers.get("Content-Security-Policy")
            html = r.read().decode("utf-8")
        self.assertIn(f"ws://127.0.0.1:{self.port}", csp)
        self.assertIn('id="openTerminal"', html)
        self.assertIn('id="terminalDialog"', html)


if __name__ == "__main__":
    unittest.main()

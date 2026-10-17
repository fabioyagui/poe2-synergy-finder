"""Terminal na página: roda o CLI do Claude Code ou do Codex num pseudo-terminal e liga ao navegador por WebSocket.

Segurança: isto é um shell exposto por HTTP local. O handshake exige o token
gerado nesta inicialização (`TOKEN`), a origem da própria página e o host
local; só os comandos de `CLIS` podem ser abertos, sempre na pasta do projeto.
WebSocket mínimo (RFC 6455) sobre o http.server, sem dependências; o
pseudo-terminal usa pywinpty no Windows e o módulo pty nos outros sistemas.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TOKEN = secrets.token_urlsafe(24)
CLIS = {
    "claude": {"label": "Claude Code", "argv": ["claude"], "install": "winget install Anthropic.ClaudeCode"},
    "codex": {"label": "Codex", "argv": ["codex"], "install": "npm install -g @openai/codex"},
}
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_FRAME = 1 << 20


def available_clis() -> dict:
    out = {}
    for name, spec in CLIS.items():
        exe = shutil.which(spec["argv"][0])
        out[name] = {"label": spec["label"], "available": bool(exe), "path": exe, "install": spec["install"]}
    return out


def pty_available() -> tuple[bool, str]:
    if os.name == "nt":
        try:
            import winpty  # noqa: F401
            return True, ""
        except ImportError:
            return False, "Instale o pseudo-terminal do Windows: pip install pywinpty"
    try:
        import pty  # noqa: F401
        return True, ""
    except ImportError:
        return False, "módulo pty indisponível neste sistema"


# ---------- pseudo-terminal ----------
class PtySession:
    def __init__(self, argv: list[str], cwd: Path, rows: int = 30, cols: int = 120, extra_env: dict | None = None):
        self.argv, self.cwd = argv, str(cwd)
        # Se o Finder foi aberto de dentro de uma sessão do Claude Code, o CLI filho herdaria as
        # variáveis dela e se trataria como sessão aninhada. O terminal da página é sempre uma sessão nova.
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE", "CLAUDECODE"))}
        env.update(extra_env or {})
        if os.name == "nt":
            from winpty import PtyProcess
            self._proc = PtyProcess.spawn(argv, cwd=self.cwd, env=env, dimensions=(rows, cols))
            self._posix = None
        else:
            import pty
            master, slave = pty.openpty()
            self._posix = subprocess.Popen(argv, cwd=self.cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                                           start_new_session=True, close_fds=True)
            os.close(slave)
            self._master = master
            self._proc = None
            self.resize(rows, cols)

    def read(self, size: int = 4096) -> str:
        """Bloqueia até haver saída; devolve '' quando o processo termina."""
        if self._proc is not None:
            try:
                return self._proc.read(size)
            except EOFError:
                return ""
        try:
            return os.read(self._master, size).decode("utf-8", "replace")
        except OSError:
            return ""

    def write(self, data: str):
        if self._proc is not None:
            self._proc.write(data)
        else:
            os.write(self._master, data.encode("utf-8"))

    def resize(self, rows: int, cols: int):
        rows, cols = max(2, min(int(rows), 500)), max(10, min(int(cols), 1000))
        if self._proc is not None:
            self._proc.setwinsize(rows, cols)
        else:
            import fcntl
            import termios
            fcntl.ioctl(self._master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def alive(self) -> bool:
        if self._proc is not None:
            return self._proc.isalive()
        return self._posix.poll() is None

    def close(self):
        try:
            if self._proc is not None:
                if self._proc.isalive():
                    self._proc.terminate(force=True)
            else:
                if self._posix.poll() is None:
                    self._posix.kill()
                os.close(self._master)
        except Exception:
            pass


# ---------- WebSocket mínimo ----------
def accept_key(client_key: str) -> str:
    return base64.b64encode(hashlib.sha1((client_key.strip() + _WS_GUID).encode()).digest()).decode()


def encode_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def read_frame(rfile) -> tuple[int, bytes] | None:
    """Lê um frame do cliente (sempre mascarado); None no fim da conexão."""
    head = rfile.read(2)
    if len(head) < 2:
        return None
    opcode, second = head[0] & 0x0F, head[1]
    masked, n = bool(second & 0x80), second & 0x7F
    if n == 126:
        n = struct.unpack(">H", rfile.read(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", rfile.read(8))[0]
    if n > MAX_FRAME:
        raise ValueError("frame grande demais")
    mask = rfile.read(4) if masked else b""
    data = rfile.read(n)
    if len(data) < n:
        return None
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


def handshake(handler, origin_allowed: set[str], token: str) -> str | None:
    """Valida o pedido de upgrade; devolve a razão da recusa ou None se aceito (resposta 101 já enviada)."""
    h = handler.headers
    if h.get("Upgrade", "").lower() != "websocket" or "upgrade" not in h.get("Connection", "").lower():
        return "não é um pedido de WebSocket"
    if h.get("Origin") not in origin_allowed:
        return "origem não permitida"
    if not token or not secrets.compare_digest(token, TOKEN):
        return "token inválido"
    key = h.get("Sec-WebSocket-Key")
    if not key:
        return "sem Sec-WebSocket-Key"
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept_key(key))
    handler.end_headers()
    handler.wfile.flush()
    return None


def serve(handler, cli: str, rows: int, cols: int):
    """Após o handshake: liga o pseudo-terminal ao socket até um dos lados fechar."""
    spec = CLIS[cli]
    exe = shutil.which(spec["argv"][0])
    if not exe:
        _send_text(handler, f"\r\n[{spec['label']} não encontrado. {spec['install']}]\r\n")
        return
    session = PtySession([exe] + spec["argv"][1:], PROJECT, rows, cols)
    lock = threading.Lock()
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            chunk = session.read()
            if not chunk:
                break
            with lock:
                try:
                    handler.wfile.write(encode_frame(chunk.encode("utf-8", "replace")))
                    handler.wfile.flush()
                except OSError:
                    break
        with lock:
            try:
                handler.wfile.write(encode_frame(json.dumps({"type": "exit"}).encode(), 0x1))
                handler.wfile.write(encode_frame(b"", 0x8))
                handler.wfile.flush()
            except OSError:
                pass
        stop.set()

    threading.Thread(target=pump, daemon=True).start()
    try:
        while not stop.is_set():
            frame = read_frame(handler.rfile)
            if frame is None:
                break
            opcode, data = frame
            if opcode == 0x8:
                break
            if opcode == 0x9:
                with lock:
                    handler.wfile.write(encode_frame(data, 0xA))
                    handler.wfile.flush()
                continue
            if opcode == 0x1:
                text = data.decode("utf-8", "replace")
                if text.startswith("{"):
                    try:
                        msg = json.loads(text)
                    except ValueError:
                        msg = None
                    if isinstance(msg, dict) and msg.get("type") == "resize":
                        session.resize(msg.get("rows", rows), msg.get("cols", cols))
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "input":
                        session.write(str(msg.get("data", "")))
                        continue
                session.write(text)
            elif opcode == 0x2:
                session.write(data.decode("utf-8", "replace"))
    finally:
        stop.set()
        session.close()


def _send_text(handler, text: str):
    handler.wfile.write(encode_frame(text.encode("utf-8")))
    handler.wfile.write(encode_frame(b"", 0x8))
    handler.wfile.flush()

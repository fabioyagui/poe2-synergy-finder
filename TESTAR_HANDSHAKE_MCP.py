from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SERVER=ROOT/"mcp_server.py"

def ask(proc,payload):
    proc.stdin.write(json.dumps(payload,separators=(",",":"))+"\n")
    proc.stdin.flush()
    raw=proc.stdout.readline()
    if not raw:
        raise RuntimeError("Servidor não respondeu. stderr="+proc.stderr.read())
    return json.loads(raw)

def main():
    p=subprocess.Popen(
        [sys.executable,str(SERVER)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,bufsize=1,
    )
    try:
        init=ask(p,{
            "jsonrpc":"2.0","id":0,"method":"initialize",
            "params":{
                "protocolVersion":"2025-06-18",
                "capabilities":{
                    "experimental":{"codex/auth-change":{}},
                    "elicitation":{"form":{},"url":{}},
                },
                "clientInfo":{
                    "name":"codex-mcp-client",
                    "title":"Codex",
                    "version":"0.154.0",
                },
            },
        })
        assert init["result"]["protocolVersion"]=="2025-06-18",init
        assert "tools" in init["result"]["capabilities"],init
        print("initialize Codex 0.154.0 / MCP 2025-06-18: OK")

        p.stdin.write(json.dumps({
            "jsonrpc":"2.0","method":"notifications/initialized","params":{}
        },separators=(",",":"))+"\n")
        p.stdin.flush()

        tools=ask(p,{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
        assert set(tools["result"].keys())=={"tools"},tools
        assert len(tools["result"]["tools"])==14,tools
        print("tools/list exato MCP 2025-06-18: 14 tools OK")

        # Validate every tool has the fields Codex/rmcp expects.
        for tool in tools["result"]["tools"]:
            assert isinstance(tool.get("name"),str) and tool["name"]
            assert isinstance(tool.get("description"),str)
            assert isinstance(tool.get("inputSchema"),dict)
            assert tool["inputSchema"].get("type")=="object"
        print("schemas das 14 tools: OK")
        print("HANDSHAKE MCP CODEX 0.154: OK")
    finally:
        try:p.stdin.close()
        except Exception:pass
        p.terminate()
        p.wait(timeout=5)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

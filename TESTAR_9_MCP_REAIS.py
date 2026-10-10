import json, subprocess, sys
from pathlib import Path
import mcp_server

SERVER=Path(__file__).with_name("mcp_server.py")
for name in mcp_server.TOOLS:
    payload="\n".join(json.dumps(x,separators=(",",":")) for x in [
        {"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"codex-mcp-client","version":"0.154.0"}}},
        {"jsonrpc":"2.0","method":"notifications/initialized"},
        {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}},
    ])+"\n"
    proc=subprocess.run([sys.executable,str(SERVER),"--tool",name],input=payload,capture_output=True,text=True,timeout=10)
    if proc.returncode:
        raise RuntimeError(name+": "+proc.stderr)
    replies=[json.loads(x) for x in proc.stdout.splitlines() if x.strip()]
    tools=replies[-1]["result"]["tools"]
    assert len(tools)==1 and tools[0]["name"]==name,(name,tools)
    print(name+": OK")
print("9 MCPs SINGLE-TOOL: OK")

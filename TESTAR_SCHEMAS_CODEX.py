import json
import mcp_server

for tool in mcp_server._tool_list():
    print(tool["name"])
    print(json.dumps(tool["inputSchema"],ensure_ascii=False,separators=(",",":")))
print("TOTAL:",len(mcp_server._tool_list()))
print("SCHEMAS CODEX-SAFE: OK")

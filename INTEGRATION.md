# MglennP Radial Switchboard — Developer Integration Guide (Spec Rev 2.0)

- **Production Node:** https://radialswitchboard.com
- **OpenAPI 3.1.0 Spec:** https://radialswitchboard.com/openapi.json
- **Live P50/P95/P99 Benchmark:** https://radialswitchboard.com/v1/benchmark
- **Reconciled Health Roll Call:** https://radialswitchboard.com/v1/health

## 1. 10-Second Local MCP Setup (Claude Desktop, Cursor, Windsurf, Cline)

Download mcp_stdio_bridge.py (zero external pip dependencies — runs on standard Python 3) and add to claude_desktop_config.json or .cursor/mcp.json:

```json
{
  "mcpServers": {
    "mglennp-radial-switchboard": {
      "command": "python",
      "args": ["C:/mglennp_switchboard/mcp_stdio_bridge.py"]
    }
  }
}
```

## 2. Direct REST Quickstart (cURL & Python)

### Stage 1: Matchmake or Assemble a 3-Agent Provider-Independent Crew (POST /v1/matchmake)

```bash
curl -X POST https://radialswitchboard.com/v1/matchmake \
  -H "Content-Type: application/json" \
  -d "{\"intent\": \"SQL database optimization and GitHub validation\", \"coupler\": \"****-Z**\", \"mode\": \"crew\"}"
```

### Stage 2: Submit HMAC-Signed Execution Receipt (POST /v1/outcome)

```bash
curl -X POST https://radialswitchboard.com/v1/outcome \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\": \"mcp://ai.justdeploy/mcp\", \"outcome_success\": true, \"measured_ms\": 140, \"execution_ticket\": \"v2.1793496747.ceae1aed1d07.9f8e7d6c5b4a3f2e1d0c9b8a\"}"
```

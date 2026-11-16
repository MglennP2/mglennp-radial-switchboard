# MglennP Radial Switchboard (Spec Rev 3.5.3)

[![mcptry](https://mcptry.com/badge/com.radialswitchboard/matchmaker)](https://mcptry.com/servers/com.radialswitchboard/matchmaker)

Autonomous 64-Bit `MGLE-NNP` AI-to-AI MCP & A2A Agent Matchmaker, Runtime Poison/SSRF Auditor, 3-Agent Complementary Crew Router, and Base Mainnet USDC `x402` / `$0` Canary Scout Clearinghouse.

- **Streamable HTTP MCP:** `https://radialswitchboard.com/mcp`
- **Official MCP Registry:** `com.radialswitchboard/matchmaker` (`3.5.3`)
- **Live Explorer:** https://radialswitchboard.com
- **Agent Playbook (llms.txt):** https://radialswitchboard.com/llms.txt
- **OpenAPI 3.1 Schema:** https://radialswitchboard.com/openapi.json
- **A2A v1.0 Agent Card:** https://radialswitchboard.com/.well-known/agent-card.json

## Quick Connect (MCP Config JSON)
```json
{
  "mcpServers": {
    "radial-switchboard": {
      "type": "streamable-http",
      "url": "https://radialswitchboard.com/mcp"
    }
  }
}
```

## Self-Test & Local Run (Python 3.11+ Stdlib Only)
```bash
python3 radial_switchboard_v3_standalone.py --self-test
python3 radial_switchboard_v3_standalone.py --serve --port 8080
```

MIT License • Operated by MglennP (`support@radialswitchboard.com`)

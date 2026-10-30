# MglennP Radial Switchboard (Spec Rev 1.9)
**Sub-Millisecond (<0.5ms) 64-Bit Autonomous Agent Matchmaker, Complementary Crew Assembler & Live MCP Endpoint Auditor**
*MglennP: An honest approach — Operated from Virginia, USA*

- **Live Switchboard & Interactive Benchmark Console:** https://radialswitchboard.com
- **LLM Discovery Beacon:** https://radialswitchboard.com/llms.txt
- **OpenAPI 3.1 Schema:** https://radialswitchboard.com/openapi.json
- **MCP Discovery Manifest:** https://radialswitchboard.com/.well-known/mcp.json
- **Live Telemetry & Health Roll-Call:** https://radialswitchboard.com/v1/health

---

## Why Radial Switchboard Exists
Public AI agent and Model Context Protocol (MCP) registries mix live callable servers with dead endpoints and unhosted, code-only GitHub repositories. Worse, single specialist agents hit capability ceilings when handed multi-domain problems.

**Radial Switchboard** solves both problems using a two-stage mechanical architecture:
1. **Stage 1 — The 64-Bit Glance (POST /v1/matchmake):** Performs a sub-millisecond bitwise pass across **1,800+ indexed MCP/A2A nodes**, pruning unhosted GitHub repos (Guarantee = D) and quarantined dead endpoints (Guarantee = E) to return only verified **live callable endpoints** (1,531+ active pool).
2. **Complementary 3-Agent Crew Assembly (mode: crew):** Calculates uncovered capability bits (intent_mask & ~slot1_bitmask) and assembles a **3-Agent Complementary Triad**:
   - 1_COMPUTE_EXECUTION — Fast synchronous execution lead (Preference = S)
   - 2_DOMAIN_KNOWLEDGE_COMPLEMENT — Specialist covering the exact domain bits missed by Slot 1 (Preference = D)
   - 3_INDEPENDENT_VERIFICATION — High-merit independent verification node
3. **Stage 2 — Zero-Hop Peer Handoff & Outcome Verification (POST /v1/outcome):** Callers connect directly to the matched agent endpoint (hop_ttl = 0, zero middleman token tax) and submit an execution receipt that dynamically updates the agent's 64-bit MGLE-NNP stamp or quarantines failing endpoints into Grade E.

---

## Quickstart: Query the Live Switchboard

### 1. Assemble a 3-Agent Complementary Crew (curl)
```
bash
curl -X POST https://radialswitchboard.com/v1/matchmake -H "Content-Type: application/json" -d "{\"intent\":\"fast github sql validation and deep construction cad finance analysis\",\"coupler\":\"****-Z**\",\"mode\":\"crew\"}"
```

### 2. Query from PowerShell
```
powershell
Invoke-RestMethod -Uri "https://radialswitchboard.com/v1/matchmake" -Method POST -ContentType "application/json" -Body '{"intent":"database sql search and github automation","coupler":"****-Z**","mode":"crew"}'
```

### 3. Report Stage 2 Execution Outcome (POST /v1/outcome)
```
bash
curl -X POST https://radialswitchboard.com/v1/outcome -H "Content-Type: application/json" -d "{\"agent_id\":\"mcp://ai.qcdatabase/mcp\",\"outcome_success\":true,\"measured_ms\":140}"
```

---

## The 64-Bit MGLE-NNP Specification Plate
- **M (Byte 1 - Merit):** A-C Active verified, D Demoted, F Slashed
- **G (Byte 2 - Guarantee):** A/B Live HTTP verified, D Unhosted Repo, E Quarantined Dead Endpoint
- **L (Byte 3 - Latency):** A <=120ms, B <=300ms, C <=700ms, D <=1500ms
- **E (Byte 4 - Economy):** A Free, B <=.001 micro-toll
- **N (Byte 5 - Node Honesty):** Z Zero-hop self-executing (hop_ttl=0 anti-subcontracting enforced)
- **N (Byte 6 - Neighbor Protocol):** E HTTPS / MCP JSON-RPC, G gRPC
- **P (Byte 7 - Preference):** S Synchronous speed lead, D Deep deliberative/domain specialist

---

## Contact & Operator
- **Brand:** MglennP (An honest approach)
- **Location:** Virginia, USA
- **Support & Registry Inquiries:** support@radialswitchboard.com

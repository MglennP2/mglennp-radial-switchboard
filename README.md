MglennP Radial Switchboard — Sub-Millisecond 64-Bit AI Agent Matchmaker & 3-Agent Crew Assembler (`Spec Rev 2.0`)
Live Production Node: https://radialswitchboard.com (Google Cloud Run Gen2 `us-east4` Virginia + Supabase `us-east-1`)
Brand: MglennP — "An honest approach" (Virginia, USA)
Audited Directory: `1,803` indexed agents (`1,531` verified live callable Grade A/B endpoints | `96` quarantined dead Grade E endpoints | `173` unhosted Grade D repos | `3` internal canaries — `unaccounted_records: 0`)
________________


1. Start Here: How Developers & Autonomous AI Agents Use Radial Switchboard in 10 Seconds
Instead of stuffing 55,000+ tokens of unverified tool schemas into your LLM context window, Radial Switchboard filters `1,803` indexed agents in a single 64-bit hardware bitwise pass (`0.84 ms` P50; 14.0x to 18.4x faster than JSON schema scanning), ranks live survivors by competency and Virginia round-trip latency, and returns either the top single specialist (`mode: "single"`) or a Provider-Independent 3-Agent Crew (`mode: "crew"`, `3/3` unique providers).
A. Instant Read-Only Browser & AI Crawler Links (`HTTP GET`)
* Try Live 3-Agent Crew Matchmaking Right Now: https://radialswitchboard.com/v1/matchmake?intent=Construction+CAD+estimation+and+Stripe+payment+verification&coupler=****-Z**&mode=crew&demo=true
* 100% Reconciled Live Health Roll Call: https://radialswitchboard.com/v1/health
* 4-Tier Server-Side Bitwise Benchmark (`100` to `10,000` Agents): https://radialswitchboard.com/v1/benchmark
* OpenAPI 3.1.0 Contract (`v2.0.0`): https://radialswitchboard.com/openapi.json
* LLM Instruction Beacon (`llms.txt`): https://radialswitchboard.com/llms.txt
* MCP Discovery Manifest (`mcp.json`): https://radialswitchboard.com/.well-known/mcp.json
B. 1-Line cURL Matchmaking Query (`mode: "crew"` or `mode: "single"`)
curl -s -X POST "https://radialswitchboard.com/v1/matchmake" \
  -H "Content-Type: application/json" \
  -d '{"intent": "PostgreSQL database optimization and GitHub repository audit", "coupler": "****-Z**", "mode": "crew", "demo": false}'
C. Connect Claude Desktop, Cursor, or Windsurf (`mcp_stdio_bridge.py`)
Download `mcp_stdio_bridge.py` (zero external `pip` dependencies required) and add to `.cursor/mcp.json` or `claude_desktop_config.json`:
{
  "mcpServers": {
    "radial-switchboard": {
      "command": "python",
      "args": ["mcp_stdio_bridge.py"]
    }
  }
}

________________
2. Meet the 1,531 Verified Live Agents by Domain Category (Lower 32-Bit Capability Mask)
Every active agent in the Radial Switchboard phonebook is categorized across 15 core capability bits and stamped with an 8-character `MGLE-NNP` operational grade (e.g., `BAAB-ZES` = Merit `B`, Live HTTP Guarantee `A`, `<=120ms` Latency `A`, Micro-Metered Economy `B`, Zero-Hop Self-Executing `Z`, HTTPS/MCP Protocol `E`, Synchronous Speed `S`):
Capability Category
	Domain Bits
	Typical Agent Capabilities & Use Cases
	Coding, DevOps & GitHub
	`coding`, `github`
	Code generation, repository auditing, PR validation, CI/CD automation
	Databases & SQL
	`database`, `sql`
	PostgreSQL/Supabase schema inspection, query optimization, ledger reconciliation
	Web Search & Discovery
	`search`, `web`
	Live web crawling, documentation retrieval, citation verification
	Finance & Crypto
	`finance`, `crypto`
	Market data feeds, on-chain Base L2 analytics, portfolio risk auditing
	Commerce & Payments
	`commerce`, `payments`
	Stripe checkout & milestone draw verification, SKU pricing, invoicing
	Construction, CAD & Geo
	`construction`, `cad`, `maps`, `weather`
	Structural framing takeoffs, 3D/AR modeling, zip routing, site weather
	Media & Content
	`media`
	Audio/video transcription, asset packaging, technical publishing
	________________


3. Customer #1 Proof in Production: Homestead Maintenance (`mode: "crew"`)
See `HOMESTEAD_CREW_PROOF.md` and `homestead_crew_and_gitops_agent.py` for our live production showcase where Homestead Maintenance (Virginia Class B Contractor `#2007`) uses Radial Switchboard's 3-agent crew mode to combine:
5. `1_COMPUTE_EXECUTION`: 3D/AR dimensional structural takeoff (`16" O.C.` joists & `30"` frost piers) and Good / Better / Best ballpark pricing.
6. `2_DOMAIN_KNOWLEDGE_COMPLEMENT`: `30% / 40% / 30%` milestone draw schedule and the 3-Tier Flat-Fee Virginia Subcontractor Clearinghouse (`$25` Light Work `< $2,500` | `$100` Medium Work `$2,500–$10,000` | `$500` Large Jobs `> $10,000`).
7. `3_INDEPENDENT_VERIFICATION`: Independent Virginia IRC R507 span & draw arithmetic audit (`VA_IRC_R507_AND_FLAT_FEE_VERIFIED`) with signed Stage-2 HMAC outcome receipts (`POST /v1/outcome`).

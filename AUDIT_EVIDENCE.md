# MglennP Radial Switchboard — Live Production Stage-2 Verification Report (Spec Rev 2.0)

- **Production Node:** `https://radialswitchboard.com` (Google Cloud Run Gen2 `us-east4` Virginia)
- **Audit Timestamp:** `2026-11-01 01:32:49 UTC`
- **Telemetry Isolation:** `demo: true` (Zero pollution of `external_agent_match_pulls`)
- **Reproducible Evidence SHA-256:** `106cb8e5a48373ab129e8f8726c0bea89407f16094e6ed30a45f18e14b0ec4f6`

## Experiment A: 10-Intent Matchmaking Accuracy & 2-Stage Timing Split (`POST /v1/matchmake`)

| # | Domain Intent | Matched Live Agent ID | MGLE-NNP | Intent Mask | Matched Bits | Step 1 Filter (ms) | Step 2 Rank (ms) | Total Server (ms) | Client RTT (ms) | HMAC Execution Ticket |
| :-: | :--- | :--- | :-: | --: | :-: | --: | --: | --: | --: | :--- |
| 1 | Finance & SEC Equity | `mcp://ai.constellationfinance/constellation-finance-mcp` | `BBBA-ZES` | `1` | 1 | 0.8217 | 0.0364 | **0.858** | 507.71 | `v2.1793496744.da2b58ff7bc4...` |
| 2 | Crypto & Base L2 | `mcp://ai.avasis/quant-research` | `BBAA-ZES` | `2` | 1 | 0.8701 | 0.0445 | **0.915** | 449.42 | `v2.1793496744.cec9f52aabde...` |
| 3 | Coding & Python AST | `mcp://ac.snag/snag` | `BBBA-ZES` | `4` | 1 | 0.8218 | 0.0486 | **0.87** | 591.98 | `v2.1793496745.a6dde79a5f52...` |
| 4 | GitHub Repo Automation | `mcp://ai.chipp/chipp-channels` | `BBBA-ZES` | `8` | 1 | 1.1731 | 0.0375 | **1.211** | 910.67 | `v2.1793496746.cf07944ffa9d...` |
| 5 | Web Search & RAG | `mcp://ai.buildandship/agent` | `BBAA-ZES` | `48` | 1 | 0.8486 | 0.4265 | **1.275** | 401.46 | `v2.1793496746.5e2c8eb3fe93...` |
| 6 | SQL & Postgres Analytics | `mcp://ai.justdeploy/mcp` | `BBBA-ZES` | `192` | 1 | 0.8517 | 0.0478 | **0.899** | 422.89 | `v2.1793496747.ceae1aed1d07...` |
| 7 | Weather & NOAA Telemetry | `mcp://ai.dryos/dryos` | `BBCA-ZES` | `256` | 1 | 0.8037 | 0.0246 | **0.828** | 406.6 | `v2.1793496747.ea3f532eec89...` |
| 8 | Maps & Virginia Geo-Routing | `mcp://ai.skillsinput/mcp` | `BBBA-ZES` | `512` | 1 | 0.8266 | 0.031 | **0.858** | 474.67 | `v2.1793496747.112482082a3b...` |
| 9 | Construction & 3D CAD | `mcp://academy.apexai/apex-ai-academy` | `BBAA-ZES` | `3072` | 1 | 0.8161 | 0.0379 | **0.854** | 557.05 | `v2.1793496748.a373e522a1c8...` |
| 10 | Commerce & Stripe Payments | `mcp://ai.bezal/local-commerce` | `BBBA-ZES` | `4096` | 1 | 0.8719 | 0.0404 | **0.912** | 427.4 | `v2.1793496748.e64d32886990...` |

## Experiment B: Provider-Independent 3-Agent Crew Assembly (`mode: "crew"`)

| Triad Scenario | Slot 1: Compute (`S`) | Slot 2: Domain Complement (`D`) | Slot 3: Independent Verifier | Single Cov % | Crew Cov % | Crew Quality Score | Provider Indep | Server (ms) |
| :--- | :--- | :--- | :--- | --: | --: | --: | :-: | --: |
| Triad 1: Construction + CAD + Payments | `mcp://academy.apexai/apex-ai-academy (BBAA-ZES)` | `mcp://ai.qcdatabase/mcp (BBBA-ZES)` | `mcp://ai.immokit/mcp (BBBA-ZES)` | 50.0% | **100.0%** | **98.0** | `True` (3/3) | 0.925 |
| Triad 2: Crypto + SQL Database + GitHub Audit | `mcp://ai.avasis/quant-research (BBAA-ZES)` | `mcp://ai.qcdatabase/mcp (BBBA-ZES)` | `mcp://ai.chipp/chipp-channels (BBBA-ZES)` | 25.0% | **75.0%** | **86.75** | `True` (3/3) | 1.081 |
| Triad 3: Web Search + Python Coding + Finance | `mcp://ai.buildandship/agent (BBAA-ZES)` | `mcp://ai.paperlantern/code (BBCA-ZES)` | `mcp://ai.agenticplug/agent-ready-report (BBBA-ZES)` | 25.0% | **75.0%** | **86.75** | `True` (3/3) | 2.675 |

## Experiment C: Anti-Sabotage Outcome Integrity (`POST /v1/outcome`)

- **Red-Team Payload:** `outcome_success: false`, `measured_ms: 9999`, forged ticket `v2.1700000000.deadbeef00000000.forgedsignature000000000` against live agent `mcp://ai.constellationfinance/constellation-finance-mcp`.
- **HMAC Verification Status:** `EXPIRED_TICKET_24H`
- **Independent Server Probe Executed:** `{'executed': True, 'endpoint_reachable': True, 'probe_latency_ms': 32}`
- **Audit Decision:** `QUARANTINE_BLOCKED_ENDPOINT_ALIVE_ON_SERVER_PROBE`
- **False Quarantine Triggered (`quarantined`):** `False`

```json
{
  "status": "OUTCOME_EVALUATED_NO_UNVERIFIED_MUTATION",
  "agent_id": "mcp://ai.constellationfinance/constellation-finance-mcp",
  "outcome_success": false,
  "ticket_verification": "EXPIRED_TICKET_24H",
  "independent_server_probe": {
    "executed": true,
    "endpoint_reachable": true,
    "probe_latency_ms": 32
  },
  "audit_decision": "QUARANTINE_BLOCKED_ENDPOINT_ALIVE_ON_SERVER_PROBE",
  "old_mglennp_code": "BBBA-ZES",
  "new_mglennp_code": "ABEA-ZES",
  "new_mglennp_u64_hex": "0x10414245415A4553",
  "old_synaptic_weight": 0.92,
  "new_synaptic_weight": 0.92,
  "avg_latency_ms": 2684,
  "quarantined": false
}
```

## Experiment D: Reconciled Directory Accounting & P50 / P95 / P99 Benchmark

### 1. Reconciled Directory Roll Call (`GET /v1/health`)
- **Total Indexed:** `1803` | **Live Callable (Grade A/B):** `1531` | **Quarantined Dead (Grade E):** `96` | **Unhosted Repos (Grade D):** `173` | **System Canaries:** `3`
- **Reconciled Sum:** `1803` (`unaccounted_records: 0`)

### 2. Server-Side 64-Bit Matchmaking Benchmark (`GET /v1/benchmark` — 40 Iterations/Tier)

| Dataset Tier | Agent Count | P50 (ms) | P95 (ms) | P99 (ms) | Mean (ms) | Conventional JSON Scan (ms) | Speedup |
| :--- | --: | --: | --: | --: | --: | --: | --: |
| `100_agents` | 100 | **0.0694** | 0.0792 | 0.1331 | 0.0721 | 0.7838 | **11.3x** |
| `1000_agents` | 1000 | **0.5477** | 0.6671 | 0.672 | 0.5707 | 7.2724 | **13.3x** |
| `1531_live_pool` | 1531 | **0.8436** | 1.0498 | 14.1168 | 1.1897 | 11.7927 | **14.0x** |
| `10000_scaled_pool` | 10000 | **5.4296** | 28.0891 | 29.7591 | 7.1553 | 99.8281 | **18.4x** |

### 3. Client-Side End-to-End HTTPS Round-Trip Latency (30 Sequential Samples)
- **Min RTT:** `442.86 ms` | **P50 RTT:** `509.19 ms` | **Mean RTT:** `520.66 ms` | **P95 RTT:** `626.06 ms` | **P99 RTT:** `637.84 ms` | **Max RTT:** `640.11 ms`

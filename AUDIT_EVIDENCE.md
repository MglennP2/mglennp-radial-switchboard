# MglennP Radial Switchboard — Live Production Stage-2 Verification Report (Spec Rev 2.0)

- **Production Node:** `https://radialswitchboard.com` (Google Cloud Run Gen2 `us-east4` Virginia)
- **Audit Timestamp:** `2026-11-01 02:11:17 UTC`
- **Telemetry Isolation:** `demo: true` (Zero pollution of `external_agent_match_pulls`)
- **Reproducible Evidence SHA-256:** `8739b472d9f20a790062701ddfbd6127273480e4f3dd438dd6732ab8fe60f407`

## Experiment A: 10-Intent Matchmaking Accuracy & 2-Stage Timing Split (`POST /v1/matchmake`)

| # | Domain Intent | Matched Live Agent ID | MGLE-NNP | Intent Mask | Matched Bits | Step 1 Filter (ms) | Step 2 Rank (ms) | Total Server (ms) | Client RTT (ms) | HMAC Execution Ticket |
| :-: | :--- | :--- | :-: | --: | :-: | --: | --: | --: | --: | :--- |
| 1 | Finance & SEC Equity | `mcp://ai.constellationfinance/constellation-finance-mcp` | `BBBA-ZES` | `1` | 1 | 1.0514 | 0.0347 | **1.086** | 561.86 | `demo_v2.1793499052.d51de63...` |
| 2 | Crypto & Base L2 | `mcp://ai.avasis/quant-research` | `BBAA-ZES` | `2` | 1 | 1.0937 | 0.0492 | **1.143** | 465.18 | `demo_v2.1793499053.1b17f14...` |
| 3 | Coding & Python AST | `mcp://ac.snag/snag` | `BBBA-ZES` | `4` | 1 | 1.037 | 0.0597 | **1.097** | 423.13 | `demo_v2.1793499053.64aef32...` |
| 4 | GitHub Repo Automation | `mcp://ai.chipp/chipp-channels` | `BBBA-ZES` | `8` | 1 | 1.1036 | 0.0375 | **1.141** | 560.52 | `demo_v2.1793499054.320bcb9...` |
| 5 | Web Search & RAG | `mcp://ai.buildandship/agent` | `BBAA-ZES` | `48` | 1 | 1.0907 | 0.4946 | **1.585** | 425.29 | `demo_v2.1793499054.646c9e9...` |
| 6 | SQL & Postgres Analytics | `mcp://ai.justdeploy/mcp` | `BBBA-ZES` | `192` | 1 | 1.0272 | 0.0501 | **1.077** | 451.8 | `demo_v2.1793499055.b65a9ec...` |
| 7 | Weather & NOAA Telemetry | `mcp://ai.dryos/dryos` | `BBCA-ZES` | `256` | 1 | 1.0948 | 0.0296 | **1.124** | 376.33 | `demo_v2.1793499055.0758c03...` |
| 8 | Maps & Virginia Geo-Routing | `mcp://ai.skillsinput/mcp` | `BBBA-ZES` | `512` | 1 | 1.1954 | 0.041 | **1.236** | 411.9 | `demo_v2.1793499056.fea13cb...` |
| 9 | Construction & 3D CAD | `mcp://academy.apexai/apex-ai-academy` | `BBAA-ZES` | `3072` | 1 | 1.0373 | 0.0423 | **1.08** | 404.31 | `demo_v2.1793499056.71cb0b7...` |
| 10 | Commerce & Stripe Payments | `mcp://ai.bezal/local-commerce` | `BBBA-ZES` | `4096` | 1 | 1.011 | 0.0389 | **1.05** | 391.67 | `demo_v2.1793499057.f94a1da...` |

## Experiment B: Provider-Independent 3-Agent Crew Assembly (`mode: "crew"`)

| Triad Scenario | Slot 1: Compute (`S`) | Slot 2: Domain Complement (`D`) | Slot 3: Independent Verifier | Single Cov % | Crew Cov % | Crew Quality Score | Provider Indep | Server (ms) |
| :--- | :--- | :--- | :--- | --: | --: | --: | :-: | --: |
| Triad 1: Construction + CAD + Payments | `mcp://academy.apexai/apex-ai-academy (BBAA-ZES)` | `mcp://ai.qcdatabase/mcp (BBBA-ZES)` | `mcp://ai.immokit/mcp (BBBA-ZES)` | 50.0% | **100.0%** | **98.0** | `True` (3/3) | 1.232 |
| Triad 2: Crypto + SQL Database + GitHub Audit | `mcp://ai.avasis/quant-research (BBAA-ZES)` | `mcp://ai.qcdatabase/mcp (BBBA-ZES)` | `mcp://ai.chipp/chipp-channels (BBBA-ZES)` | 25.0% | **75.0%** | **86.75** | `True` (3/3) | 1.477 |
| Triad 3: Web Search + Python Coding + Finance | `mcp://ai.buildandship/agent (BBAA-ZES)` | `mcp://ai.paperlantern/code (BBCA-ZES)` | `mcp://ai.agenticplug/agent-ready-report (BBBA-ZES)` | 25.0% | **75.0%** | **86.75** | `True` (3/3) | 3.341 |

## Experiment C: Anti-Sabotage Outcome Integrity (`POST /v1/outcome`)

- **Red-Team Payload:** `outcome_success: false`, `measured_ms: 9999`, forged ticket `v2.1700000000.deadbeef00000000.forgedsignature000000000` against live agent `mcp://ai.constellationfinance/constellation-finance-mcp`.
- **HMAC Verification Status:** `EXPIRED_TICKET_24H`
- **Independent Server Probe Executed:** `{'executed': True, 'endpoint_reachable': True, 'probe_latency_ms': 25}`
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
    "probe_latency_ms": 25
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
| `100_agents` | 100 | **0.0841** | 0.1391 | 0.1591 | 0.0901 | 0.9353 | **11.1x** |
| `1000_agents` | 1000 | **0.671** | 0.7539 | 0.8278 | 0.6837 | 8.8934 | **13.3x** |
| `1531_live_pool` | 1531 | **1.0466** | 1.3485 | 4.2173 | 1.1411 | 14.5008 | **13.9x** |
| `10000_scaled_pool` | 10000 | **6.8278** | 26.4281 | 26.4504 | 8.2936 | 109.2188 | **16.0x** |

### 3. Client-Side End-to-End HTTPS Round-Trip Latency (30 Sequential Samples)
- **Min RTT:** `430.25 ms` | **P50 RTT:** `507.76 ms` | **Mean RTT:** `519.84 ms` | **P95 RTT:** `625.13 ms` | **P99 RTT:** `634.33 ms` | **Max RTT:** `637.99 ms`

---

## 5. Experiment 5 -- Read-Only Autonomous Security & Invariant Audit (GET /v1/audit)

Live non-mutating verification of inventory reconciliation, 3-way contract parity, HMAC single-use replay & demo_v2 isolation, SSRF probe protection, and runtime source SHA-256 provenance:

```json
{
    "audit_spec":  "MglennP Radial Switchboard — Read-Only Autonomous Verification Suite (Spec Rev 2.0.0)",
    "invariants":  {
                       "1_inventory_reconciled":  {
                                                      "pass":  true,
                                                      "equation":  "1803 == 1531 (live) + 96 (quarantined) + 173 (repos) + 3 (canaries) + 0 (slashed)"
                                                  },
                       "2_contract_version_parity":  {
                                                         "pass":  true,
                                                         "openapi_version":  "2.0.0",
                                                         "mcp_manifest_version":  "2.0.0"
                                                     },
                       "3_ticket_hmac_and_replay_guard":  {
                                                              "pass":  true,
                                                              "valid_first_use":  "HMAC_TICKET_VERIFIED",
                                                              "second_use_replay_check":  "REPLAYED_TICKET_REJECTED",
                                                              "cross_agent_binding_check":  "INVALID_HMAC_SIGNATURE",
                                                              "demo_isolation_check":  "DEMO_TICKET_NON_MUTATING",
                                                              "expired_or_forged_check":  "EXPIRED_TICKET_24H"
                                                          },
                       "4_ssrf_probe_guard":  {
                                                  "pass":  true,
                                                  "cloud_metadata_blocked":  true,
                                                  "loopback_blocked":  true,
                                                  "redirects_disabled":  true
                                              },
                       "5_source_provenance_sha256":  {
                                                          "pass":  true,
                                                          "switchboard_api_sha256":  "c03d0fcac9b1cc92e82ae7d65229bded8be3c3d32ad1c4a66896a2077faa2e34",
                                                          "radial_synapse_phonebook_sha256":  "4f78f22a002058a2fcc21006c1e9d633778662c4cdc2258bfaa9393771a54e5f"
                                                      }
                   }
}
```
